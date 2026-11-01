import numpy as np
import pandas as pd
import geopandas as gpd
import os
import json
from copy import deepcopy
from src.utils.config import find_project_root, load_config

### *** HELPER FUNCTIONS *** ###

def create_queens_style_guess(input_string):
    """
    Because addresses in the Queens borough of New York City often include hyphens, 
    they are frequently misidientifed as the "range" address type by our LLM-based
    parsing approach. This script converts "range" address types into a "queens_exact"
    address type, correcting the most common misidentification scenario. This will serve
    as the initial guess in a manual review of all addresses located in Queens. 
    """

    input_address_components = json.loads(input_string)
    output_address_components = []
    
    for input_component in input_address_components:
        
        if input_component['address_type'] == 'range':
    
            output_component = {}
            output_component['address_type'] = 'queens_exact'
            output_component['cross_street'] = input_component['first_building_number']
            output_component['first_building_number'] = input_component['last_building_number']
            output_component['last_building_number'] = input_component['last_building_number']
            output_component['street'] = input_component['street']
            
        else:
            output_component = deepcopy(input_component)
    
        output_address_components.append(output_component)

    output_string = json.dumps(output_address_components)
    return output_string

### *** MAIN SCRIPT *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

# Get current working directory 
pwd = os.getcwd()

# Read in data on loan addresses
address_data_path = os.path.join(pwd,'geocoding_input/filtered_loans_address_data.parquet')
address_data = pd.read_parquet(address_data_path)

# Get loans from New York state
address_data = address_data[address_data['state'] == 'NY']

# Get loans from Queens zip codes
queens_zip_mask = address_data['zip'].str[:3].isin(['111','113','114','116','110'])
address_data = address_data[queens_zip_mask]

# Record loan ids
queens_loan_ids = address_data['masterloanidtrepp'].tolist()

# Read in data on llm-parsed addresses
llm_parsed_addresses = pd.read_parquet(os.path.join(pwd,'geocoding_input/consistent_parsed_addresses.parquet'))
llm_parsed_addresses = llm_parsed_addresses[llm_parsed_addresses['masterloanidtrepp'].isin(queens_loan_ids)]

# Read in data on manually-parsed addresses
manual_parsed_addresses = pd.read_parquet(os.path.join(pwd,'manual_review/inconsistent_address_parsing/review_results.parquet'))
manual_parsed_addresses = manual_parsed_addresses[manual_parsed_addresses['masterloanidtrepp'].isin(queens_loan_ids)]

# Combine data
common_cols = ['masterloanidtrepp','address_string','address_components']
queens_addresses = pd.concat([llm_parsed_addresses[common_cols],manual_parsed_addresses[common_cols]]).reset_index(drop=True)

# Correct most common misidentification scenario ("range" --> "queens_exact")
queens_addresses['address_components'] = queens_addresses['address_components'].apply(create_queens_style_guess)

# Save output
outname = os.path.join(pwd,'geocoding_input/queens_addresses_for_review.parquet')
queens_addresses.to_parquet(outname)