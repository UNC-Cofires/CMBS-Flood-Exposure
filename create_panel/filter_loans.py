import numpy as np
import pandas as pd
import os
from src.utils.config import find_project_root, load_config

### *** HELPER FUNCTIONS *** ###

def filter_loans(loans,loan_prop_info,included_states):
    """
    This function selects Trepp CMBS loans that meet the following inclusion criteria:

    1. Loans that are non-delinquent when first observed in the data
    2. Single-property loans
    3. Single-note loans
    4. Loans collateralized by properties located in a specified list of states

    You might also want to perform some pre-filtering to ensure that the loans fed into
    this function consist entirely of first-lien mortgages. This seems to be the standard
    for most conduit and agency securitizations, but may not hold for other deal types
    (e.g., CRE CLOs). 

    param: loans: Trepp loan-level data
    param: loan_prop_info: dataframe describing associations between loan ids and property ids
    param: included_states: list states to include (e.g., ["NY","CA","TX"])
    returns: loans: filtered version of loan-level data
    """
    
    num_loans = len(loans['masterloanidtrepp'].unique())
    first_obs = loans.drop_duplicates(subset=['masterloanidtrepp'],keep='first')
    starting_num_loans = num_loans

    print(f'\nStarting number of loans: {num_loans}\n',flush=True)

    # Filter out loans that are known to be delinquent when first observed
    non_delinq_mask = (first_obs['dlqderivedcd'].isna())|(first_obs['dlqderivedcd'].isin(['0','A','B']))
    first_obs = first_obs[non_delinq_mask]
    loans = loans[loans['masterloanidtrepp'].isin(first_obs['masterloanidtrepp'])]
    num_loans = len(loans['masterloanidtrepp'].unique())

    print(f'1) Dropped loans known to be delinquent when first observed. Number of loans remaining: {num_loans}',flush=True)

    # Filter out multi-property loans
    multi_prop_loan_ids = loan_prop_info[loan_prop_info['masterloanidtrepp'].duplicated(keep=False)]['masterloanidtrepp'].unique().tolist()
    m1 = (first_obs['numprop'] > 1)
    m2 = (first_obs['address'].str.lower().str.contains('various'))
    m3 = (first_obs['state']=='VR')
    m4 = (first_obs['masterloanidtrepp'].isin(multi_prop_loan_ids))
    multi_prop_mask = (m1|m2|m3|m4)
    first_obs = first_obs[~multi_prop_mask]
    loans = loans[loans['masterloanidtrepp'].isin(first_obs['masterloanidtrepp'])]
    num_loans = len(loans['masterloanidtrepp'].unique())

    print(f'2) Dropped multi-property loans. Number of loans remaining: {num_loans}',flush=True)
    
    # Filter out multi-note loans
    multi_note_loan_ids = loan_prop_info[loan_prop_info['masterpropidtrepp'].duplicated(keep=False)]['masterloanidtrepp'].unique().tolist()
    m1 = (first_obs['numnotes']>1)&(~first_obs['numnotes'].isna())
    m2 = (~first_obs['acrossdealsloanidtrepp'].isna())
    m3 = (~first_obs['loanindeals'].isna())
    m4 = (first_obs['masterloanidtrepp'].isin(multi_note_loan_ids))
    multi_note_mask = (m1|m2|m3|m4)
    first_obs = first_obs[~multi_note_mask]
    loans = loans[loans['masterloanidtrepp'].isin(first_obs['masterloanidtrepp'])]
    num_loans = len(loans['masterloanidtrepp'].unique())

    print(f'3) Dropped multi-note loans. Number of loans remaining: {num_loans}',flush=True)

    # Filter out loans from outside list of included states
    state_mask = (first_obs['state'].isin(included_states))
    first_obs = first_obs[state_mask]
    loans = loans[loans['masterloanidtrepp'].isin(first_obs['masterloanidtrepp'])]
    num_loans = len(loans['masterloanidtrepp'].unique())

    print(f'4) Dropped loans from outside list of included states. Number of loans remaining: {num_loans}',flush=True)

    # Reset index
    loans = loans.reset_index(drop=True)

    print(f'\nEnding number of loans: {num_loans} ({100*num_loans/starting_num_loans:.2f}%)\n',flush=True)

    return loans

### *** INITIAL SETUP *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

### *** GET LIST OF CMBS DEALS TO INCLUDE *** ###

# Public offerings of CMBS conduit deals from the 1998-2025 period
# (excludes privately-placed securities, SASB, and other less-common deal types)
deals = pd.read_parquet(config['paths']['included_CMBS_deals'])

# Get deal IDs
dealnames = deals['DealName'].tolist()

### *** GET LOANS *** ###

# Get basic loan info
loan_dir = os.path.join(config['paths']['trepp_data_dir'],'loan')
loan_filepaths = [os.path.join(loan_dir,x) for x in np.sort(os.listdir(loan_dir))]

filters = [('dosname','in',dealnames)]
loans = pd.read_parquet(loan_filepaths,filters=filters)

# Attach details on loan capital structure
# (relevant for multi-note loans)
usecols = ['dosname',
           'masterloanidtrepp',
           'distdate',
           'numnotes',
           'acrossdealsloanidtrepp',
           'loanindeals',
           'curwholeloanbal']

loan2_dir = os.path.join(config['paths']['trepp_data_dir'],'loan2')
loan2_filepaths = [os.path.join(loan2_dir,x) for x in np.sort(os.listdir(loan2_dir))]
loan2 = pd.read_parquet(loan2_filepaths,filters=filters,columns=usecols)

# Merge data
loans = pd.merge(loans,loan2,how='left',on=['dosname','masterloanidtrepp','distdate'])

### *** GET COMBINATIONS OF LOAN AND PROPERTY IDS *** ###

# Get path to trepp property-level data files
prop_dir = os.path.join(config['paths']['trepp_data_dir'],'prop')
prop_filepaths = [os.path.join(prop_dir,x) for x in np.sort(os.listdir(prop_dir))]

# Determine associations between properties and loans
filters = [('masterloanidtrepp','in',loans['masterloanidtrepp'].unique().tolist())]
usecols = ['masterloanidtrepp','masterpropidtrepp']
loan_prop_info = pd.read_parquet(prop_filepaths,columns=usecols,filters=filters).drop_duplicates()

### *** FILTER LOANS BASED ON INCLUSION CRITERIA *** ###

# Get list of included states
included_states = np.loadtxt(config['paths']['included_states'],dtype=str)

# Filter loans
loans = filter_loans(loans,loan_prop_info,included_states)

### *** SAVE RESULTS *** ###

pwd = os.getcwd()
outname = os.path.join(pwd,'filtered_loans.parquet')
loans.to_parquet(outname)