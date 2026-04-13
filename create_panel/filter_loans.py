import numpy as np
import pandas as pd
import os

### *** HELPER FUNCTIONS *** ###

def filter_loans(loans):
    """
    This function selects Trepp CMBS loans that meet the following inclusion criteria:

    1. Loans that are first observed in data within 720 days of origination
    2. Loans that are non-delinquent when first observed in the data
    3. Single-property loans
    4. Single-note loans

    You might also want to perform some pre-filtering to ensure that the loans fed into
    this function consist entirely of first-lien mortgages. This seems to be the standard
    for most conduit and agency securitizations, but may not hold for other deal types
    (e.g., CRE CLOs). 

    param: loans: Trepp loan-level data
    returns: loans: filtered version of loan-level data
    """
    
    num_loans = len(loans['masterloanidtrepp'].unique())
    starting_num_loans = num_loans

    print(f'\nStarting number of loans: {num_loans}\n',flush=True)

    # Filter out loans that are not observed until over a year post-origination
    first_obs = loans.drop_duplicates(subset=['masterloanidtrepp'],keep='first')
    first_obs = first_obs[(first_obs['distdate'] - first_obs['origdate']).dt.days <= 720]
    loans = loans[loans['masterloanidtrepp'].isin(first_obs['masterloanidtrepp'])]
    num_loans = len(loans['masterloanidtrepp'].unique())

    print(f'1) Dropped loans not observed until >720 days post-origination. Number of loans remaining: {num_loans}',flush=True)

    # Filter out loans that are known to be delinquent when first observed
    non_delinq_mask = (first_obs['dlqderivedcd'].isna())|(first_obs['dlqderivedcd'].isin(['0','A','B']))
    first_obs = first_obs[non_delinq_mask]
    loans = loans[loans['masterloanidtrepp'].isin(first_obs['masterloanidtrepp'])]
    num_loans = len(loans['masterloanidtrepp'].unique())

    print(f'2) Dropped loans known to be delinquent when first observed. Number of loans remaining: {num_loans}',flush=True)

    # Filter out multi-property loans
    first_obs = first_obs[first_obs['numprop']==1]
    loans = loans[loans['masterloanidtrepp'].isin(first_obs['masterloanidtrepp'])]
    num_loans = len(loans['masterloanidtrepp'].unique())

    print(f'3) Dropped multi-property loans. Number of loans remaining: {num_loans}',flush=True)
    
    # Filter out multi-note loans
    m1 = (first_obs['numnotes']>1)&(~first_obs['numnotes'].isna())
    m2 = (~first_obs['acrossdealsloanidtrepp'].isna())
    m3 = (~first_obs['loanindeals'].isna())
    multi_note_mask = (m1|m2|m3)
    first_obs = first_obs[~multi_note_mask]
    loans = loans[loans['masterloanidtrepp'].isin(first_obs['masterloanidtrepp'])]
    num_loans = len(loans['masterloanidtrepp'].unique())

    print(f'4) Dropped multi-note loans. Number of loans remaining: {num_loans}',flush=True)

    # Reset index
    loans = loans.reset_index(drop=True)

    print(f'\nEnding number of loans: {num_loans} ({100*num_loans/starting_num_loans:.2f}%)\n',flush=True)

    return loans

### *** GET LIST OF CMBS DEALS TO INCLUDE *** ###

# Public offerings of CMBS conduit deals from the 2000-2025 period
# (excludes privately-placed securities, SASB, and other less-common deal types)
conduit_deals_path = '/proj/characklab/projects/kieranf/CMBS/data/Trepp/CIK_matching/public_2000-2025_conduit_CMBS_deals.parquet'
conduit_deals = pd.read_parquet(conduit_deals_path)

# Public offerings of Agency CMBS and from the 2000-2025 period
# (excludes privately-placed securities)
agency_deals_path = '/proj/characklab/projects/kieranf/CMBS/data/Trepp/CIK_matching/public_2000-2025_agency_CMBS_deals.parquet'
agency_deals = pd.read_parquet(agency_deals_path)

# Get deal IDs
conduit_dealnames = conduit_deals['DealName'].tolist()
agency_dealnames = agency_deals['DealName'].tolist()
included_dealnames = conduit_dealnames + agency_dealnames

### *** GET LOANS *** ###

# Get basic loan info
loan_dir = '/proj/characklab/projects/kieranf/CMBS/data/Trepp/raw_parquet/loan'
loan_filepaths = [os.path.join(loan_dir,x) for x in np.sort(os.listdir(loan_dir))]

filters = [('dosname','in',included_dealnames)]
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

loan2_dir = '/proj/characklab/projects/kieranf/CMBS/data/Trepp/raw_parquet/loan2'
loan2_filepaths = [os.path.join(loan2_dir,x) for x in np.sort(os.listdir(loan2_dir))]
loan2 = pd.read_parquet(loan2_filepaths,filters=filters,columns=usecols)

# Merge data
loans = pd.merge(loans,loan2,how='left',on=['dosname','masterloanidtrepp','distdate'])

# Break into conduit and agency
conduit_loans = loans[loans['dosname'].isin(conduit_dealnames)]
agency_loans = loans[loans['dosname'].isin(agency_dealnames)]

### *** FILTER LOANS BASED ON INCLUSION CRITERIA *** ###

# Conduit CMBS deals
print('\n#--- Conduit CMBS deals ---#\n')
conduit_loans = filter_loans(conduit_loans)

# Agency CMBS deals
print('\n#--- Agency CMBS deals ---#\n')
agency_loans = filter_loans(agency_loans)

### *** SAVE RESULTS *** ###

# Conduit loans
pwd = os.getcwd()
outname = os.path.join(pwd,'filtered_conduit_loans.parquet')
conduit_loans.to_parquet(outname)

# Agency loans
pwd = os.getcwd()
outname = os.path.join(pwd,'filtered_agency_loans.parquet')
agency_loans.to_parquet(outname)

