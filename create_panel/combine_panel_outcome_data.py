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

### *** LOAD DATA *** ###

## Private-label CMBS conduit loans
conduit_path = os.path.join(pwd,'panel_outcome_data_trepp.parquet')
conduit_loans = pd.read_parquet(conduit_path)

## Fannie Mae multifamily loans
fannie_path = os.path.join(project_root,'fannie_mae/create_panel/panel_outcome_data_fannie.parquet')
fannie_loans = pd.read_parquet(fannie_path)

## Freddie Mac multifamily loans
freddie_path = os.path.join(project_root,'freddie_mac/create_panel/panel_outcome_data_freddie.parquet')
freddie_loans = pd.read_parquet(freddie_path)

### *** FILTER DATA *** ###

rename_dict = {'masterloanidtrepp':'loanid','masterpropidtrepp':'propid','cssaproptype':'proptype'}

## Private-label

# Make clear that loan/property identifiers are specific to Trepp database
conduit_loans.rename(columns=rename_dict,inplace=True)
conduit_loans['loanid'] = 'TREPP-' + conduit_loans['loanid']
conduit_loans['propid'] = 'TREPP-' + conduit_loans['propid']

# Restrict to multifamily, retail, and office properties
conduit_loans = conduit_loans[conduit_loans['proptype'].isin(['MF','RT','OF'])]

## Fannie

# Make clear that loan/property identifiers are specific to Fannie Mae database
fannie_loans['loanid'] = 'FNMA-' + fannie_loans['loanid']
fannie_loans['propid'] = 'FNMA-' + fannie_loans['propid']

# Restrict to multifamily properties and denote agency loan status
fannie_loans = fannie_loans[fannie_loans['proptype']=='Multifamily']
fannie_loans['proptype']='GSE-MF'

## Freddie

# Make clear that loan/property identifiers are specific to Trepp database
freddie_loans.rename(columns=rename_dict,inplace=True)
freddie_loans['loanid'] = 'TREPP-' + freddie_loans['loanid']
freddie_loans['propid'] = 'TREPP-' + freddie_loans['propid']

# Restrict to multifamily properties and denote agency loan status
freddie_loans = freddie_loans[freddie_loans['proptype']=='MF']
freddie_loans['proptype']='GSE-MF'

### *** COMBINE DATA *** ###

panel = pd.concat([conduit_loans,freddie_loans,fannie_loans]).reset_index(drop=True)

# Clean data types
date_cols = list(panel.columns[panel.dtypes == 'timestamp[ns][pyarrow]'])
object_cols = list(panel.columns[panel.dtypes == 'object'])

for col in date_cols:
    panel[col] = panel[col].astype('date32[day][pyarrow]')

for col in object_cols:
    panel[col] = panel[col].astype('string[pyarrow]')

# Save to file
outname = os.path.join(pwd,'panel_outcome_data_combined.parquet')
panel.to_parquet(outname)

### *** PRINT SUMMARY FOR USER *** ###

num_loans = len(panel['loanid'].unique())
num_loan_years = len(panel)

print(f'Number of loans in panel: {num_loans}')
print(f'Number of loan-years in panel: {num_loan_years}\n')

print('Distribution of property types:')

for proptype in panel['proptype'].value_counts().index.values:

    mask = (panel['proptype']==proptype)
    proptype_num_loans = len(panel[mask]['loanid'].unique())
    proptype_num_loan_years = len(panel[mask])
    proptype_loan_pct = 100*(proptype_num_loans/num_loans)
    proptype_loan_year_pct = 100*(proptype_num_loan_years/num_loan_years)

    print(f'    {proptype}: {proptype_num_loans} loans ({proptype_loan_pct:.1f}%), {proptype_num_loan_years} loan-years ({proptype_loan_year_pct:.1f}%)')

print('\nPopulation rate of key fields:')

fields = ['zero_balance_flag',
          'modification_flag',
          'D60',
          'D90',
          'in_foreclosure_or_REO',
          'ever_D60',
          'ever_D90',
          'ever_in_foreclosure_or_REO',
          'realizedloss',
          'loss_rate',
          'rev',
          'exp',
          'noi',
          'occ']

for field in fields:
    pop_rate = (~panel[field].isna()).mean()
    print(f'    {field}: {100*pop_rate:.1f}%')