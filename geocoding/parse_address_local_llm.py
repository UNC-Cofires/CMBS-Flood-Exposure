import numpy as np
import pandas as pd
import time
from datetime import timedelta
import json
import sys
import os
from vllm import LLM, SamplingParams
from src.utils.config import find_project_root, load_config
from llm_address_parsing_prompts import build_prompt

###----------FUNCTION DEFINITIONS----------###
# Function definitions are safe at the top level — they are not executed
# at import time, only defined. They reference `llm` and `sampling_params`
# as globals, which will be defined inside the __main__ block before
# any of these functions are called.

def _format_prompt(messages: list[dict]) -> str:
    """
    Converts a list of chat message dicts into a single formatted string.

    vLLM's generate() method expects raw text strings, not message dicts.
    apply_chat_template() handles converting the system/user/assistant turns
    into whatever input format the specific model expects (e.g. Gemma's
    <start_of_turn> / <end_of_turn> tokens).

    Note: if llm.get_tokenizer() is not available in your vLLM version,
    you can load the tokenizer separately instead:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    """
    tokenizer = llm.get_tokenizer()
    prompt = tokenizer.apply_chat_template(
        messages,
        # tokenize=False: Return a string rather than token IDs.
        # vLLM handles tokenization internally — we just need the string.
        tokenize=False,
        # add_generation_prompt=True: Appends the model's "start of response"
        # marker so the model knows it should begin generating a reply.
        add_generation_prompt=True,
        # enable_thinkign=False: disable thinking mode to save on computation
        # this means that the model provides only the final response without
        # explaining its reasoning. 
        enable_thinking=False,
    )

    return prompt

def parse_addresses_batch(addresses: list[str]) -> list[str]:
    """
    Parse a list of address strings in a single vLLM call.

    vLLM's core advantage over standard transformers inference is its ability
    to efficiently schedule many requests concurrently using PagedAttention —
    a memory management technique that avoids wasting GPU memory on padding.
    Passing all addresses at once maximizes GPU utilization and throughput
    compared to calling parse_address() in a loop.

    Returns a list of raw JSON strings in the same order as the input list.
    """
    # Build and format a prompt string for each address
    prompts = [
        _format_prompt(build_prompt(address))
        for address in addresses
    ]

    # vLLM schedules all prompts together and returns results in input order
    outputs = llm.generate(prompts, sampling_params)

    # Extract the generated text string from each RequestOutput object
    return [out.outputs[0].text for out in outputs]

def postprocess_output_text(result,address_string,address_id):
    """
    This function converts raw JSON string representation of an address parsed using local LLMs
    to a python dictionary while adding fields for the address_id and input string.

    Returns a python dictionary. 
    """

    address_dict = {'address_id':address_id,'address_string':address_string,'parsing_errors':False}

    # Attempt to parse JSON
    try:
        address_dict = address_dict | json.loads(result)

        # For single locations, enforce that address is equal to original string
        if address_dict['multiple_locations'] == False:
            address_dict['addresses'] = [address_string]

    except:
        address_dict['parsing_errors'] = True
        address_dict = address_dict | {'multiple_locations':pd.NA,'range_too_large':pd.NA,'range_ambiguous':pd.NA,'addresses':[]}

    # Sort locations alphabetically (modifies inplace)
    address_dict['addresses'].sort()
    
    # Create field listing number of locations
    address_dict['num_locations'] = len(address_dict['addresses'])

    return address_dict

###--------------MAIN EXECUTION--------------###
# Everything that spawns subprocesses — including LLM() — must be inside this guard.
# When vLLM spawns a subprocess and re-imports this script, the subprocess
# will skip this block entirely, preventing the infinite spawn loop.

if __name__ == '__main__':

    ### *** INITIAL SETUP *** ###
    
    # Determine root directory of project and load configuration file
    project_root = find_project_root()
    config = load_config()
    
    # Get current working directory
    pwd = os.getcwd()
    
    # Get ID of local LLM to run
    MODEL_ID = sys.argv[1] 
    MODEL_NAME = MODEL_ID.split('/')[-1]
    print(f'\nLocal LLM: {MODEL_NAME}\n')
    
    # Specify chunk size (e.g., save progress every 1000 addresses)
    CHUNK_SIZE=1000
    
    # Create folder for output
    outfolder = os.path.join(pwd,f'llm_address_parsing/{MODEL_NAME}')
    os.makedirs(outfolder,exist_ok=True)
    
    ### *** LOAD ADDRESS DATA *** ###
    
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
    
    ### *** MODEL LOADING *** ###
    
    # LLM() starts vLLM's inference engine and loads the model into GPU memory.
    # This happens once at startup. 
    
    llm = LLM(
        
        model=MODEL_ID,
    
        # dtype: Numeric precision for model weights.
        # "bfloat16" halves memory usage vs. float32 with minimal quality loss.
        dtype="bfloat16",
    
        # max_model_len: Maximum total sequence length (prompt + generated tokens).
        # vLLM pre-allocates its KV cache based on this value, so keeping it
        # smaller frees memory for larger batch sizes.
        # The few-shot prompt in this script is roughly 2,000–3,000 tokens;
        # 8192 gives ample headroom. Increase this value if you hit
        # context-length errors at runtime.
        max_model_len=8192,
    
        # gpu_memory_utilization: Fraction of GPU VRAM vLLM may use (0.0–1.0).
        # After loading model weights, vLLM pre-allocates the remaining share
        # of this budget for the KV cache. 0.90 leaves a small safety margin
        # to avoid out-of-memory errors from other GPU overhead.
        gpu_memory_utilization=0.90,
    )
    
    ### *** SAMPLING PARAMETERS *** ###
    
    # Controls how the model generates output tokens.
    
    sampling_params = SamplingParams(
        # temperature: Controls randomness in token selection.
        # 0.0 = greedy decoding (always pick the highest-probability token).
        # This is ideal for structured output tasks like JSON generation,
        # where you want deterministic, consistent results rather than variety.
        temperature=0.0,
    
        # max_tokens: Maximum number of new tokens to generate per request.
        # Setting this unnecessarily high wastes compute on padding;
        # setting it too low risks truncating valid output.
        max_tokens=2048,
    )
    
    ### *** PROCESS ADDRESS DATA IN CHUNKS *** ###
    
    for chunk_number in remaining_chunks:
    
        print(f'\n# --- Chunk Number: {chunk_number} / {max(remaining_chunks)} --- #\n',flush=True)
    
        t1 = time.time()
    
        # Get list of addresses to process in this chunk
        chunk_mask = (address_data['chunk']==chunk_number)
        address_ids = address_data[chunk_mask]['masterloanidtrepp'].tolist()
        address_strings = address_data[chunk_mask]['address'].tolist()
    
        # Parse addresses
        results = parse_addresses_batch(address_strings)
        results_df = pd.DataFrame([postprocess_output_text(result,address_string,address_id) for result,address_string,address_id in zip(results,address_strings,address_ids)])
    
        # Update column names and record the specific LLM used for parsing
        results_df.rename(columns={'address_id':'masterloanidtrepp'},inplace=True)
        results_df['model_id'] = MODEL_ID
    
        # Save results
        outname = os.path.join(outfolder,f'parsed_address_data_chunk_{chunk_number:04d}.parquet')
        results_df.to_parquet(outname)
    
        t2 = time.time()
    
        time_elapsed = timedelta(seconds=t2-t1)
        print(f'Time elapsed: {time_elapsed}',flush=True)