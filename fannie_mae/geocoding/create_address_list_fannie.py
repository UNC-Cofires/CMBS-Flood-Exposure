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
loan_path = os.path.join(project_root,'fannie_mae/create_panel/filtered_loans_fannie.parquet')
usecols = ['Loan Number','Property Name','Property Address','Property City','Property State','Property Zip Code']
loans = pd.read_parquet(loan_path,columns=usecols)

# Rename columns
loans.columns = ['loan_number','propname','address','city','state','zip']

# Save results
outname = os.path.join(outfolder,'filtered_loans_address_data.parquet')
loans.to_parquet(outname)
