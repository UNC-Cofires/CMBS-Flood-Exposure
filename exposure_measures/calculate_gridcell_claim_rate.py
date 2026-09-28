import numpy as np
import pandas as pd
import geopandas as gpd
import os
from itertools import product
from src.utils.config import find_project_root, load_config

### *** HELPER FUNCTIONS *** ###

def policies_in_force_over_time(df):

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

# OpenFEMA NFIP Policies
usecols = ['propertyState','latitude','longitude','policyEffectiveDate','policyTerminationDate','policyCount']
policies = pd.read_parquet(config['paths']['openfema_policies'],columns=usecols)
policies['policyEffectiveDate'] = pd.to_datetime(policies['policyEffectiveDate'],errors='coerce')
policies['policyTerminationDate'] = pd.to_datetime(policies['policyTerminationDate'],errors='coerce')

# OpenFEMA NFIP Claims
usecols = ['state','latitude','longitude','dateOfLoss','buildingDamageAmount','contentsDamageAmount']
claims = pd.read_parquet(config['paths']['openfema_claims'],columns=usecols)
claims['dateOfLoss'] = pd.to_datetime(claims['dateOfLoss'])

# 0.1 x 0.1 degree latitude/longitude gridcells
latlon_gridcells = gpd.read_file(config['paths']['gridcells'])

### *** GET COMBINATIONS OF GRIDCELL / YEAR *** ###

gridcells = latlon_gridcells['gridcell'].unique()
start_year = 1998
end_year = 2025
years = np.arange(start_year,end_year+1)

gridcell_df = pd.DataFrame(product(gridcells,years),columns=['gridcell','year'])

### *** CLEAN OPENFEMA GRIDCELLS *** ###

# Create gridcell variable (combination of rounded lat/lon)
claims['latitude'] = pd.to_numeric(claims['latitude'],errors='coerce')
claims['longitude'] = pd.to_numeric(claims['longitude'],errors='coerce')
policies['latitude'] = pd.to_numeric(policies['latitude'],errors='coerce')
policies['longitude'] = pd.to_numeric(policies['longitude'],errors='coerce')

claims['gridcell'] = claims['latitude'].apply(lambda x: f'{x:.1f}') + ',' + claims['longitude'].apply(lambda x: f'{x:.1f}')
policies['gridcell'] = policies['latitude'].apply(lambda x: f'{x:.1f}') + ',' + policies['longitude'].apply(lambda x: f'{x:.1f}')

# Drop nonexistent gridcells
claims = claims[claims['gridcell'].isin(gridcell_df['gridcell'])]
policies = policies[policies['gridcell'].isin(gridcell_df['gridcell'])]

### *** CALCULATE NUMBER OF CLAIMS *** ###

# Drop claims with no demonstrable flood damage
# (might be due to non-covered perils like wind)
claims['buildingDamageAmount'] = claims['buildingDamageAmount'].fillna(0)
claims['contentsDamageAmount'] = claims['contentsDamageAmount'].fillna(0)
claims['totalDamageAmount'] = claims['buildingDamageAmount'] + claims['contentsDamageAmount']
claims = claims[claims['totalDamageAmount'] > 0]

# Calculate number of NFIP claims by gridcell and year
claims['claimCount'] = 1
claims['year'] = claims['dateOfLoss'].dt.year

# Aggregate number of claims by gridcell and year
claim_counts = claims.groupby(['gridcell','year']).agg({'claimCount':'sum'}).reset_index()

# Attach to gridcell-level dataframe
gridcell_df = pd.merge(gridcell_df,claim_counts,how='left',on=['gridcell','year']).fillna(0)

### *** CALCULATE POLICY-TIME *** ###

# Estimate number of policies-in-force (PIF) in each gridcell on each day
PIF_timeseries = policies.groupby('gridcell').apply(policies_in_force_over_time).reset_index()[['gridcell','date','policies_in_force']]
PIF_timeseries.rename(columns={'policies_in_force':'policyDays'},inplace=True)
PIF_timeseries['year'] = PIF_timeseries['date'].dt.year

# Exclude pre-2010 PIF estimates that do not reflect full policy base in force. 
# Also drop entries from after end of study period. 
PIF_timeseries = PIF_timeseries[(PIF_timeseries['year'] >= 2010)&(PIF_timeseries['year'] <= end_year)]

# Calculate follow-up time among NFIP policyholders in each gridcell and year
policy_time = PIF_timeseries.groupby(['gridcell','year']).agg({'policyDays':'sum'}).reset_index()
policy_time['policyYears'] = policy_time['policyDays']/365
policy_time.drop(columns='policyDays',inplace=True)

# Attach to gridcell-level dataframe
gridcell_df = pd.merge(gridcell_df,policy_time,how='left',on=['gridcell','year']).reset_index(drop=True)

### *** CALCULATE CLAIM RATE *** ###

# Because data on pre-2010 policy enrollment is incomplete, fill in the missing PIF data
# for each gridcell by assuming that PIF is equal to 2010 levels. This assumption is likely
# to be conservative and may overestimate the number of policies per capita during the
# 1998-2009 period.
gridcell_df['policyYears'] = gridcell_df.groupby('gridcell')['policyYears'].bfill()

# Calculate claim rate in each gridcell
# (Likely to be unstable in gridcells with few policies due to small numbers problem)
gridcell_df['claimRate'] = gridcell_df['claimCount'] / gridcell_df['policyYears']

### *** SAVE RESULTS *** ###

# Save file
gridcell_df.to_parquet('NFIP_claim_rate_by_gridcell.parquet')