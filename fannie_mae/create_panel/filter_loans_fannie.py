import numpy as np
import pandas as pd
import os
from src.utils.config import find_project_root, load_config

### *** INITIAL SETUP *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

### *** LOAD DATA *** ###

# Search results for Fannie Mae Multifamily MBS returned by the DUS Disclose Portal
loans = pd.read_parquet(config['paths']['dus_disclose_search_results'])

# List of included US states
included_states = np.loadtxt(config['paths']['included_states'],dtype=str)

### *** FILTER DATA *** ###

# Get starting number of loans
num_loans = len(loans['Loan Number'].unique())
starting_num_loans = num_loans
print(f'\nStarting number of loans: {num_loans}\n',flush=True)

# Exclude multi-property loans
property_count = loans[['Loan Number','Property ID']].groupby('Loan Number').agg(num_properties=('Property ID','nunique')).reset_index()
multi_property_loan_ids = property_count[property_count['num_properties'] > 1]['Loan Number'].unique()
multi_property_mask = (loans['Loan Number'].isin(multi_property_loan_ids))
loans = loans[~multi_property_mask]
num_loans = len(loans['Loan Number'].unique())
print(f'1) Dropped multi-property loans. Number of loans remaining: {num_loans}',flush=True)

# Exclude cross-collateralized and supplemental loans
# (i.e., those where one property serves as collateral for multiple loans)
loan_count = loans[['Loan Number','Property ID']].groupby('Property ID').agg(num_loans=('Loan Number','nunique')).reset_index()
multi_loan_property_ids = loan_count[loan_count['num_loans'] > 1]['Property ID'].unique()
multi_loan_mask = (loans['Property ID'].isin(multi_loan_property_ids))|(loans['Loan Number'].duplicated(keep=False))
loans = loans[~multi_loan_mask]
num_loans = len(loans['Loan Number'].unique())
print(f'2) Dropped cross-collateralized and supplemental loans. Number of loans remaining: {num_loans}',flush=True)

# Exclude properties with missing address information
address_cols = ['Property Address','Property City','Property State','Property Zip Code']
missing_address_mask = loans[address_cols].isna().any(axis=1)
loans = loans[~missing_address_mask]
num_loans = len(loans['Loan Number'].unique())
print(f'3) Dropped loans with missing address information. Number of loans remaining: {num_loans}',flush=True)

# Exclude loans from outside list of included states
included_states_mask = loans['Property State'].isin(included_states)
loans = loans[included_states_mask].reset_index(drop=True)
num_loans = len(loans['Loan Number'].unique())
print(f'4) Dropped from outside list of included states. Number of loans remaining: {num_loans}',flush=True)

# Print update for user
loans = loans.reset_index(drop=True)
print(f'\nEnding number of loans: {num_loans} ({100*num_loans/starting_num_loans:.2f}%)\n',flush=True)

### *** SAVE RESULTS *** ###

pwd = os.getcwd()
outname = os.path.join(pwd,'filtered_loans_fannie.parquet')
loans.to_parquet(outname)