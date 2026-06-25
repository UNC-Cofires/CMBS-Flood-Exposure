import numpy as np
import pandas as pd
import geopandas as gpd
import pickle
import os
from src.utils.config import find_project_root, load_config

### *** HELPER FUNCTIONS *** ###

def join_points_to_polygons(points,polygons,max_dist=100):
    
    """
    Helper function to spatially join points to polygons. 
    Starts by using within predicate to speed things up, then does sjoin_nearest for 
    any remaining unmatched points that fall within distance threshold of polygon. 
    """
    
    df1 = points.sjoin(polygons,how='left',predicate='within')
    matched_mask = ~df1['index_right'].isna()
    df1 = df1.drop(columns=['index_right'])
    df1 = df1[matched_mask]
    
    df2 = points[~matched_mask].sjoin_nearest(polygons,how='left',max_distance=max_dist).drop(columns=['index_right'])
    df3 = pd.concat([df1,df2])
    return(df3)

def join_points_to_overlapping_polygons(left,right,id_col):

    """
    Helper function to spatially join points to overlapping polygons. Overlaps commonly occur 
    with national flood hazard layer (NFHL) data. These are mostly benign
    (e.g., a map panel that straddles two counties and is included twice). 
    To maintain the correct number of rows, attributes from overlapping polygons will be aggregated into lists

    param: left: points gdf
    param: right: polygon gdf (may contain overlaps)
    param: id_col: column in points gdf that uniquely identifies each row. 
    """

    df = left[[id_col,'geometry']].copy()
    df = df.sjoin(right,how='left',predicate='within').drop(columns=['index_right'])
    df = df.groupby(id_col).agg(list)
    df.drop(columns='geometry',inplace=True)

    return(pd.merge(left,df,on=id_col,how='left'))

def join_polygons_to_overlapping_polygons(left,right,id_col):

    """
    Helper function to spatially join polygons to overlapping polygons. Overlaps commonly occur 
    with national flood hazard layer (NFHL) data. These are mostly benign
    (e.g., a map panel that straddles two counties and is included twice). 
    To maintain the correct number of rows, attributes from overlapping polygons will be aggregated into lists

    This is also helpful for catching when you have a building whose footprint is partially
    inside the SFHA. 

    param: left: polygon gdf (no overlaps)
    param: right: polygon gdf (may contain overlaps)
    param: id_col: column in polygons gdf that uniquely identifies each row. 
    """

    df = left[[id_col,'polygon_geometry']].copy()
    df = df.sjoin(right,how='left',predicate='intersects').drop(columns=['index_right'])
    df = df.groupby(id_col).agg(list)
    df.drop(columns='polygon_geometry',inplace=True)

    return(pd.merge(left,df,on=id_col,how='left'))

def clean_nan_string_list_values(x):
    """
    If a string representation of a list contains only missing values, return pd.NA
    """
    v = x

    if not pd.isna(x):
        if x in ['[nan]','[NA]','[<NA>]','[]']:
            v = pd.NA

    return v

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
outfolder = os.path.join(pwd,'structure_info',state)
if not os.path.exists(outfolder):
    os.makedirs(outfolder,exist_ok=True)

### *** LOAD DATA *** ###

## State and county boundaries
counties_2022 = gpd.read_file(config['paths']['counties_2022'])
counties_2022 = counties_2022[counties_2022['STUSPS']==state].to_crs(proj_crs)
counties_2022['countyfips_2022'] = counties_2022['GEOID'].copy()

state_fips = counties_2022['STATEFP'].values[0]
state_area_gdf = counties_2022[['geometry']].dissolve()

counties_2010 = gpd.read_file(config['paths']['counties_2010'])
counties_2010 = counties_2010[counties_2010['STATE']==state_fips].to_crs(proj_crs)
counties_2010['countyfips_2010'] = counties_2010['STATE'] + counties_2010['COUNTY']

# Create a buffered version of the state area that we'll use for filtering
buffer_dist = 5000
buffered_state_area_gdf = state_area_gdf.copy()
buffered_state_area_gdf['geometry'] = buffered_state_area_gdf['geometry'].buffer(buffer_dist)
buffered_state_area_proj_mask = buffered_state_area_gdf['geometry'].values[0]
buffered_state_area_geog_mask = buffered_state_area_gdf['geometry'].to_crs(geog_crs).values[0]

## USA structures dataset
buildings_path = f'{config['paths']['usa_structures_dir']}/{state}/{state}_Structures.gdb'
usecols = ['BUILD_ID','LATITUDE','LONGITUDE','HEIGHT','SQMETERS','OCC_CLS','PROP_ZIP']
buildings = gpd.read_file(buildings_path,layer=f'{state}_Structures',columns=usecols).to_crs(proj_crs)
buildings.rename(columns={'geometry':'polygon_geometry'},inplace=True)
buildings['geometry'] = buildings['polygon_geometry'].centroid
buildings.set_geometry('geometry',inplace=True)
buildings['state'] = state

# USA structures building ID is only unique within a given state. 
# To make unique across nation, append the state abbreviation to the ID. 
buildings['BUILD_ID'] = f'{state}_' + buildings['BUILD_ID'].astype('string[pyarrow]')

## census block groups
blockgroups_2000 = gpd.read_file(config['paths']['censusblockgroups_2000']).to_crs(geog_crs).rename(columns={'GEOID':'censusblockgroup_2000'})
blockgroups_2010 = gpd.read_file(config['paths']['censusblockgroups_2010']).to_crs(geog_crs).rename(columns={'GEOID':'censusblockgroup_2010'})
blockgroups_2020 = gpd.read_file(config['paths']['censusblockgroups_2020']).to_crs(geog_crs).rename(columns={'GEOID':'censusblockgroup_2020'})

blockgroups_2000 = blockgroups_2000[blockgroups_2000.intersects(buffered_state_area_geog_mask)].to_crs(proj_crs)
blockgroups_2010 = blockgroups_2010[blockgroups_2010.intersects(buffered_state_area_geog_mask)].to_crs(proj_crs)
blockgroups_2020 = blockgroups_2020[blockgroups_2020.intersects(buffered_state_area_geog_mask)].to_crs(proj_crs)

## Zip code tabulation areas (ZCTAs)
ZCTA_path = '/proj/characklab/projects/kieranf/flood_damage_index/data/geospatial_data/census_ZCTAs/tl_2020_us_zcta520'
ZCTAs = gpd.read_file(ZCTA_path).to_crs(geog_crs).rename(columns={'GEOID20':'zcta_2020'})[['zcta_2020','geometry']]
ZCTAs = ZCTAs[ZCTAs.intersects(buffered_state_area_geog_mask)].to_crs(proj_crs)

## National Flood Hazard Layer (NFHL)

# Flood zone attributes
NFHL_info_path = f'{config['paths']['nfhl_dir']}/{state}/{state}_FLD_HAZ_AR.parquet'
NFHL_info = pd.read_parquet(NFHL_info_path)

# Flood zone geometries
NFHL_geom_path = f'{config['paths']['nfhl_dir']}/{state}/{state}_FLD_HAZ_AR_geometry.pickle'
with open(NFHL_geom_path,'rb') as f:
    NFHL_geom = pickle.load(f)
    
NFHL_geom = NFHL_geom.to_crs(proj_crs)
NFHL = NFHL_geom.merge(NFHL_info,how='left',on='FLD_AR_ID')
NFHL_cols = ['FLD_ZONE','ZONE_SUBTY','SFHA_TF']
NFHL = NFHL[NFHL_cols + ['geometry']]

## Parcel boundaries

# Load parcels from landrecords.us nationwide dataset posted on kaggle
# (https://www.kaggle.com/datasets/landrecordsus/us-parcel-layer)
parcels_path = f'{config['paths']['parcels_dir']}/{state}/{state}_parcels.parquet'
parcel_cols = ['lrid']
parcels = gpd.read_parquet(parcels_path,columns=parcel_cols+['geometry']).to_crs(proj_crs)

# Calculate the shape index for each parcel: SI = Perimeter/(4*sqrt(Area))
# perfect square = 1.0, perfect circle = 0.886, complex shapes = >1.0
# Typically, ~95% of parcels have a SI of <1.5
SI = parcels['geometry'].length/(4*np.sqrt(parcels['geometry'].area))

# Exclude those with a shape index of >3.0
# (these mostly correspond to road networks and other "stringy" shapes)
parcels = parcels[SI <= 3.0]

### *** DATA JOINING *** ###

# Get starting number of buildings
print(f'Starting number of buildings: {len(buildings)}',flush=True)

# Spatially join 2010 counties to buildings
buildings = join_points_to_polygons(buildings,counties_2010[['countyfips_2010','geometry']],max_dist=500)

# Spatially join 2022 counties to buildings
buildings = join_points_to_polygons(buildings,counties_2022[['countyfips_2022','geometry']],max_dist=500)

# Spatially join 2000 block groups to buildings
buildings = join_points_to_polygons(buildings,blockgroups_2000,max_dist=500)

# Spatially join 2010 block groups to buildings
buildings = join_points_to_polygons(buildings,blockgroups_2010,max_dist=500)

# Spatially join 2020 block groups to buildings
buildings = join_points_to_polygons(buildings,blockgroups_2020,max_dist=500)

# Spatially join 2020 ZCTAs to buildings
buildings = join_points_to_polygons(buildings,ZCTAs,max_dist=500)

# Spatially join parcel ids to buildings.
# Sometimes parcels overlap, so may return multiple.
# Also, some areas are missing data, so may return NA.
buildings = join_points_to_overlapping_polygons(buildings,parcels,'BUILD_ID')

# Spatially join FEMA flood zone to buildings
# Sometimes flood zone polygons overlap, so may return multiple.
# Also, not all areas are mapped, so may return NA.

# Use building footprint (polygon) instead of centroid (point) when 
# checking for intersections with flood zones. This ensures that a 
# building will be classified as inside the SFHA if any part of the
# structure touches the SFHA polygon. 
buildings.set_geometry('polygon_geometry',crs=proj_crs,inplace=True)
buildings = join_polygons_to_overlapping_polygons(buildings,NFHL,'BUILD_ID')

# Get ending number of buildings (should be same as start)
print(f'Ending number of buildings: {len(buildings)}',flush=True)

### *** DATA CLEANING / FORMATTING *** ###

# Create "cleaned" versions of columns with multiple potential values per building. 
# This can occur due to spatial joins to overlapping polygons.
# We'll append "_values" to the end of the column name to denote this. 

for col in parcel_cols + NFHL_cols:
    buildings.rename(columns={col:f'{col}_values'},inplace=True)

# Create binary variables denoting whether a building is located inside the FEMA 100-year floodplain (a.k.a. SFHA)
# or outside the FEMA 100-year floodplain but inside the FEMA 500-year floodplain.
# Because the NFHL can contain overlapping geometries, we'll consider a property to be inside the floodplain if 
# it touches any NFHL polygon classified as part of the SFHA. This approach errs on the side of assuming that the 
# SFHA is as large as theoretically possible. 
buildings['FEMA_100y_floodplain_indicator'] = buildings['SFHA_TF_values'].apply(lambda x: int('T' in x))
buildings['FEMA_500y_floodplain_indicator'] = buildings['ZONE_SUBTY_values'].apply(lambda x: int('0.2 PCT ANNUAL CHANCE FLOOD HAZARD' in x))
buildings['FEMA_500y_floodplain_indicator'] = buildings['FEMA_500y_floodplain_indicator']*(1-buildings['FEMA_100y_floodplain_indicator'])

# Convert to pyarrow dtypes
string_cols = buildings.dtypes[buildings.dtypes=='object'].index.values
for col in string_cols:
    buildings[col] = buildings[col].astype('string[pyarrow]')

# Clean NAN values in string representation of lists
for col in parcel_cols + NFHL_cols:
    buildings[f'{col}_values'] = buildings[f'{col}_values'].apply(clean_nan_string_list_values)

# Convert geometries to geographic CRS
buildings.rename(columns={'geometry':'point_geometry'},inplace=True)
buildings['point_geometry'] = buildings['point_geometry'].to_crs(geog_crs)
buildings['polygon_geometry'] = buildings['polygon_geometry'].to_crs(geog_crs)

# Reorder columns so geometries appear last
geometry_cols = ['point_geometry','polygon_geometry']
attribute_cols = [x for x in buildings.columns if x not in geometry_cols]
buildings = buildings[attribute_cols + geometry_cols]

### *** SAVE RESULTS *** ###

# Save as GeoParquet
outname = os.path.join(outfolder,f'{state}_structure_info.parquet')
buildings.to_parquet(outname)