import numpy as np
import pandas as pd
import os
from src.utils.config import find_project_root, load_config

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

# Get present working directory
pwd = os.getcwd()

# Get path to trepp property-level data files
prop_dir = os.path.join(config['paths']['trepp_data_dir'],'prop')
prop_filepaths = [os.path.join(prop_dir,x) for x in np.sort(os.listdir(prop_dir))]

# Get IDs of filtered loans that meet inclusion criteria
loan_path = os.path.join(pwd,'filtered_loans.parquet')
loan_ids = pd.read_parquet(loan_path,columns=['masterloanidtrepp'])['masterloanidtrepp'].unique().tolist()

# Get IDs of properties associated with these loans
filters = [('masterloanidtrepp','in',loan_ids)]
loan_prop_info = pd.read_parquet(prop_filepaths,columns=['masterloanidtrepp','masterpropidtrepp'],filters=filters).drop_duplicates()
prop_ids = loan_prop_info['masterpropidtrepp'].unique().tolist()

# Print number of unique loans and properties
print(f'Number of loans: {len(loan_ids)}',flush=True)
print(f'Number of properties: {len(prop_ids)}',flush=True)

# Concatenate data from included properties and save results
outname = os.path.join(pwd,'filtered_properties.parquet')
props = pd.read_parquet(prop_filepaths,filters=[('masterpropidtrepp','in',prop_ids)])
props.to_parquet(outname)