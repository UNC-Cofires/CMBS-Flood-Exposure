import numpy as np
import pandas as pd
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
model_ids_string =  sys.argv[1]
model_ids = model_ids_string.split(',')
model_names = [model_id.split('/')[-1] for model_id in model_ids]

print('\nChecking for consistency across the following LLMs:',flush=True)
for model_name in model_names:
    print(f'    {model_name}',flush=True)

### *** CHECK FOR CONSISTENCY ACROSS MODELS *** ###

# Load data on addresses parsed using LLMs
data_folders = [os.path.join(pwd,f'llm_address_parsing/{model_name}') for model_name in model_names]
parsed_addresses = pd.concat([load_chunked_parquet_data(folder) for folder in data_folders]).reset_index(drop=True)

# Create string representation of list of street numbers / addresses associated with each loan
# (Easier to make string-to-sting comparisons than list-to-list comparisons)
parsed_addresses['addresses_for_comparison'] = parsed_addresses['addresses'].astype('string[pyarrow]')
parsed_addresses = parsed_addresses.sort_values(by='masterloanidtrepp')

# Specify columns that will be used to check consistency across models
comparison_cols = ['parsing_errors',
                   'multiple_locations',
                   'range_too_large',
                   'range_ambiguous',
                   'num_locations',
                   'addresses_for_comparison']

# Check whether address parsing output associated with each loan is consistent across LLMs
check_consistency = parsed_addresses.groupby('masterloanidtrepp').apply(all_rows_equal,subset=comparison_cols)
check_consistency = pd.DataFrame({'masterloanidtrepp':check_consistency.index.values,'is_consistent':check_consistency.values})

# Create a list of loans where output is consistent / inconsistent
consistent_loan_ids = check_consistency[check_consistency['is_consistent']==True]['masterloanidtrepp'].tolist()
inconsistent_loan_ids = check_consistency[check_consistency['is_consistent']==False]['masterloanidtrepp'].tolist()

# Print results to console
num_consistent_loans = len(consistent_loan_ids)
num_inconsistent_loans = len(inconsistent_loan_ids)
num_loans = num_consistent_loans + num_inconsistent_loans
pct_consistent = 100*(num_consistent_loans/num_loans)

print(f'\nNumber of addresses that were consistent across LLMs: {num_consistent_loans} / {num_loans} ({pct_consistent:.2f}%)')
print(f'Number excluded because of inconsistencies across LLMs: {num_inconsistent_loans} / {num_loans} ({100-pct_consistent:.2f}%)')

### *** EXCLUDE ADDRESSES THAT DON'T MEET GEOCODING CRITERIA *** ###

parsed_addresses = parsed_addresses[parsed_addresses['masterloanidtrepp'].isin(consistent_loan_ids)]
parsed_addresses = parsed_addresses.drop_duplicates(subset='masterloanidtrepp').drop(columns=['model_id','addresses_for_comparison'])

m = (parsed_addresses['parsing_errors']==True)
parsed_addresses = parsed_addresses[~m]
print(f'Number excluded because of JSON parsing errors: {np.sum(m)} / {num_loans} ({100*np.mean(m):.1f}%)')

m = (parsed_addresses['range_too_large']==True)
parsed_addresses = parsed_addresses[~m]
print(f'Number excluded because the range of addresses was too large: {np.sum(m)} / {num_loans} ({100*np.mean(m):.1f}%)')

m = (parsed_addresses['range_ambiguous']==True)
parsed_addresses = parsed_addresses[~m]
print(f'Number excluded because the range of addresses was ambiguous: {np.sum(m)} / {num_loans} ({100*np.mean(m):.1f}%)')

### *** CREATE FINAL LIST OF LOCATIONS TO GEOCODE *** ###

# Explode dataframe so that each row corresponds to a potential location associated with a loan.
# Loans whose original addresses correspond to multiple locations (e.g., "110-115 Main St")
# will now show up multiple times in the dataframe (e.g., "110 Main St","111 Main St",...,"115 Main St"). 
parsed_addresses = parsed_addresses[['masterloanidtrepp','address_string','addresses']].explode('addresses')
parsed_addresses = parsed_addresses.rename(columns={'address_string':'original_address_string','addresses':'parsed_address'})
parsed_addresses = parsed_addresses.reset_index(drop=True)

# Attach data on city / state / zip
parsed_addresses = pd.merge(parsed_addresses,loan_level_address_data,how='left',on='masterloanidtrepp')
parsed_addresses = parsed_addresses[['masterloanidtrepp','propname','original_address_string','parsed_address','city','state','zip']]

# Print update to console
final_num_loans = len(parsed_addresses['masterloanidtrepp'].unique())
final_num_addresses = len(parsed_addresses)

print(f'Final list of locations to geocode consists of {final_num_addresses} addresses associated with {final_num_loans} unique loans.')
print(f'These loans represent {final_num_loans} / {num_loans} ({100*(final_num_loans/num_loans):.2f}%) of the pre-parsing number of loans.')

### *** SAVE RESULTS *** ###

outname = os.path.join(address_dir,'parsed_loan_addresses.parquet')
parsed_addresses.to_parquet(outname)

outname = os.path.join(address_dir,'parsing_consistency_check_results.parquet')
check_consistency.to_parquet(outname)
