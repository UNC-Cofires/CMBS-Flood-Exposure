import numpy as np
import pandas as pd
import os
from src.utils.config import find_project_root, load_config

### *** HELPER FUNCTIONS *** ###

def match_deals(freddie_deal,trepp_deals,date_tolerance=1,balance_tolerance=10e6):
    """
    param: freddie_deal: row of pandas dataframe describing attributes of freddie mac deal 
                         downloaded from MISA portal
    param: trepp_deals: pandas dataframe of candidate deals included in Trepp database
    returns: trepp_dealname: unique identifier of deal in trepp database
    """

    trepp_dealname = pd.NA

    deal_name = freddie_deal['Deal Name']
    closing_date = pd.Timestamp(freddie_deal['Deal Closing Dt'])
    orig_balance = freddie_deal['Orig Balance']
        
    name_match = (trepp_deals['bloombergName']==deal_name)
    date_match = np.abs((trepp_deals['ClosingDate'] - closing_date).dt.days) <= date_tolerance
    balance_match = np.abs(trepp_deals['CutoffBalance'] - orig_balance) <= balance_tolerance

    # First try for exact match based on deal name
    if np.sum(name_match)==1:
        trepp_dealname = trepp_deals[name_match]['DealName'].iloc[0]
    # If that fails, attempt to match based on closing date and cutoff balance
    elif np.sum(date_match&balance_match)==1:
        trepp_dealname = trepp_deals[date_match&balance_match]['DealName'].iloc[0]

    return(trepp_dealname)

### *** INITIAL SETUP *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

### *** MATCH DEALS *** ###

# Search results from Freddie Mac's MISA portal
freddie_deals = pd.read_parquet(config['paths']['misa_search_results_deal_info'])

# CMBS deals included in Trepp database
trepp_deal_dir = os.path.join(config['paths']['trepp_data_dir'],'deal')
trepp_deal_filepaths = [os.path.join(trepp_deal_dir,x) for x in np.sort(os.listdir(trepp_deal_dir))]

usecols = ['DealName',
           'bloombergName',
           'DealType',
           'PrivType',
           'ClosingDate',
           'LeadUnderwriter',
           'Trustee',
           'MasterServicer',
           'SpecialServicer',
           'CutoffBalance',
           'CutoffAssetCount']

# Get unique listing of deals
trepp_deals = pd.read_parquet(trepp_deal_filepaths,columns=usecols).drop_duplicates(subset=['DealName'],keep='last')

# Filter for Agency CMBS
trepp_deals = trepp_deals[trepp_deals['DealType']=='Agency CMBS']

# For each Freddie Mac deal, check for a match in the Trepp Database
freddie_deals['TreppDealName'] = freddie_deals.apply(lambda x: match_deals(x,trepp_deals),axis=1)

original_num_deals = len(freddie_deals)
num_matched_deals = (~freddie_deals['TreppDealName'].isna()).sum()

freddie_deals = freddie_deals.dropna(subset='TreppDealName').reset_index(drop=True)
trepp_deals = trepp_deals[trepp_deals['DealName'].isin(freddie_deals['TreppDealName'])].reset_index(drop=True)

### *** MATCH LOANS *** ###

# Get Annex A-1 info from Freddie Mac MISA portal
annex_a1 = pd.read_parquet(config['paths']['misa_search_results_annex_a1'])

# Attach deal info
annex_a1 = pd.merge(freddie_deals[['Short Deal Name','Deal Name','TreppDealName']],annex_a1,on='Short Deal Name',how='right')

# Drop unmatched observations
annex_a1 = annex_a1.dropna(subset='TreppDealName')

# Get rows corresponding to loan info (as opposed to collateral info for multi-property loans)
annex_a1 = annex_a1[annex_a1['Row Type']=='A1 Loan'].reset_index(drop=True)

# Get loan info from Trepp Database
loan_dir = os.path.join(config['paths']['trepp_data_dir'],'loan')
loan_filepaths = [os.path.join(loan_dir,x) for x in np.sort(os.listdir(loan_dir))]

usecols = ['dosname','masterloanidtrepp','collateralid','origloanbal','oterm','maturitydate']

filters = [('dosname','in',freddie_deals['TreppDealName'].tolist())]
loans = pd.read_parquet(loan_filepaths,filters=filters,columns=usecols)

# Only interested in origination characteristics, so drop longitudinal observations
loans = loans.groupby('masterloanidtrepp').last().reset_index()

# Attempt to merge on deal name and prospectus loan id
matched_loans = pd.merge(loans,
                         annex_a1,
                         left_on=['dosname','collateralid'],
                         right_on=['TreppDealName','Prospectus Loan Id'],
                         how='right')

# Remove loans that fail to match or whose original balance and maturity dates disagree
m1 = matched_loans['masterloanidtrepp'].isna()
m2 = matched_loans['masterloanidtrepp'].duplicated(keep=False)
m3 = np.abs(matched_loans['origloanbal'] - matched_loans['Original Loan Amount']) > 100
m4 = np.abs((matched_loans['maturitydate'] - pd.to_datetime(matched_loans['Maturity Date'])).dt.days) > 1
invalid_mask = (m1|m2|m3|m4)

matched_loans = matched_loans[~invalid_mask].reset_index(drop=True)
matched_loans = matched_loans.drop(columns=['collateralid','origloanbal','oterm','maturitydate','TreppDealName'])

### *** PRINT UPDATE FOR USER *** ###

original_num_loans = len(loans['masterloanidtrepp'].unique())
num_matched_loans = len(matched_loans['masterloanidtrepp'].unique())

perc_match_deal = 100*num_matched_deals/original_num_deals
perc_match_loan = 100*num_matched_loans/original_num_loans

print(f'Matched {num_matched_deals} / {original_num_deals} ({perc_match_deal:.2f}%) Deals.')
print(f'Matched {num_matched_loans} / {original_num_loans} ({perc_match_loan:.2f}%) Loans.')

### *** SAVE RESULTS *** ###

matched_loans.to_parquet('matched_freddie_trepp_loans_annex_a1.parquet')
freddie_deals.to_parquet('matched_freddie_trepp_deals.parquet')