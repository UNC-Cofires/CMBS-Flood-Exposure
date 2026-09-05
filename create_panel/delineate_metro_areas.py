import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import os
from src.utils.config import find_project_root, load_config

### *** INITIAL SETUP *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

# Get current working directory 
pwd = os.getcwd()

# Create folder for output
outfolder = os.path.join(pwd,'metro_areas')
os.makedirs(outfolder,exist_ok=True)

### *** ATTACH CBSA / CSA INFORMATION TO COUNTIES *** ###

# Counties
included_states = np.loadtxt(config['paths']['included_states'],dtype=str)
counties = gpd.read_file(config['paths']['counties_2022'])
counties = counties[counties['STUSPS'].isin(included_states)]

# County membership in combined statistical areas (CSAs) and core-based statistical areas (CBSAs)
# CBSAs encompass both metropolitan statistical areas (MSAs) and micropolitan statistical areas (μSAs)
metro_delineations = pd.read_excel(config['paths']['csa_cbsa_delineations'],dtype='string[pyarrow]')
metro_delineations['GEOID'] = metro_delineations['FIPS State Code'] + metro_delineations['FIPS County Code']
metro_delineations = metro_delineations[metro_delineations['FIPS State Code'].isin(counties['STATEFP'])]

# Attach CSA / CBSA info to counties
metro_delineations = counties[['GEOID','NAME','STUSPS','STATE_NAME','STATEFP','geometry']].merge(metro_delineations,on='GEOID',how='left')

rename_dict = {'CSA Code':'csa_code',
               'CSA Title':'csa_title',
               'CBSA Code':'cbsa_code',
               'CBSA Title':'cbsa_title',
               'Metropolitan/Micropolitan Statistical Area':'cbsa_type'}

metro_delineations = metro_delineations.rename(columns=rename_dict)
metro_delineations = metro_delineations[['GEOID','NAME','STUSPS','csa_code','csa_title','cbsa_code','cbsa_title','cbsa_type','geometry']]

### *** SAVE RESULTS *** ###

outname = os.path.join(outfolder,'county_metro_area_groupings.parquet')
metro_delineations.to_parquet(outname)