import numpy as np
import pandas as pd
import geopandas as gpd
import os
from itertools import product
from src.utils.config import find_project_root, load_config

### *** HELPER FUNCTIONS *** ###

def assign_census_vintage(df,date_col,geoid_col,v2000_geoids,v2010_geoids,v2020_geoids):
    """
    This function attempts to determine the census GEOID vintage of OpenFEMA records 
    that contain a census GEOID whose vintage is unspecified. This task is accomplished
    through the following steps: 

    1) For a given record year (e.g., policies with an effective date in 2015), the 
       match rate between OpenFEMA GEOIDs and census GEOIDs from different vintages
       is computed. 
    2) For each record year, census vintages (e.g., 2000, 2010, 2020) are ordered
       from highest to lowest match rate. 
    3) For a given record, we first attempt to match to the highest priority vintage.
       If a match occurs, then the record is assigned that vintage. If no match occurs,
       we will attempt to find a match in the next highest priority vintage. This 
       process continues until either a match is found or until all options are 
       exhausted (resulting in a vintage of NA). 
    
    param: df: pandas dataframe containing records with ambiguous census vintage
    param: date_col: name of column denoting date of each record in df
    param: geoid_col: name of column containing census geoid of ambiguous vintage
    param: v2000_geoids: numpy array of geoids from the 2000 census vintage
    param: v2010_geoids: numpy array of geoids from the 2010 census vintage
    param: v2020_geoids: numpy array of geoids from the 2020 census vintage
    returns: df: modified version of df containing a "vintage" column
    returns: match_rate: match rate of record geoids to each census vintage, 
                         stratified by record year. 
    """

    # Create a column denoting whether geoid of record matches to each vintage
    df['2000'] = df[geoid_col].isin(v2000_geoids)
    df['2010'] = df[geoid_col].isin(v2010_geoids)
    df['2020'] = df[geoid_col].isin(v2020_geoids)
    
    # Create column denoting year of record
    df['record_year'] = df[date_col].dt.year
    
    # Calculate match rate for each record year x vintage combination
    match_rate = df.groupby('record_year')[['2000','2010','2020']].mean().reset_index()
    match_rate = pd.melt(match_rate,id_vars=['record_year'],var_name='vintage',value_name='match_rate')
    
    # For each record year, order vintages from lowest to highest match rate
    match_rate = match_rate.sort_values(by=['record_year','match_rate'],ascending=[True,False])
    vintage_order = match_rate.groupby('record_year').agg({'vintage':tuple}).reset_index().rename(columns={'vintage':'vintage_order'})
    
    # Attach to record-level dataframe. This will be used to determine priority of
    # each potential vintage match. 
    df = pd.merge(df,vintage_order,on='record_year',how='left')
    
    # For each record, assign vintage based on priority and presence of a match
    df['vintage'] = pd.NA
    orderings = df['vintage_order'].unique()
    
    for order in orderings:
        mask = (df['vintage_order'] == order)
        df.loc[mask,'vintage'] = df[mask][list(order)].apply(lambda x: x.idxmax() if x.any() else pd.NA, axis=1)
    
    df['vintage'] = df['vintage'].astype('int64[pyarrow]')
    df.drop(columns=['2000','2010','2020','record_year','vintage_order'],inplace=True)

    return(df,match_rate)

def policies_in_force_over_time(df):
    """
    This function calculates the daily number of NFIP policies in force
    based on the listed start/end dates of each OpenFEMA policy record. 
    """

    start_date = df['policyEffectiveDate'].min()
    end_date = pd.Timestamp('today')
        
    t = pd.date_range(start_date,end_date,freq='D')
    timeseries_df = pd.DataFrame(data={'date':t})
    
    inflow = df[['policyEffectiveDate','policyCount']].groupby('policyEffectiveDate').sum().reset_index().rename(columns={'policyCount':'inflow','policyEffectiveDate':'date'})
    outflow = df[['policyTerminationDate','policyCount']].groupby('policyTerminationDate').sum().reset_index().rename(columns={'policyCount':'outflow','policyTerminationDate':'date'})
    
    timeseries_df = pd.merge(timeseries_df,inflow,on='date',how='left')
    timeseries_df = pd.merge(timeseries_df,outflow,on='date',how='left')
    timeseries_df.fillna(0,inplace=True)
    
    timeseries_df['netflow'] = timeseries_df['inflow'] - timeseries_df['outflow']
    timeseries_df['policies_in_force'] = timeseries_df['netflow'].cumsum()
    
    return(timeseries_df)

### *** INITIAL SETUP *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

# Get current working directory
pwd = os.getcwd()

### *** LOAD DATA *** ###

# Census block groups
bg2000 = gpd.read_file(config['paths']['censusblockgroups_2000'],ignore_geometry=True)
bg2010 = gpd.read_file(config['paths']['censusblockgroups_2010'],ignore_geometry=True)
bg2020 = gpd.read_file(config['paths']['censusblockgroups_2020'],ignore_geometry=True)

# Block group to tract crosswalks
bg2000_tr2010_crosswalk = pd.read_parquet(os.path.join(pwd,'crosswalks/bg2000_tr2010_crosswalk.parquet'))
bg2020_tr2010_crosswalk = pd.read_parquet(os.path.join(pwd,'crosswalks/bg2020_tr2010_crosswalk.parquet'))

# OpenFEMA NFIP Policies
usecols = ['propertyState','censusGeoid','originalNBDate','policyEffectiveDate','policyTerminationDate','policyCount']
policies = pd.read_parquet(config['paths']['openfema_policies'],columns=usecols)
policies['originalNBDate'] = pd.to_datetime(policies['originalNBDate'],errors='coerce')
policies['policyEffectiveDate'] = pd.to_datetime(policies['policyEffectiveDate'],errors='coerce')
policies['policyTerminationDate'] = pd.to_datetime(policies['policyTerminationDate'],errors='coerce')

# OpenFEMA NFIP Claims
usecols = ['state','censusGeoid','dateOfLoss','buildingDamageAmount','contentsDamageAmount']
claims = pd.read_parquet(config['paths']['openfema_claims'],columns=usecols)
claims['dateOfLoss'] = pd.to_datetime(claims['dateOfLoss'])

### *** ASSIGN CENSUS VINTAGE TO OPENFEMA RECORDS *** ###

# Get list of GEOIDs from each census vintage
v2000_geoids = bg2000['GEOID'].unique()
v2010_geoids = bg2010['GEOID'].unique()
v2020_geoids = bg2020['GEOID'].unique()

# Infer census GEOID vintage of OpenFEMA NFIP claim records
claims,vintage_claim_match_rate = assign_census_vintage(claims,
                                                        'dateOfLoss',
                                                        'censusGeoid',
                                                        v2000_geoids,
                                                        v2010_geoids,
                                                        v2020_geoids)

# Infer census GEOID vintage of OpenFEMA NFIP policy records
policies,vintage_policy_match_rate = assign_census_vintage(policies,
                                                        'policyEffectiveDate',
                                                        'censusGeoid',
                                                        v2000_geoids,
                                                        v2010_geoids,
                                                        v2020_geoids)

### *** USE CROSSWALKS TO DETERMINE 2010 TRACT *** ###

# 2000 block groups --> 2010 tracts
cw_2000 = bg2000_tr2010_crosswalk[['censusblockgroup_2000','censustract_2010']]
cw_2000 = cw_2000.rename(columns={'censusblockgroup_2000':'censusGeoid'})
cw_2000['vintage'] = 2000

# 2020 block groups --> 2010 tracts
cw_2020 = bg2020_tr2010_crosswalk[['censusblockgroup_2020','censustract_2010']]
cw_2020 = cw_2020.rename(columns={'censusblockgroup_2020':'censusGeoid'})
cw_2020['vintage'] = 2020

# 2010 block groups --> 2010 tracts
cw_2010 = pd.DataFrame({'censusGeoid':bg2010['GEOID']})
cw_2010 = cw_2010.dropna().drop_duplicates()
cw_2010['censustract_2010'] = cw_2010['censusGeoid'].apply(lambda x: x[:11])
cw_2010['vintage'] = 2010

# Combined crosswalk dataframe
cw_combined = pd.concat([cw_2000,cw_2010,cw_2020]).reset_index(drop=True)

# Attach to OpenFEMA records
claims = pd.merge(claims,cw_combined,on=['censusGeoid','vintage'],how='left')
policies = pd.merge(policies,cw_combined,on=['censusGeoid','vintage'],how='left')

### *** GET COMBINATIONS OF CENSUS TRACT / YEAR *** ###

tracts = cw_2010['censustract_2010'].unique()
start_year = 1998
end_year = 2025
years = np.arange(start_year,end_year+1)

tract_df = pd.DataFrame(product(tracts,years),columns=['censustract_2010','year'])

# Drop records with missing tract information
claims = claims[claims['censustract_2010'].isin(tracts)]
policies = policies[policies['censustract_2010'].isin(tracts)]

### *** CALCULATE NUMBER OF CLAIMS *** ###

# Drop claims with no demonstrable flood damage
# (might be due to non-covered perils like wind)
claims['buildingDamageAmount'] = claims['buildingDamageAmount'].fillna(0)
claims['contentsDamageAmount'] = claims['contentsDamageAmount'].fillna(0)
claims['totalDamageAmount'] = claims['buildingDamageAmount'] + claims['contentsDamageAmount']
claims = claims[claims['totalDamageAmount'] > 0]

# Calculate number of NFIP claims by tract and year
claims['claimCount'] = 1
claims['year'] = claims['dateOfLoss'].dt.year

# Aggregate number of claims by tract and year
claim_counts = claims.groupby(['censustract_2010','year']).agg({'claimCount':'sum'}).reset_index()

# Attach to tract-level dataframe
tract_df = pd.merge(tract_df,claim_counts,how='left',on=['censustract_2010','year']).fillna(0)

### *** CALCULATE POLICY-TIME *** ###

# Estimate number of policies-in-force (PIF) in each tract on each day
PIF_timeseries = policies.groupby('censustract_2010').apply(policies_in_force_over_time).reset_index()[['censustract_2010','date','policies_in_force']]
PIF_timeseries.rename(columns={'policies_in_force':'policyDays'},inplace=True)
PIF_timeseries['year'] = PIF_timeseries['date'].dt.year

# Exclude pre-2010 PIF estimates that do not reflect full policy base in force. 
# Also drop entries from after end of study period. 
PIF_timeseries = PIF_timeseries[(PIF_timeseries['year'] >= 2010)&(PIF_timeseries['year'] <= end_year)]

# Calculate follow-up time among NFIP policyholders in each tract and year
policy_time = PIF_timeseries.groupby(['censustract_2010','year']).agg({'policyDays':'sum'}).reset_index()
policy_time['policyYears'] = policy_time['policyDays']/365
policy_time.drop(columns='policyDays',inplace=True)

# Attach to tract-level dataframe
tract_df = pd.merge(tract_df,policy_time,how='left',on=['censustract_2010','year']).reset_index(drop=True)

### *** CALCULATE CLAIM RATE *** ###

# Because data on pre-2010 policy enrollment is incomplete, fill in the missing PIF data
# for each tract by assuming that PIF is equal to 2010 levels. This assumption is likely
# to be conservative and may overestimate the number of policies per capita during the
# 1998-2009 period.
tract_df['policyYears'] = tract_df.groupby('censustract_2010')['policyYears'].bfill()

# Calculate claim rate in each tract
# (may be unstable in tracts with few policies due to small numbers problem)
tract_df['claimRate'] = tract_df['claimCount'] / tract_df['policyYears']

### *** SAVE RESULTS *** ###

tract_df.to_parquet('NFIP_claim_rate_by_tract.parquet')
vintage_claim_match_rate.to_parquet('census_vintage_match_rate_claims.parquet')
vintage_policy_match_rate.to_parquet('census_vintage_match_rate_policies.parquet')

