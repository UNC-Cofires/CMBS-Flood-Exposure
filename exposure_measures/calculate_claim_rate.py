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
usecols = ['propertyState','reportedZipCode','policyEffectiveDate','policyTerminationDate','policyCount']
policies = pd.read_parquet(config['paths']['openfema_policies'],columns=usecols)
policies['policyEffectiveDate'] = pd.to_datetime(policies['policyEffectiveDate'],errors='coerce')
policies['policyTerminationDate'] = pd.to_datetime(policies['policyTerminationDate'],errors='coerce')

# OpenFEMA NFIP Claims
usecols = ['state','reportedZipCode','dateOfLoss','buildingDamageAmount','contentsDamageAmount']
claims = pd.read_parquet(config['paths']['openfema_claims'],columns=usecols)
claims['dateOfLoss'] = pd.to_datetime(claims['dateOfLoss'])

# Census Bureau Zip Code Tabulation Areas (ZCTAs)
zctas = gpd.read_file(config['paths']['zctas_2020'])

### *** GET COMBINATIONS OF ZIPCODE / YEAR *** ###

zipcodes = zctas['ZCTA5CE20'].unique()
start_year = 1998
end_year = 2025
years = np.arange(start_year,end_year+1)

zipcode_df = pd.DataFrame(product(zipcodes,years),columns=['reportedZipCode','year'])

### *** CLEAN OPENFEMA ZIP CODES *** ###

# Sometimes data contains ZIP+4
# In these cases, keep only the 5-digit zip code
claims['reportedZipCode'] = claims['reportedZipCode'].apply(lambda x: x.split('-')[0])
policies['reportedZipCode'] = policies['reportedZipCode'].apply(lambda x: x.split('-')[0])

# Drop zipcodes that are missing from census data
claims = claims[claims['reportedZipCode'].isin(zipcode_df['reportedZipCode'])]
policies = policies[policies['reportedZipCode'].isin(zipcode_df['reportedZipCode'])]

### *** CALCULATE NUMBER OF CLAIMS *** ###

# Drop claims with no demonstrable flood damage
# (might be due to non-covered perils like wind)
claims['buildingDamageAmount'] = claims['buildingDamageAmount'].fillna(0)
claims['contentsDamageAmount'] = claims['contentsDamageAmount'].fillna(0)
claims['totalDamageAmount'] = claims['buildingDamageAmount'] + claims['contentsDamageAmount']
claims = claims[claims['totalDamageAmount'] > 0]

# Calculate number of NFIP claims by zipcode and year
claims['claimCount'] = 1
claims['year'] = claims['dateOfLoss'].dt.year

# Aggregate number of claims by zipcode and year
claim_counts = claims.groupby(['reportedZipCode','year']).agg({'claimCount':'sum'}).reset_index()

# Attach to zipcode-level dataframe
zipcode_df = pd.merge(zipcode_df,claim_counts,how='left',on=['reportedZipCode','year']).fillna(0)

### *** CALCULATE POLICY-TIME *** ###

# Estimate number of policies-in-force (PIF) in each zip code on each day
PIF_timeseries = policies.groupby('reportedZipCode').apply(policies_in_force_over_time).reset_index()[['reportedZipCode','date','policies_in_force']]
PIF_timeseries.rename(columns={'policies_in_force':'policyDays'},inplace=True)
PIF_timeseries['year'] = PIF_timeseries['date'].dt.year

# Exclude pre-2010 PIF estimates that do not reflect full policy base in force. 
# Also drop entries from after end of study period. 
PIF_timeseries = PIF_timeseries[(PIF_timeseries['year'] >= 2010)&(PIF_timeseries['year'] <= end_year)]

# Calculate follow-up time among NFIP policyholders in each zipcode and year
policy_time = PIF_timeseries.groupby(['reportedZipCode','year']).agg({'policyDays':'sum'}).reset_index()
policy_time['policyYears'] = policy_time['policyDays']/365
policy_time.drop(columns='policyDays',inplace=True)

# Attach to zipcode-level dataframe
zipcode_df = pd.merge(zipcode_df,policy_time,how='left',on=['reportedZipCode','year']).reset_index(drop=True)

### *** CALCULATE CLAIM RATE *** ###

# Because data on pre-2010 policy enrollment is incomplete, fill in the missing PIF data
# for each zip code by assuming that PIF is equal to 2010 levels. This assumption is likely
# to be conservative and may overestimate the number of policies per capita during the
# 1998-2009 period.
zipcode_df['policyYears'] = zipcode_df.groupby('reportedZipCode')['policyYears'].bfill()

# Calculate claim rate in each zip code
# (Likely to be unstable in zipcodes with few policies due to small numbers problem)
zipcode_df['claimRate'] = zipcode_df['claimCount'] / zipcode_df['policyYears']

### *** SAVE RESULTS *** ###

outname = os.path.join(pwd,'NFIP_claim_rate_by_zipcode.parquet')
zipcode_df.to_parquet(outname)