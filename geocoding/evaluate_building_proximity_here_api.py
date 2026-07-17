import numpy as np
import pandas as pd
import geopandas as gpd
import os
from src.utils.config import find_project_root, load_config

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

# Create folders for output
geocoding_dir = os.path.join(pwd,'geocoding_output')
within_tolerance_dir = os.path.join(geocoding_dir,'within_tolerance/here_api')
outside_tolerance_dir = os.path.join(geocoding_dir,'outside_tolerance/here_api')
os.makedirs(within_tolerance_dir,exist_ok=True)
os.makedirs(outside_tolerance_dir,exist_ok=True)

### *** LOAD DATA *** ###

# Results of geocoding address data using HERE API
address_data_path = os.path.join(geocoding_dir,'geocoding_output_here_api.parquet')
filters=[('state','=',state)]
address_data = pd.read_parquet(address_data_path,filters=filters)

# Buildings
buildings_path = os.path.join(pwd,f'structure_info/{state}/{state}_structure_info.parquet')
buildings = gpd.read_parquet(buildings_path,columns=['BUILD_ID','polygon_geometry'])
buildings = buildings.set_geometry('polygon_geometry').to_crs(proj_crs)

### *** EVALUATE PROXIMITY OF GEOCODED ADDRESSES TO BUILDINGS *** ###

# Get addresses that were matched to a precise location (i.e., not those that are geocoded to a street or approximate location)
precise_match_mask = (address_data['resultType']=='houseNumber')&(address_data['houseNumberFallback']==False)
keepcols = ['masterloanidtrepp','propname','address','city','state','zip','parsed_address','query_string']
imprecise_geocodes = address_data[~precise_match_mask][keepcols]
address_data = address_data[precise_match_mask]
address_data = gpd.GeoDataFrame(address_data, geometry=gpd.points_from_xy(address_data['geocodedLongitude'], address_data['geocodedLatitude'],crs=geog_crs))
address_data = address_data[keepcols + ['geometry']].to_crs(proj_crs)

# Join to nearest building within 30-meter cutoff
cutoff=30
address_data = gpd.sjoin_nearest(address_data,buildings,how='left',max_distance=cutoff,distance_col='distance_to_building_m').drop(columns='index_right')

# Break out entries that to not match to a building within this cutoff
# (We'll attempt to re-geocode these using Google's API)
exceed_cutoff_mask = address_data['distance_to_building_m'].isna()
exceed_cutoff_data = address_data[exceed_cutoff_mask][keepcols]
address_data = address_data[~exceed_cutoff_mask].reset_index(drop=True).to_crs(geog_crs)
outside_tolerance_data = pd.concat([imprecise_geocodes,exceed_cutoff_data]).reset_index(drop=True)

### *** SAVE RESULTS *** ###

# Addresses within 30 meters of a building
outname = os.path.join(within_tolerance_dir,f'{state}_addresses_within_tolerance_here_api.parquet')
address_data.to_parquet(outname)

# Addresses >30 meters from a building (will be re-geocoded)
outname = os.path.join(outside_tolerance_dir,f'{state}_addresses_outside_tolerance_here_api.parquet')
outside_tolerance_data.to_parquet(outname)

# Print results to console
num_within = len(address_data)
num_outside = len(outside_tolerance_data)
percent_within = 100*num_within/(num_within+num_outside)

print(f'\nNumber of addresses within {cutoff:.0f}-meter distance-to-building tolerance: {num_within} / {num_within + num_outside} ({percent_within:.2f}%)',flush=True)