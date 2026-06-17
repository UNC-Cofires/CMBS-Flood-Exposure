import numpy as np
import pandas as pd
import json
import sys
import os
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from src.utils.config import find_project_root, load_config
from llm_address_parsing_prompts import build_prompt

### *** INITIAL SETUP *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

# Get current working directory
pwd = os.getcwd()

# Get ID of local LLM to run
MODEL_ID = sys.argv[1]
MODEL_NAME = MODEL_ID.split('/')[-1]
print(f'Local LLM: {MODEL_NAME}')

# Specify chunk size (e.g., save progress every 500 addresses)
CHUNK_SIZE=500

# Create folder for output
outfolder = os.path.join(pwd,f'llm_address_parsing/{MODEL_NAME}')
os.makedirs(outfolder,exist_ok=True)

### *** LOAD DATA *** ###

address_dir = os.path.join(pwd,'geocoding_input')
address_data_path = os.path.join(address_dir,'filtered_loans_address_data.parquet')
address_data = pd.read_parquet(address_data_path)

# Break list of addresses into chunks
address_data['chunk'] = (np.arange(len(address_data)) // CHUNK_SIZE) + 1

# Determine which chunks we've already geocoded
completed_chunks = [x for x in os.listdir(outfolder) if x.endswith('parquet')]
completed_chunks = [int(x.split('.parquet')[0].split('_')[-1]) for x in completed_chunks]

# Keep only those loans that are not yet geocoded
address_data = address_data[~address_data['chunk'].isin(completed_chunks)]
remaining_chunks = address_data['chunk'].unique()

### *** LOAD MODEL *** ###

quantization_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, padding_side = "left")

# LLaMA-based tokenizers do not define a pad token by default.
# Setting it to eos_token is the standard workaround for batched inference.
# The attention mask generated during tokenization ensures padded positions
# are ignored by the model, so using eos_token here is safe.
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    quantization_config=quantization_config,
    device_map="auto",
    # Note: do NOT set torch_dtype manually when using bitsandbytes
)

### *** APPLY MODEL *** ###

def _tokenize_batch(messages_list: list[list[dict]]) -> dict:
    """
    Applies the chat template to each conversation individually to produce
    formatted strings, then tokenizes and left-pads all of them into a
    single batch.

    Two-step approach (template → string, then tokenize) is used for
    compatibility across Transformers versions and to keep padding logic
    in one place.

    Left padding (set on the tokenizer at load time) is required for
    decoder-only models during batched generation: the generated tokens
    must be right-aligned so that all sequences in the batch begin
    generating from the same position.
    """
    text_inputs = [
        tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=False,         # Return a plain string, not tensors
            enable_thinking=False,
        )
        for messages in messages_list
    ]

    # Tokenize all strings together so padding is applied uniformly
    return tokenizer(
        text_inputs,
        return_tensors="pt",
        padding=True,       # Pad to the longest sequence in the batch
        truncation=False,
    )


def _decode_output(raw_output: str) -> dict:
    """
    Attempts to parse a JSON object from the model's raw output.
    Returns a fallback dict with raw_output populated on failure.
    """
    try:
        cleaned = (
            raw_output.strip()
            .removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )
        return json.loads(cleaned)
    except json.JSONDecodeError:
        print(f"Warning: Could not parse JSON from model output")
        return {
            "multiple_locations": None,
            "range_too_large":    None,
            "range_ambiguous":    None,
            "addresses":          [],
        }


def parse_addresses_batch(
    address_ids: list,
    address_strings: list[str],
    batch_size: int = 8,
) -> pd.DataFrame:
    """
    Classifies and expands a list of address strings in batches,
    returning the results as a DataFrame.

    Args:
        address_ids:     Identifiers for each address (any hashable type).
        address_strings: Address strings to parse, one per ID.
        batch_size:      Number of addresses per forward pass. Reduce this
                         if you encounter GPU out-of-memory errors; the
                         optimal value depends on GPU memory and prompt length.

    Returns:
        A DataFrame with one row per input address and columns:
            address_id, address_string, multiple_locations,
            range_too_large, range_ambiguous, addresses, raw_output.
        raw_output is None for rows where JSON parsing succeeded and
        contains the raw model output for rows where it failed.
    """
    if len(address_ids) != len(address_strings):
        raise ValueError("address_ids and address_strings must have the same length.")

    records = []

    for batch_start in range(0, len(address_strings), batch_size):
        batch_ids     = address_ids[batch_start : batch_start + batch_size]
        batch_strings = address_strings[batch_start : batch_start + batch_size]

        print(
            f"Processing addresses {batch_start + 1}–"
            f"{batch_start + len(batch_strings)} of {len(address_strings)} ..."
        )

        # Build prompt messages and tokenize the whole batch at once
        messages_list = [build_prompt(addr) for addr in batch_strings]
        inputs = _tokenize_batch(messages_list).to(model.device)

        # All sequences are left-padded to the same length, so a single
        # input_length value correctly marks where generated tokens begin
        # for every sequence in the batch.
        input_length = inputs["input_ids"].shape[-1]

        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=2048,
                do_sample=False,          # Ensures output is deterministic and reproducible
                eos_token_id=tokenizer.eos_token_id,
                pad_token_id=tokenizer.eos_token_id,
            )

        # Decode and parse each sequence in the batch
        for addr_id, addr_string, single_output in zip(
            batch_ids, batch_strings, output_ids
        ):
            generated_tokens = single_output[input_length:]
            raw_output = tokenizer.decode(
                generated_tokens, skip_special_tokens=True
            ).strip()

            parsed = _decode_output(raw_output)

            records.append({
                "address_id":         addr_id,
                "address_string":     addr_string,
                "multiple_locations": parsed.get("multiple_locations"),
                "range_too_large":    parsed.get("range_too_large"),
                "range_ambiguous":    parsed.get("range_ambiguous"),
                "addresses":          parsed.get("addresses", [])})

    return pd.DataFrame(records).fillna(pd.NA)

### *** PROCESS ADDRESS DATA IN CHUNKS *** ###

for chunk_number in remaining_chunks:

    print(f'\n# --- Chunk Number: {chunk_number} / {max(remaining_chunks)} --- #\n',flush=True)
    
    chunk_mask = (address_data['chunk']==chunk_number)

    address_ids = address_data[chunk_mask]['masterloanidtrepp'].tolist()
    address_strings = address_data[chunk_mask]['address'].tolist()

    # Parse addresses
    results_df = parse_addresses_batch(address_ids, address_strings, batch_size=25)
    results_df.rename(columns={'address_id':'masterloanidtrepp'},inplace=True)
    results_df['model_id'] = MODEL_ID

    # Save results
    outname = os.path.join(outfolder,f'parsed_address_data_chunk_{chunk_number:04d}.parquet')
    results_df.to_parquet(outname)