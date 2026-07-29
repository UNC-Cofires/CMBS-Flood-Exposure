import numpy as np
import pandas as pd
import geopandas as gpd
import os
from src.utils.config import find_project_root, load_config

### *** HELPER FUCNTIONS *** ###

def process_parcel_ids(x):
    """
    This function converts a string representation of a list of parcel_ids matched to buildings
    (e.g., "['p100','p101']") to an actual list (e.g., ['p100','p101']). Next, it checks whether
    this list is single-valued. If it contains multiple values, the parcel associated with a 
    building is ambiguous and will be set to NA. 
    """

    if pd.isna(x):
        parcel_id = pd.NA
    else:
        parcel_id_list = x.strip("[]'").split(',')
        if len(parcel_id_list) != 1:
            parcel_id = pd.NA
        else:
            parcel_id = parcel_id_list[0]

    return parcel_id

### *** INITIAL SETUP *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

# Get current working directory
pwd = os.getcwd()

# Get state of interest
state_idx = int(os.environ['SLURM_ARRAY_TASK_ID'])
state_list = np.loadtxt(config['paths']['included_states'],dtype=str)
state = state_list[state_idx]

# Get geographic CRS
geog_crs = config['gis_params']['geographic_crs']

# Determine appropriate projected CRS for state
if state not in ['AK','HI']:
    proj_crs = config['gis_params']['conus_projected_crs']
elif state == 'AK':
    proj_crs = config['gis_params']['ak_projected_crs']
else:
    proj_crs = config['gis_params']['hi_projected_crs']

print(f'State: {state}\nGeographic CRS: {geog_crs}\nProjected CRS: {proj_crs}')

# Create folder for output
output_dir = os.path.join(pwd,f'property_geospatial_data')
os.makedirs(output_dir,exist_ok=True)

### *** LOAD DATA *** ###

# Geocoded address points
address_data_path = os.path.join(pwd,f'geocoding_output/within_tolerance/here_api/{state}_addresses_within_tolerance_here_api.parquet')
address_data = gpd.read_parquet(address_data_path).to_crs(geog_crs)

# Building footprints
buildings_path = os.path.join(pwd,f'structure_info/{state}/{state}_structure_info.parquet')
buildings = gpd.read_parquet(buildings_path).to_crs(geog_crs)
buildings['lrid_values'] = buildings['lrid_values'].apply(process_parcel_ids)
buildings.rename(columns={'lrid_values':'lrid'},inplace=True)
matched_parcel_ids = buildings[buildings['BUILD_ID'].isin(address_data['BUILD_ID'])]['lrid'].dropna().tolist()
buildings.set_index('BUILD_ID',inplace=True)

# Land parcels
parcels_dir = config['paths']['parcels_dir']
parcels_path = os.path.join(parcels_dir,f'{state}/{state}_parcels.parquet')
filters = [('lrid','in',matched_parcel_ids)]
parcels = gpd.read_parquet(parcels_path,columns=['lrid','geometry'],filters=filters).to_crs(geog_crs)
parcels.set_index('lrid',inplace=True)

### *** MATCH LOANS TO BUILDINGS AND PARCELS *** ##

agg_dict = {'propname':'first',
            'address':'first',
            'city':'first',
            'state':'first',
            'zip':'first',
            'BUILD_ID': lambda x: list(np.unique(x))}

loan_data = address_data.groupby('masterloanidtrepp').agg(agg_dict)
loan_data.rename(columns={'BUILD_ID':'direct_match_building_ids'},inplace=True)
loan_data['indirect_match_building_ids'] = pd.NA
loan_data['building_ids'] = pd.NA
loan_data['parcel_ids'] = pd.NA

for loan_id in loan_data.index.values:

    # Get parcels associated with direct building matches
    direct_match_building_ids = loan_data.at[loan_id,'direct_match_building_ids']
    parcel_ids = buildings.loc[direct_match_building_ids]['lrid'].dropna().drop_duplicates().tolist()

    # Get additional buildings on these parcels (indirect building matches) 
    building_ids = buildings[buildings['lrid'].isin(parcel_ids)].index.tolist()
    indirect_match_building_ids = [x for x in building_ids if x not in direct_match_building_ids]

    # Record information in loan-level data
    loan_data.at[loan_id,'indirect_match_building_ids'] = indirect_match_building_ids
    loan_data.at[loan_id,'building_ids'] = building_ids
    loan_data.at[loan_id,'parcel_ids'] = parcel_ids

### *** GET BUILDINGS AND PARCELS ASSOCIATED WITH LOANS *** ###

# Reset indices so that we can use unique identifiers for merge operations
loan_data.reset_index(inplace=True)
buildings.reset_index(inplace=True)
parcels.reset_index(inplace=True)

# Get direct building matches
direct_match_buildings = loan_data[['masterloanidtrepp','direct_match_building_ids']].explode('direct_match_building_ids')
direct_match_buildings.rename(columns={'direct_match_building_ids':'BUILD_ID'},inplace=True)
direct_match_buildings['direct_match'] = 1
direct_match_buildings = pd.merge(buildings,direct_match_buildings,on='BUILD_ID',how='right')
direct_match_buildings = direct_match_buildings[['masterloanidtrepp','direct_match']+list(buildings.columns)]

# Get indirect building matches
indirect_match_buildings = loan_data[['masterloanidtrepp','indirect_match_building_ids']].explode('indirect_match_building_ids')
indirect_match_buildings.rename(columns={'indirect_match_building_ids':'BUILD_ID'},inplace=True)
indirect_match_buildings.dropna(subset='BUILD_ID',inplace=True)
indirect_match_buildings['direct_match'] = 0
indirect_match_buildings = pd.merge(buildings,indirect_match_buildings,on='BUILD_ID',how='right')
indirect_match_buildings = indirect_match_buildings[['masterloanidtrepp','direct_match']+list(buildings.columns)]

# Combine direct and indirect building matches into single geodataframe
match_buildings = pd.concat([direct_match_buildings,indirect_match_buildings]).sort_values(by='masterloanidtrepp').reset_index(drop=True)

# Get parcel matches
match_parcels = loan_data[['masterloanidtrepp','parcel_ids']].explode('parcel_ids')
match_parcels.rename(columns={'parcel_ids':'lrid'},inplace=True)
match_parcels.dropna(subset='lrid',inplace=True)
match_parcels = pd.merge(parcels,match_parcels,on='lrid',how='right')
match_parcels = match_parcels[['masterloanidtrepp']+list(parcels.columns)]

### *** SAVE RESULTS *** ###

# Matching information
subfolder = os.path.join(output_dir,'match_info')
os.makedirs(subfolder,exist_ok=True)
outname = os.path.join(subfolder,f'{state}_match_info.parquet')
loan_data.to_parquet(outname)

# Matched buildings
subfolder = os.path.join(output_dir,'matched_buildings')
os.makedirs(subfolder,exist_ok=True)
outname = os.path.join(subfolder,f'{state}_matched_buildings.parquet')
match_buildings.to_parquet(outname)

# Matched parcels
subfolder = os.path.join(output_dir,'matched_parcels')
os.makedirs(subfolder,exist_ok=True)
outname = os.path.join(subfolder,f'{state}_matched_parcels.parquet')
match_parcels.to_parquet(outname)