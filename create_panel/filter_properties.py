import numpy as np
import pandas as pd
import os
import gc

# Get present working directory
pwd = os.getcwd()

# Get path to trepp property-level data files
prop_dir = '/proj/characklab/projects/kieranf/CMBS/data/Trepp/raw_parquet/prop'
prop_filepaths = [os.path.join(prop_dir,x) for x in np.sort(os.listdir(prop_dir))]

# Get IDs of loans that meet inclusion criteria
conduit_loan_path = os.path.join(pwd,'filtered_conduit_loans.parquet')
agency_loan_path = os.path.join(pwd,'filtered_agency_loans.parquet')
conduit_loan_ids = pd.read_parquet(conduit_loan_path,columns=['masterloanidtrepp'])['masterloanidtrepp'].unique().tolist()
agency_loan_ids = pd.read_parquet(agency_loan_path,columns=['masterloanidtrepp'])['masterloanidtrepp'].unique().tolist()

# Get IDs of properties associated with these loans
loan_prop_info = pd.read_parquet(prop_filepaths,columns=['masterloanidtrepp','masterpropidtrepp']).drop_duplicates()
conduit_loan_prop_info = loan_prop_info[loan_prop_info['masterloanidtrepp'].isin(conduit_loan_ids)]
agency_loan_prop_info = loan_prop_info[loan_prop_info['masterloanidtrepp'].isin(agency_loan_ids)]
conduit_prop_ids = conduit_loan_prop_info['masterpropidtrepp'].unique().tolist()
agency_prop_ids = agency_loan_prop_info['masterpropidtrepp'].unique().tolist()

# Concatenate data from included properties and save results

# Properties included in conduit CMBS deals
outname = os.path.join(pwd,'filtered_conduit_properties.parquet')
conduit_props = pd.read_parquet(prop_filepaths,filters=[('masterpropidtrepp','in',conduit_prop_ids)])
conduit_props.to_parquet(outname)
del conduit_props
gc.collect()

# Properties included in agency CMBS deals
outname = os.path.join(pwd,'filtered_agency_properties.parquet')
agency_props = pd.read_parquet(prop_filepaths,filters=[('masterpropidtrepp','in',agency_prop_ids)])
agency_props.to_parquet(outname)
del agency_props
gc.collect()