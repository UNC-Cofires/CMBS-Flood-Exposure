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

    D60 = (df['dlqderivedcd']=='2').astype('int64[pyarrow]').fillna(0)
    D90 = (df['dlqderivedcd']=='3').astype('int64[pyarrow]').fillna(0)

    df['ever_D60'] = D60.cumsum().clip(upper=1)
    df['ever_D90'] = D90.cumsum().clip(upper=1)
    df['ever_in_foreclosure_or_REO'] = df['in_foreclosure_or_REO'].cumsum().clip(upper=1)

    return df

### *** INITIAL SETUP *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

# Get current working directory 
pwd = os.getcwd()

### *** CREATE CMBS LOAN PANEL *** ###

## Load data

# Read in loan file 
loan_path = os.path.join(pwd,'filtered_loans.parquet')

loan_usecols = ['masterloanidtrepp',
                'distdate',
                'origdate',
                'maturitydate',
                'obal',
                'dlqderivedcd',
                'prepaycd',
                'propname',
                'address',
                'city',
                'state',
                'zip',
                'cssaproptype',
                'priorfyasof',
                'priorfyrev',
                'priorfyexp',
                'priorfynoi',
                'priorfyocc']

loans = pd.read_parquet(loan_path,columns=loan_usecols)

# Read in prop file
prop_path = os.path.join(pwd,'filtered_properties.parquet')
prop_usecols = ['masterloanidtrepp','masterpropidtrepp','distdate','propstatus']
prop = pd.read_parquet(prop_path,columns=prop_usecols)

# Attach property status to loan file
loans = pd.merge(loans,prop,on=['masterloanidtrepp','distdate'],how='left')

## Evaluate loan/property status

# In foreclosure or REO
foreclosure_REO_mask = loans['propstatus'].isin([1,2])
loans['in_foreclosure_or_REO'] = foreclosure_REO_mask.astype('int64[pyarrow]')

# Defeased, released or substituted
defeased_released_mask = loans['propstatus'].isin([3,4,5])

# Paid off or prepaid
zero_balance_mask = (loans['obal']==0)

# Drop observations from after a loan is paid off or a property is defeased/released/substituted
active_mask = ~(defeased_released_mask|zero_balance_mask)
loans = loans[active_mask]

# Evaluate delinquency status of each loan over time
loans = loans.groupby('masterloanidtrepp').apply(evaluate_delinquency).reset_index(drop=True)

## Create panel of yearly property financial observations

agg_dict = {'distdate':['min','max'],
            'origdate':'last',
            'maturitydate':'last',
            'masterpropidtrepp':'last',
            'propname':'last',
            'address':'last',
            'city':'last',
            'state':'last',
            'zip':'last',
            'cssaproptype':'last'}

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

## Determine loan delinquency status in each year

delinquency_status = loans[['masterloanidtrepp','distdate','ever_D60','ever_D90','ever_in_foreclosure_or_REO']]
delinquency_status['year'] = delinquency_status['distdate'].dt.year
delinquency_status = delinquency_status.groupby(['masterloanidtrepp','year']).agg({'ever_D60':'max','ever_D90':'max','ever_in_foreclosure_or_REO':'max'}).reset_index()

# Sometimes a loan won't be marked as delinquent in the Trepp data until it is already D90+. 
# We know that in these situations, it must have been 60 days delinquent at some point in time.  
# Update delinquency fields so that D60 >= D90 >= foreclosed/REO at all timepoints.  
delinquency_status['ever_D60'] = (delinquency_status['ever_D60'] + delinquency_status['ever_D90'] + delinquency_status['ever_in_foreclosure_or_REO']).clip(upper=1)
delinquency_status['ever_D90'] = (delinquency_status['ever_D90'] + delinquency_status['ever_in_foreclosure_or_REO']).clip(upper=1)

# Attach to panel data
panel = pd.merge(panel,delinquency_status,on=['masterloanidtrepp','year'],how='left')

## Determine property revenues, expenses, noi, and occupancy in each year

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

### *** ATTACH BUILDING ATTRIBUTES *** ###

buildings_path = os.path.join(project_root,'geocoding/property_geospatial_data/matched_buildings')
buildings = gpd.read_parquet(buildings_path)
buildings = buildings.sort_values(by=['masterloanidtrepp','direct_match','SQMETERS'],ascending=False)

agg_dict = {'LATITUDE':'first',
            'LONGITUDE':'first',
            'countyfips_2022':'first',
            'censusblockgroup_2020':'first',
            'zcta_2020':'first',
            'FEMA_100y_floodplain_indicator':'max',
            'FEMA_500y_floodplain_indicator':'max'}

building_attributes = buildings.groupby('masterloanidtrepp').agg(agg_dict)
building_attributes['FEMA_500y_floodplain_indicator'] = ((building_attributes['FEMA_500y_floodplain_indicator']==1)&(building_attributes['FEMA_100y_floodplain_indicator']==0)).astype(int)
building_attributes = building_attributes.rename(columns={'LATITUDE':'latitude','LONGITUDE':'longitude'}).reset_index()

panel = pd.merge(panel,building_attributes,on='masterloanidtrepp',how='inner')

### *** ATTACH COUNTY METRO AREA GROUPINGS *** ###

metro_areas_path = os.path.join(pwd,'metro_areas/county_metro_area_groupings.parquet')
metro_areas = gpd.read_parquet(metro_areas_path).rename(columns={'GEOID':'countyfips_2022'})
metro_areas = metro_areas[['countyfips_2022','csa_code','csa_title','cbsa_code','cbsa_title','cbsa_type']]

panel = pd.merge(panel,metro_areas,on='countyfips_2022',how='left')

# Drop properties located in areas outside CBSAs
panel = panel.dropna(subset=['cbsa_code']).reset_index(drop=True)


### *** SAVE RESULTS *** ###

# Reorder columns
columns = ['masterloanidtrepp',
           'year',
           'first_obs',
           'last_obs',
           'origdate',
           'maturitydate',
           'vintage',
           'masterpropidtrepp',
           'cssaproptype',
           'propname',
           'address',
           'city',
           'state',
           'zip',
           'latitude',
           'longitude',
           'countyfips_2022',
           'censusblockgroup_2020',
           'zcta_2020',
           'csa_code',
           'csa_title',
           'cbsa_code',
           'cbsa_title',
           'cbsa_type',
           'FEMA_100y_floodplain_indicator',
           'FEMA_500y_floodplain_indicator',
           'ever_D60',
           'ever_D90',
           'ever_in_foreclosure_or_REO',
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

fields = ['ever_D60','ever_D90','ever_in_foreclosure_or_REO','rev','exp','noi','occ']
for field in fields:
    pop_rate = (~panel[field].isna()).mean()
    print(f'    {field}: {100*pop_rate:.1f}%')