import numpy as np
import pandas as pd
import os
from src.utils.config import find_project_root, load_config

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

# Get current working directory 
pwd = os.getcwd()

# Create folder for address list
outfolder = os.path.join(pwd,'geocoding_input')
os.makedirs(outfolder,exist_ok=True)

# Loan-level data to geocode
loan_path = os.path.join(project_root,'create_panel/filtered_loans.parquet')
usecols = ['masterloanidtrepp','propname','address','city','state','zip']
loans = pd.read_parquet(loan_path,columns=usecols)

# Drop redundant rows so we have one row per loan
loans = loans.groupby('masterloanidtrepp').last().reset_index()

# Save results
outname = os.path.join(outfolder,'filtered_loans_address_data.parquet')
loans.to_parquet(outname)