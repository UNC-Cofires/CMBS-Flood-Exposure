import numpy as np
import pandas as pd
import os
from src.utils.config import find_project_root, load_config

### *** INITIAL SETUP *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

# Get current working directory 
pwd = os.getcwd()

# Specify path to original loan-level address data
address_dir = os.path.join(pwd,'geocoding_input')
address_data_path = os.path.join(address_dir,'filtered_loans_address_data.parquet')
address_data = pd.read_parquet(address_data_path)

### *** COMBINE DATA *** ###

# LLM-parsed addresses that were consistent across models
llm_addresses_path = os.path.join(address_dir,'consistent_parsed_addresses.parquet')
llm_addresses = pd.read_parquet(llm_addresses_path,columns=['masterloanidtrepp','address_components'])

# Human-reviewed addresses that were inconsistent across LLMs
human_addresses_path = os.path.join(pwd,'manual_review/inconsistent_address_parsing/review_results.parquet')
human_addresses = pd.read_parquet(human_addresses_path,columns=['masterloanidtrepp','address_components'])

# Human-reviewed addresses from Queens, NYC
queens_addresses_path = os.path.join(pwd,'manual_review/queens_addresses/review_results.parquet')
queens_addresses = pd.read_parquet(queens_addresses_path,columns=['masterloanidtrepp','address_components'])

# Remove Queens addresses from other dataframes to avoid duplication
llm_addresses = llm_addresses[~llm_addresses['masterloanidtrepp'].isin(queens_addresses['masterloanidtrepp'])]
human_addresses = human_addresses[~human_addresses['masterloanidtrepp'].isin(queens_addresses['masterloanidtrepp'])]

# Concatenate dataframes
parsed_addresses = pd.concat([llm_addresses,human_addresses,queens_addresses])

# Attach parsed address components to original dataframe
address_data = pd.merge(address_data,parsed_addresses,how='left',on='masterloanidtrepp')

### *** SAVE RESULTS *** ###

outname = os.path.join(address_dir,'filtered_loans_parsed_address_data.parquet')
address_data.to_parquet(outname)