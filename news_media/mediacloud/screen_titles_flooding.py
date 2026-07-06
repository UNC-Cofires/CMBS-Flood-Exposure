import numpy as np
import pandas as pd
import time
from datetime import timedelta
from copy import deepcopy
import json
import sys
import os
from vllm import LLM, SamplingParams
from src.utils.config import find_project_root, load_config
from media_analysis_prompts import build_title_screening_flood_prompt

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

def screen_titles_batch(urls: list[str], titles: list[str]) -> list[str]:
    """
    Screen a list of news article urls and titles in a single vLLM call.
    Returns a list of raw JSON strings in the same order as the input list.
    """
    # Build and format a prompt string for each address
    prompts = [
        _format_prompt(build_title_screening_flood_prompt(url,title))
        for url,title in zip(urls,titles)
    ]

    # vLLM schedules all prompts together and returns results in input order
    outputs = llm.generate(prompts, sampling_params)

    # Extract the generated text string from each RequestOutput object
    return [out.outputs[0].text for out in outputs]

def postprocess_output_text(result,id,url,title):
    """
    This function checks whether the output returned by an LLM 
    is a valid JSON  while adding fields for the article id, url, and title. 
    
    Returns a python dictionary. 
    """

    article_dict = {'id':id,'url':url,'title':title,'parsing_errors':False}

    # Attempt to parse JSON output
    try:
        result_dict = json.loads(result)
        article_dict['classification'] = result_dict['classification']
        article_dict['reasoning'] = result_dict['reasoning']

    # If errors occur, make a note of this and return an empty JSON array
    except:
        article_dict['parsing_errors'] = True
        article_dict['classification'] = pd.NA
        article_dict['reasoning'] = pd.NA

    return article_dict

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
    
    # Create folder for output
    outfolder = os.path.join(pwd,f'title_screening/flooding/{MODEL_NAME}')
    os.makedirs(outfolder,exist_ok=True)
    
    ### *** LOAD MEDIACLOUD SEARCH RESULTS *** ###
    
    # Load data on media search results
    search_results_folder = os.path.join(pwd,'search_results')
    search_results_periods = pd.period_range('2008-01','2026-04',freq='M')
    search_results_period_strings = np.array([period.strftime('%Y-%m') for period in search_results_periods])
    
    input_filepaths = np.array([os.path.join(search_results_folder,f'{period_string}_search_results.parquet') for period_string in search_results_period_strings])
    output_filepaths = np.array([os.path.join(outfolder,f'{period_string}_title_screening.parquet') for period_string in search_results_period_strings])
    already_processed = np.array([os.path.exists(path) for path in output_filepaths])
    
    input_filepaths = input_filepaths[~already_processed]
    output_filepaths = output_filepaths[~already_processed]
    search_results_period_strings = search_results_period_strings[~already_processed]
    
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
        # The few-shot prompt in this script is roughly 2000 tokens;
        # 8000 gives ample headroom. Increase this value if you hit
        # context-length errors at runtime.
        max_model_len=8000,
    
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
        max_tokens=1024,
    )
    
    ### *** PROCESS ARTICLE TITLES AND URLS IN CHUNKS *** ###
        
    for period_string,input_filepath,output_filepath in zip(search_results_period_strings,input_filepaths,output_filepaths):
    
        print(f'\n# --- Screening titles of articles from {period_string} --- #\n',flush=True)
    
        t1 = time.time()
    
        # Get list of article titles and urls
        articles = pd.read_parquet(input_filepath)
        article_ids = articles['id'].tolist()
        article_urls = articles['url'].tolist()
        article_titles = articles['title'].tolist()
    
        # Classify whether articles deal with flood / hurricane events based on title and url
        results = screen_titles_batch(article_urls,article_titles)
        results_df = pd.DataFrame([postprocess_output_text(result,id,url,title) for result,id,url,title in zip(results,article_ids,article_urls,article_titles)])
    
        # Record the specific LLM used to classify article 
        results_df['model_id'] = MODEL_ID
    
        # Save results
        results_df.to_parquet(output_filepath)
    
        t2 = time.time()
    
        time_elapsed = timedelta(seconds=t2-t1)
        print(f'Time elapsed: {time_elapsed}',flush=True)
