import numpy as np
import pandas as pd
import json
import sys
import os
from src.utils.config import find_project_root, load_config

### *** HELPER FUNCTIONS *** ###

def load_chunked_parquet_data(data_folder):
    """
    This function reads in all parquet files in data_folder and 
    returns a concatenated pandas dataframe. Parquet files are 
    assumed to all follow the same layout.

    The main use case for this function is reading in data that 
    was written in chunks. 
    (e.g., "data_file_part_001.parquet","data_file_part_002.parquet", etc.)
    """

    files = os.listdir(data_folder)
    files = np.sort([f for f in files if f.endswith('.parquet')])
    filepaths = [os.path.join(data_folder,f) for f in files]
    df = pd.read_parquet(filepaths)
    return df

def all_rows_equal(df,subset=None):
    """
    This function checks if all rows in a pandas dataframe are equal to one another. 
    If you would like to compare across only a subset of columns in the dataframe, 
    please pass a list of columns to use using the subset argument.
    """

    if subset is not None:
        all_equal = df[subset].eq(df.iloc[0][subset],axis=1).all(axis=None)
    else:
        all_equal = df.eq(df.iloc[0],axis=1).all(axis=None)

    return all_equal

### *** INITIAL SETUP *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

# Get current working directory 
pwd = os.getcwd()

# Specify path to original loan-level address data
address_dir = os.path.join(pwd,'geocoding_input')
loan_level_address_data_path = os.path.join(address_dir,'filtered_loans_address_data.parquet')
loan_level_address_data = pd.read_parquet(loan_level_address_data_path)

# List of LLMs whose outputs will be compared
# (command-line argument passed as a comma-separated list)
model_ids_string =  "cyankiwi/Qwen3.5-9B-AWQ-4bit,cyankiwi/gemma-4-12B-it-AWQ-INT4"#sys.argv[1]
model_ids = model_ids_string.split(',')
model_names = [model_id.split('/')[-1] for model_id in model_ids]

print('\nChecking for consistency across the following LLMs:',flush=True)
for model_name in model_names:
    print(f'    {model_name}',flush=True)

### *** CHECK FOR CONSISTENCY ACROSS MODELS *** ###

# Load data on addresses parsed using LLMs
data_folders = [os.path.join(pwd,f'llm_address_parsing/{model_name}') for model_name in model_names]
parsed_addresses = pd.concat([load_chunked_parquet_data(folder) for folder in data_folders]).reset_index(drop=True)
parsed_addresses = parsed_addresses.sort_values(by='masterloanidtrepp').reset_index(drop=True)

comparison_cols = ['parsing_errors','address_components']
check_consistency = parsed_addresses.groupby('masterloanidtrepp').apply(all_rows_equal,subset=comparison_cols)
check_consistency = pd.DataFrame({'masterloanidtrepp':check_consistency.index.values,'is_consistent':check_consistency.values})

# Create a list of loans where output is consistent / inconsistent
consistent_loan_ids = check_consistency[check_consistency['is_consistent']==True]['masterloanidtrepp'].tolist()
inconsistent_loan_ids = check_consistency[check_consistency['is_consistent']==False]['masterloanidtrepp'].tolist()

# Create a list of loans that could not be parsed by any model
parsing_errors_mask = (parsed_addresses['parsing_errors'])&(parsed_addresses['masterloanidtrepp'].isin(consistent_loan_ids))
parsing_errors_loan_ids = parsed_addresses[parsing_errors_mask]['masterloanidtrepp'].unique().tolist()

# Print results to console
num_consistent_loans = len(consistent_loan_ids)
num_inconsistent_loans = len(inconsistent_loan_ids)
num_loans = num_consistent_loans + num_inconsistent_loans
pct_consistent = 100*(num_consistent_loans/num_loans)
num_parsing_failures = len(parsing_errors_loan_ids)
pct_parsing_failures = 100*(num_parsing_failures/num_loans)

print(f'\nNumber of addresses that were consistent across LLMs: {num_consistent_loans} / {num_loans} ({pct_consistent:.2f}%)')
print(f'Number of addresses that were inconsistent across LLMs: {num_inconsistent_loans} / {num_loans} ({100-pct_consistent:.2f}%)')
print(f'Number of addresses that were consistent but could not be parsed: {num_parsing_failures} / {num_loans} ({pct_parsing_failures:.2f}%)')

### *** SAVE RESULTS *** ###

# Split out addresses that were inconsistent or that failed to parse for manual review
manual_review_mask = parsed_addresses['masterloanidtrepp'].isin(inconsistent_loan_ids)|parsed_addresses['masterloanidtrepp'].isin(parsing_errors_loan_ids)
manual_review_addresses = parsed_addresses[manual_review_mask].reset_index(drop=True)
consistent_addresses = parsed_addresses[~manual_review_mask].drop(columns='model_id').drop_duplicates().reset_index(drop=True)

# Randomly sample 500 addresses from consistent sample to be manually reviewed for correctness
consistent_review_sample = consistent_addresses.sample(500)

# Save to file
outname = os.path.join(address_dir,'consistent_parsed_addresses.parquet')
consistent_addresses.to_parquet(outname)

outname = os.path.join(address_dir,'consistent_parsed_addresses_random_sample.parquet')
consistent_review_sample.to_parquet(outname)

outname = os.path.join(address_dir,'manual_review_parsed_addresses.parquet')
manual_review_addresses.to_parquet(outname)
