import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import os
from src.utils.config import find_project_root, load_config

### *** HELPER FUNCTIONS *** ###

def group_county(county):
    """
    This function determines whether a county is a member of a core-based statistical area (CBSA)
    as defined by the U.S. Census Bureau. Counties are grouped together based on the following rules: 

    1. Counties that are members of a combined statistical area (CSAs) are grouped together. 
    2. Counties outside CSAs that are members of a metropolitan statistical area (MSA) or 
       micropolitan statistical area (μSA) are grouped together. 
    3. Counties outside CBSAs that are members of the same state are grouped together. 

    param: county: row of pandas dataframe describing the membership of a given county in CBSAs
    returns: county: modified row of pandas dataframe with additional fields describing
                     group_code, group_name, and group_type
    """
    
    group_code = pd.NA
    group_name = pd.NA
    group_type = pd.NA
    
    if not pd.isna(county['CSA Code']):
        group_code = county['CSA Code']
        group_name = county['CSA Title']
        group_type = 'CSA'
    elif not pd.isna(county['CBSA Code']):
        group_code = county['CBSA Code']
        group_name = county['CBSA Title']
    
        if county['Metropolitan/Micropolitan Statistical Area'] == 'Metropolitan Statistical Area':
            group_type = 'MSA outside CSA'
        else:
            group_type = 'μSA outside CSA'
    else:
        group_code = county['STATEFP']
        group_name = 'Non-CBSA counties in ' + county['STATE_NAME']
        group_type = 'area of state outside CBSA'

    county['group_code'] = group_code
    county['group_name'] = group_name
    county['group_type'] = group_type
    
    return county

### *** INITIAL SETUP *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

# Get current working directory 
pwd = os.getcwd()

# Create folder for output
outfolder = os.path.join(pwd,'metro_areas')
os.makedirs(outfolder,exist_ok=True)

### *** LOAD DATA *** ###

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

### *** DEFINE GEOGRAPHIC GROUPS USED FOR FIXED EFFECTS *** ###

metro_delineations = metro_delineations.apply(group_county,axis=1)
metro_delineations = metro_delineations[['GEOID','NAME','STUSPS','group_code','group_name','group_type','geometry']]

### *** SAVE RESULTS *** ###

outname = os.path.join(outfolder,'county_metro_area_groupings.parquet')
metro_delineations.to_parquet(outname)