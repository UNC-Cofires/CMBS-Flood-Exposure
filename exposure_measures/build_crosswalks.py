import numpy as np
import pandas as pd
import os
from src.utils.config import find_project_root, load_config

### *** HELPER FUNCTIONS *** ###

def create_one_to_one_crosswalk(buildings,source_col='censusblockgroup_2020',target_col='censustract_2010'):
    """
    This function creates a one-to-one crosswalk between geographic identifiers in a manner that 
    seeks to maximize the number of buildings in each source geometry that intersect with their
    assigned target geometry. 
    
    For example, when mapping 2020 block groups onto 2010 tracts, this function will assign each
    block group to the tract which contains the most of that block group's buildings. In general,
    this process will work best when mapping smaller geometries (e.g., block groups) onto larger 
    geometries (e.g., tracts). Mapping large-to-large (e.g., 2020 tracts to 2010 tracts) will likely
    result in a higher proportion of buildings that are "lost" due to incomplete overlap between 
    source and target geometries. 

    param: buildings: pandas dataframe where each row represents a building. Must contain the following
                      columns: "BUILD_ID", <source_col>, and <target_col> where the latter two columns
                      record the location of each building in the source/target geometries.  
    param: source_col: column of the buildings dataframe corresponding to the source geometry. This should
                      ideally be something small like census blocks or block groups. 
    param: target_col: column of the buildings dataframe corresponding to the target geometry. This should
                      ideally be something larger like census tracts.
    param: crosswalk: pandas dataframe containing the assigned target geometry for each source geometry,
                      as well as information on the number of buildings that are preserved/lost due to the
                      one-to-one assignment constraint. 
    """

    # Get number of buildings in each source geometry
    source_building_count = buildings.groupby([source_col])[['BUILD_ID']].count().reset_index()
    source_building_count.rename(columns={'BUILD_ID':'source_building_count'},inplace=True)

    # Get number of buildings in each intersection of source/target geometries
    crosswalk = buildings.groupby([source_col,target_col])[['BUILD_ID']].count().reset_index()
    crosswalk.rename(columns={'BUILD_ID':'intersection_building_count'},inplace=True)
    crosswalk = pd.merge(crosswalk,source_building_count,on=source_col,how='left')

    # For each source geometry, select the target geometry that maximizes the
    # number of intersecting buildings.
    crosswalk = crosswalk.sort_values(by=[source_col,'intersection_building_count'],ascending=[True,False])
    crosswalk = crosswalk.groupby(source_col).first().reset_index()

    # Determine what share of buildings in the source geometry are located within
    # the selected target geometry.
    crosswalk['captured_building_share'] = crosswalk['intersection_building_count'] / crosswalk['source_building_count']

    # Create description and rearrange columns
    crosswalk['description'] = f'{source_col} --> {target_col}'

    column_order = [source_col,
                    target_col,
                    'description',
                    'source_building_count',
                    'intersection_building_count',
                    'captured_building_share']

    crosswalk = crosswalk[column_order]

    # Print update for user
    overall_captured_share = crosswalk['intersection_building_count'].sum() / crosswalk['source_building_count'].sum()
    print(f'{source_col} --> {target_col} : captures {100*overall_captured_share:.2f}% of buildings')

    return crosswalk

### *** INITIAL SETUP *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

# Get current working directory
pwd = os.getcwd()

# Create folder for output
outfolder = os.path.join(pwd,'crosswalks')
os.makedirs(outfolder,exist_ok=True)

### *** LOAD AND CLEAN DATA *** ###

# Read in USA structures data with census identifiers attached
states = np.loadtxt(config['paths']['included_states'],dtype=str)
buildings_dir = os.path.join(project_root,'geocoding/structure_info')
buildings_filepaths = [os.path.join(buildings_dir,f'{state}/{state}_structure_info.parquet') for state in states]
usecols = ['BUILD_ID','censusblockgroup_2000','censusblockgroup_2010','censusblockgroup_2020']
buildings = pd.read_parquet(buildings_filepaths,columns=usecols)

# Create census tract GEOID based on first 11 digits of block group GEOID
for year in [2000,2010,2020]:
    buildings[f'censustract_{year}'] = buildings[f'censusblockgroup_{year}'].map(lambda x: x[:11],na_action='ignore')

### *** CREATE ONE-TO-ONE CROSSWALKS *** ###

# 2020 block groups to 2010 tracts
bg2020_tr2010_crosswalk = create_one_to_one_crosswalk(buildings,'censusblockgroup_2020','censustract_2010')

# 2000 block groups to 2010 tracts
bg2000_tr2010_crosswalk = create_one_to_one_crosswalk(buildings,'censusblockgroup_2000','censustract_2010')

# 2010 block groups to 2020 tracts
bg2010_tr2020_crosswalk = create_one_to_one_crosswalk(buildings,'censusblockgroup_2010','censustract_2020')

# 2000 block groups to 2020 tracts
bg2000_tr2020_crosswalk = create_one_to_one_crosswalk(buildings,'censusblockgroup_2000','censustract_2020')

### *** SAVE RESULTS *** ###

# Save as parquet
outname = os.path.join(outfolder,'bg2020_tr2010_crosswalk.parquet')
bg2020_tr2010_crosswalk.to_parquet(outname)

outname = os.path.join(outfolder,'bg2000_tr2010_crosswalk.parquet')
bg2000_tr2010_crosswalk.to_parquet(outname)

outname = os.path.join(outfolder,'bg2010_tr2020_crosswalk.parquet')
bg2010_tr2020_crosswalk.to_parquet(outname)

outname = os.path.join(outfolder,'bg2000_tr2020_crosswalk.parquet')
bg2000_tr2020_crosswalk.to_parquet(outname)

# And as CSV
outname = os.path.join(outfolder,'bg2020_tr2010_crosswalk.csv')
bg2020_tr2010_crosswalk.to_csv(outname,index=False)

outname = os.path.join(outfolder,'bg2000_tr2010_crosswalk.csv')
bg2000_tr2010_crosswalk.to_csv(outname,index=False)

outname = os.path.join(outfolder,'bg2010_tr2020_crosswalk.csv')
bg2010_tr2020_crosswalk.to_csv(outname,index=False)

outname = os.path.join(outfolder,'bg2000_tr2020_crosswalk.csv')
bg2000_tr2020_crosswalk.to_csv(outname,index=False)