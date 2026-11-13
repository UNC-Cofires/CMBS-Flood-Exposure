import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import os
from src.utils.config import find_project_root, load_config

### *** HELPER FUNCTIONS *** ###

def evaluate_delinquency(df):
    """
    This function evaluates 

    param: df: pandas dataframe describing delinquency status over time for a specific loan in 
               the Trepp database. Assumed to be pre-sorted based on the distdate column. 
    returns: df: modified version of dataframe that contains columns denoting whether the loan
                 has ever experienced a specific delinquency status (e.g., 60+ days delinquent) 
                 at different points in time. 
    """

    df['D60'] = (df['dlqderivedcd']=='2').astype('int64[pyarrow]').fillna(0)
    df['D90'] = (df['dlqderivedcd']=='3').astype('int64[pyarrow]').fillna(0)
    df['ever_D60'] = df['D60'].cumsum().clip(upper=1)
    df['ever_D90'] = df['D90'].cumsum().clip(upper=1)
    df['ever_in_foreclosure_or_REO'] = df['in_foreclosure_or_REO'].cumsum().clip(upper=1)

    return df

def combine_codes(x):
    """
    This function takes as input a pandas series and returns a comma-separated list of unique values. 
    """
    return x.dropna().drop_duplicates().astype('string[pyarrow]').str.cat(sep=",")

### *** INITIAL SETUP *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

# Get current working directory 
pwd = os.getcwd()

### *** LOAD DATA *** ###

# Read in loan file 
loan_path = os.path.join(pwd,'filtered_loans.parquet')

loan_usecols = ['masterloanidtrepp',
                'distdate',
                'origdate',
                'maturitydate',
                'origloanbal',
                'obal',
                'dlqderivedcd',
                'prepaycd',
                'realizedloss',
                'loanmoddate',
                'loanmodcode',
                'workoutcode',
                'propname',
                'address',
                'city',
                'state',
                'zip',
                'cssaproptype',
                'units',
                'rentarea',
                'priorfyasof',
                'priorfyrev',
                'priorfyexp',
                'priorfynoi',
                'priorfyocc']

loans = pd.read_parquet(loan_path,columns=loan_usecols)

# Read in prop file
prop_path = os.path.join(pwd,'filtered_properties.parquet')
prop_usecols = ['masterloanidtrepp',
                'masterpropidtrepp',
                'distdate',
                'propstatus']

prop = pd.read_parquet(prop_path,columns=prop_usecols)

# Read in additional columns in prop file that we'll use to assess lease rollover
lease_rollover_usecols = ['masterloanidtrepp',
                          'distdate',
                          'curlessee1expdt',
                          'curlessee2expdt',
                          'curlessee3expdt',
                          'lesseepctcurr1',
                          'lesseepctcurr2',
                          'lesseepctcurr3']

lease_rollover = pd.read_parquet(prop_path,columns=lease_rollover_usecols)

# Attach property status to loan file
loans = pd.merge(loans,prop,on=['masterloanidtrepp','distdate'],how='left')

### *** REALIZED LOSSES *** ###

losses = loans[['masterloanidtrepp','distdate','origloanbal','realizedloss']]
losses['year'] = losses['distdate'].dt.year

agg_dict = {'origloanbal':'last',
            'realizedloss':'last'}

losses = losses.groupby(['masterloanidtrepp','year']).agg(agg_dict).reset_index()
losses['loss_rate'] = 100*losses['realizedloss']/losses['origloanbal']

### *** LOAN STATUS OVER TIME *** ###

# In foreclosure or REO
foreclosure_REO_mask = loans['propstatus'].isin([1,2])
loans['in_foreclosure_or_REO'] = foreclosure_REO_mask.astype('int64[pyarrow]')

# Paid off, prepaid, or liquidated
# (Still count loan as "active" during the first month where a zero balance shows up)
loans['zero_balance_flag'] = (loans['obal']==0).astype('int64[pyarrow]')
zero_balance_mask = loans.groupby('masterloanidtrepp')['zero_balance_flag'].cumsum() > 1

# Defeased, released or substituted
# (Still count loan as "active" during the first month when defeased)
loans['defeased_released_flag'] = loans['propstatus'].isin([3,4,5]).astype('int64[pyarrow]')
defeased_released_mask = loans.groupby('masterloanidtrepp')['defeased_released_flag'].cumsum() > 1

# Drop observations from after a loan is repaid/liquidated or a property is defeased/released/substituted
active_mask = ~(zero_balance_mask|defeased_released_mask)
loans = loans[active_mask]

# Evaluate delinquency status of each loan over time
loans = loans.groupby('masterloanidtrepp').apply(evaluate_delinquency).reset_index(drop=True)

### *** BUILD ANNUAL PANEL *** ###

agg_dict = {'distdate':['min','max'],
            'origdate':'last',
            'maturitydate':'last',
            'origloanbal':'last',
            'masterpropidtrepp':'last',
            'propname':'last',
            'address':'last',
            'city':'last',
            'state':'last',
            'zip':'last',
            'cssaproptype':'last',
            'units':'last',
            'rentarea':'last'}

panel = loans.groupby('masterloanidtrepp').agg(agg_dict)

colnames = list(agg_dict.keys())
colnames.remove('distdate')
colnames = ['first_obs','last_obs'] + colnames

panel.columns = colnames

# Drop entries with missing data in key fields
panel = panel.dropna(subset=['cssaproptype','origdate','first_obs','last_obs'])

# Specify loan vintage (year of origination)
panel['vintage'] = panel['origdate'].dt.year

# Create one row for each loan-year of observation
panel['year'] = panel.apply(lambda x: np.arange(x['first_obs'].year,x['last_obs'].year+1),axis=1)
panel = panel.explode('year').reset_index()

### *** DELINQUENCY STATUS *** ###

delinquency_status = loans[['masterloanidtrepp','distdate','D60','D90','in_foreclosure_or_REO','ever_D60','ever_D90','ever_in_foreclosure_or_REO']]
delinquency_status['year'] = delinquency_status['distdate'].dt.year

agg_dict = {'D60':'max',
            'D90':'max',
            'in_foreclosure_or_REO':'max',
            'ever_D60':'max',
            'ever_D90':'max',
            'ever_in_foreclosure_or_REO':'max'}

delinquency_status = delinquency_status.groupby(['masterloanidtrepp','year']).agg(agg_dict).reset_index()

# Sometimes a loan won't be marked as delinquent in the Trepp data until it is already D90+. 
# We know that in these situations, it must have been 60 days delinquent at some point in time.  
# Update delinquency fields so that D60 >= D90 >= foreclosed/REO at all timepoints.
delinquency_status['D60'] = (delinquency_status['D60'] + delinquency_status['D90'] + delinquency_status['in_foreclosure_or_REO']).clip(upper=1)
delinquency_status['D90'] = (delinquency_status['D90'] + delinquency_status['in_foreclosure_or_REO']).clip(upper=1)
delinquency_status['ever_D60'] = (delinquency_status['ever_D60'] + delinquency_status['ever_D90'] + delinquency_status['ever_in_foreclosure_or_REO']).clip(upper=1)
delinquency_status['ever_D90'] = (delinquency_status['ever_D90'] + delinquency_status['ever_in_foreclosure_or_REO']).clip(upper=1)

# Attach to panel data
panel = pd.merge(panel,delinquency_status,on=['masterloanidtrepp','year'],how='left')

# Also attach information on realized losses
panel = pd.merge(panel,losses[['masterloanidtrepp','year','realizedloss','loss_rate']],on=['masterloanidtrepp','year'],how='left')

### *** PROPERTY FINANCIALS *** ###

prop_financials = loans[['masterloanidtrepp','priorfyasof','priorfyrev','priorfyexp','priorfynoi','priorfyocc']]
rename_dict = {'priorfyasof':'year','priorfyrev':'rev','priorfyexp':'exp','priorfynoi':'noi','priorfyocc':'occ'}
prop_financials = prop_financials.rename(columns=rename_dict).dropna(subset=['year'])
prop_financials['year'] = prop_financials['year'].dt.year
prop_financials = prop_financials.drop_duplicates(subset=['masterloanidtrepp','year'],keep='last')

# Attach to panel data
panel = pd.merge(panel,prop_financials,on=['masterloanidtrepp','year'],how='left')

# Filter panel by years included in study period
study_period_mask = (panel['year'] >= 1998)&(panel['year'] <= 2025)
panel = panel[study_period_mask].reset_index(drop=True)

### *** LEASE ROLLOVER *** ###

lease_rollover['year'] = lease_rollover['distdate'].dt.year
lease_rollover = lease_rollover.drop_duplicates(subset=['masterloanidtrepp','year'])

for i in range(1,3+1):
    lease_rollover[f'rollyear{i}'] = lease_rollover[f'curlessee{i}expdt'].dt.year
    lease_rollover[f'next2roll{i}'] = (lease_rollover[f'rollyear{i}'] - lease_rollover['year'] < 2).astype(int)
    lease_rollover[f'rollshare{i}'] = lease_rollover[f'lesseepctcurr{i}'].fillna(0).clip(0,100)

roll_presence = lease_rollover[['next2roll1','next2roll2','next2roll3']].to_numpy()
roll_intensity = lease_rollover[['rollshare1','rollshare2','rollshare3']].to_numpy()
share_rolling = np.minimum((roll_presence*roll_intensity).sum(axis=1),100)

missing_lease_data_mask = lease_rollover[['rollyear1','rollyear2','rollyear3']].isna().all(axis=1)
share_rolling[missing_lease_data_mask] = np.nan

lease_rollover['pctrollnext2years'] = share_rolling
lease_rollover = lease_rollover[['masterloanidtrepp','year','pctrollnext2years']]

panel = pd.merge(panel,lease_rollover,on=['masterloanidtrepp','year'],how='left')

### *** REMAINING YEARS TO MATURITY *** ###

remaining_maturity = loans[['masterloanidtrepp','distdate','maturitydate']]
remaining_maturity['year'] = remaining_maturity['distdate'].dt.year
remaining_maturity['matyear'] = remaining_maturity['maturitydate'].dt.year
remaining_maturity['remainingterm'] = (remaining_maturity['matyear'] - remaining_maturity['year']).clip(0,None).astype('int64[pyarrow]')
remaining_maturity = remaining_maturity.drop_duplicates(subset=['masterloanidtrepp','year'])
remaining_maturity = remaining_maturity[['masterloanidtrepp','year','remainingterm']]

panel = pd.merge(panel,remaining_maturity,on=['masterloanidtrepp','year'],how='left')

### *** LOAN MODIFICATIONS / WORKOUTS *** ###

modifications = loans[['masterloanidtrepp','distdate','loanmoddate','loanmodcode','workoutcode']]

modified_mask = (~modifications[['loanmoddate','loanmodcode','workoutcode']].isna().all(axis=1))
modifications = modifications[modified_mask]

modifications['year'] = modifications['distdate'].dt.year
modifications['modyear'] = modifications['loanmoddate'].dt.year
modifications['modification_flag'] = (modifications['year'] == modifications['modyear']).astype('int64[pyarrow]')

agg_dict = {'modification_flag':'max',
            'loanmodcode': combine_codes,
            'workoutcode': combine_codes}

modifications = modifications.groupby(['masterloanidtrepp','year']).agg(agg_dict).reset_index()
modifications['loanmodcode'] = modifications['loanmodcode'].replace('',pd.NA)
modifications['workoutcode'] = modifications['workoutcode'].replace('',pd.NA)

panel = pd.merge(panel,modifications,on=['masterloanidtrepp','year'],how='left')
panel['modification_flag'] = panel['modification_flag'].fillna(0)

### *** LOAN LIQUIDATIONS / PREPAYMENTS *** ###

payoffs = loans[['masterloanidtrepp','distdate','zero_balance_flag','prepaycd','defeased_released_flag']]
mask = (~payoffs['prepaycd'].isna())|(payoffs['zero_balance_flag']==1)|(payoffs['defeased_released_flag']==1)
payoffs = payoffs[mask]

payoffs['year'] = payoffs['distdate'].dt.year

agg_dict = {'zero_balance_flag':'max',
            'defeased_released_flag':'max',
            'prepaycd': combine_codes}

payoffs = payoffs.groupby(['masterloanidtrepp','year']).agg(agg_dict).reset_index()
payoffs['prepaycd'] = payoffs['prepaycd'].replace('',pd.NA)

panel = pd.merge(panel,payoffs,on=['masterloanidtrepp','year'],how='left')
panel['zero_balance_flag'] = panel['zero_balance_flag'].fillna(0)
panel['defeased_released_flag'] = panel['defeased_released_flag'].fillna(0)

### *** ATTACH BUILDING ATTRIBUTES *** ###

# Load buildings
buildings_path = os.path.join(project_root,'geocoding/property_geospatial_data/matched_buildings')
buildings = gpd.read_parquet(buildings_path).set_geometry('point_geometry').to_crs(config['gis_params']['geographic_crs'])
buildings = buildings.sort_values(by=['masterloanidtrepp','direct_match','SQMETERS'],ascending=False)

# Create latitude/longitude variables
buildings['latitude'] = buildings['point_geometry'].y
buildings['longitude'] = buildings['point_geometry'].x

# Create census tract variable
buildings['censustract_2010'] = buildings['censusblockgroup_2010'].map(lambda x: x[:11], na_action='ignore')

# Aggregate attributes from structures associated with a given property
agg_dict = {'latitude':'first',
            'longitude':'first',
            'countyfips_2022':'first',
            'censustract_2010':'first',
            'zcta_2020':'first',
            'BUILD_ID':'count',
            'FEMA_100y_floodplain_indicator':'max',
            'FEMA_500y_floodplain_indicator':'max'}

building_attributes = buildings.groupby('masterloanidtrepp').agg(agg_dict)

building_attributes['FEMA_500y_floodplain_indicator'] = ((building_attributes['FEMA_500y_floodplain_indicator']==1)&(building_attributes['FEMA_100y_floodplain_indicator']==0)).astype(int)
building_attributes['floodzone'] = pd.from_dummies(building_attributes[['FEMA_100y_floodplain_indicator','FEMA_500y_floodplain_indicator']],default_category='outside_FEMA_floodplains')
building_attributes['floodzone'] = building_attributes['floodzone'].str.replace('_indicator','')
building_attributes['lumped_floodzone'] = building_attributes['floodzone'].apply(lambda x: 'inside_FEMA_floodplains' if x != 'outside_FEMA_floodplains' else x)

building_attributes = building_attributes.rename(columns={'BUILD_ID':'num_structures'}).reset_index()

panel = pd.merge(panel,building_attributes,on='masterloanidtrepp',how='inner')

# Create 0.1 x 0.1 degree lat/lon gridcell identifier
panel['gridcell'] = panel['latitude'].apply(lambda x: f'{x:0.1f}') + ',' + panel['longitude'].apply(lambda x: f'{x:0.1f}')

### *** ATTACH COUNTY METRO AREA GROUPINGS *** ###

metro_areas_path = os.path.join(pwd,'metro_areas/county_metro_area_groupings.parquet')
metro_areas = gpd.read_parquet(metro_areas_path).rename(columns={'GEOID':'countyfips_2022'})
metro_areas = metro_areas[['countyfips_2022','csa_code','csa_title','cbsa_code','cbsa_title','cbsa_type']]

panel = pd.merge(panel,metro_areas,on='countyfips_2022',how='left')

# Drop properties located in areas outside CBSAs
panel = panel.dropna(subset=['cbsa_code']).reset_index(drop=True)

### *** SAVE RESULTS *** ###

# Rename columns
rename_dict = {'zcta_2020':'zipcode'}
panel.rename(columns=rename_dict, inplace=True)

# Reorder columns
columns = ['masterloanidtrepp',
           'year',
           'first_obs',
           'last_obs',
           'origdate',
           'origloanbal',
           'maturitydate',
           'vintage',
           'masterpropidtrepp',
           'cssaproptype',
           'units',
           'rentarea',
           'num_structures',
           'propname',
           'address',
           'city',
           'state',
           'zip',
           'latitude',
           'longitude',
           'gridcell',
           'countyfips_2022',
           'censustract_2010',
           'zipcode',
           'csa_code',
           'csa_title',
           'cbsa_code',
           'cbsa_title',
           'cbsa_type',
           'FEMA_100y_floodplain_indicator',
           'FEMA_500y_floodplain_indicator',
           'floodzone',
           'lumped_floodzone',
           'pctrollnext2years',
           'remainingterm',
           'zero_balance_flag',
           'prepaycd',
           'defeased_released_flag',
           'modification_flag',
           'loanmodcode',
           'workoutcode',
           'D60',
           'D90',
           'in_foreclosure_or_REO',
           'ever_D60',
           'ever_D90',
           'ever_in_foreclosure_or_REO',
           'realizedloss',
           'loss_rate',
           'rev',
           'exp',
           'noi',
           'occ']

panel = panel[columns]

# Save to file
outname = os.path.join(pwd,'panel_outcome_data.parquet')
panel.to_parquet(outname)

### *** PRINT SUMMARY FOR USER *** ###

num_loans = len(panel['masterloanidtrepp'].unique())
num_loan_years = len(panel)

print(f'Number of loans in panel: {num_loans}')
print(f'Number of loan-years in panel: {num_loan_years}\n')
print('Population rate of key fields:')

fields = ['zero_balance_flag',
          'modification_flag',
          'D60',
          'D90',
          'in_foreclosure_or_REO',
          'ever_D60',
          'ever_D90',
          'ever_in_foreclosure_or_REO',
          'realizedloss',
          'loss_rate',
          'rev',
          'exp',
          'noi',
          'occ']

for field in fields:
    pop_rate = (~panel[field].isna()).mean()
    print(f'    {field}: {100*pop_rate:.1f}%')