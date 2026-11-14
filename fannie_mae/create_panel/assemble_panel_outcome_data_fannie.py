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
               the Fannie Mae Multifamily Loan Performance Database (MFLPD). 
               Assumed to be pre-sorted based on the Reporting Period Date column. 
    returns: df: modified version of dataframe that contains columns denoting whether the loan
                 has ever experienced a specific delinquency status (e.g., 60+ days delinquent) 
                 at different points in time. 
    """

    df['D60'] = (df['Loan Payment Status']=='60-89 Days Delinquent').astype('int64[pyarrow]').fillna(0)
    df['D90'] = (df['Loan Payment Status']=='90+ Days Delinquent').astype('int64[pyarrow]').fillna(0)
    df['ever_D60'] = df['D60'].cumsum().clip(upper=1)
    df['ever_D90'] = df['D90'].cumsum().clip(upper=1)
    df['ever_in_foreclosure_or_REO'] = df['in_foreclosure_or_REO'].cumsum().clip(upper=1)

    return df

### *** INITIAL SETUP *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

# Get current working directory 
pwd = os.getcwd()

### *** LOAD DATA *** ###

## Loan origination data

loan_orig_path = os.path.join(pwd,'filtered_loans_fannie.parquet')

usecols = ['Loan Number',
           'Property ID',
           'Property Specific Property Type',
           'Property Total Units',
           'Property Name',
           'Property Address',
           'Property City',
           'Property State',
           'Property Zip Code']

loan_orig = pd.read_parquet(loan_orig_path,columns=usecols)
loan_orig['Property ID'] = loan_orig['Property ID'].astype('int64[pyarrow]').astype('string[pyarrow]')

## Loan performance data

usecols = ['Loan Number',
           'Reporting Period Date',
           'Note Date',
           'Original UPB',
           'UPB - Current',
           'Maturity Date - Current',
           'Loan Payment Status',
           'Liquidation/Prepayment Code',
           'Liquidation/Prepayment Date',
           'Lifetime Net Credit Loss Amount',
           'Modification Indicator',
           'Most Recent Modification Date',
           'Defeasance Date',
           'Foreclosure Date']

loan_perf = pd.read_parquet(config['paths']['fannie_loan_performance_data'],columns=usecols)
loan_perf = loan_perf.rename(columns={'Maturity Date - Current':'maturitydate'})

## Combine origination and performance data
loans = pd.merge(loan_orig,loan_perf,how='left',on='Loan Number')

## Operating statement data downloaded from DUS Disclose
operating_statements_path = os.path.join(pwd,'operating_statement_data/fannie_operating_statement_data_clean.parquet')
operating_statements = pd.read_parquet(operating_statements_path)

# Sort by loan ID / time
loans = loans.sort_values(by=['Loan Number','Reporting Period Date']).reset_index(drop=True)
operating_statements = operating_statements.sort_values(by=['Loan Number','statement_ending_date']).reset_index(drop=True)

### *** REALIZED LOSSES *** ###

losses = loans[['Loan Number','Reporting Period Date','Original UPB','Lifetime Net Credit Loss Amount']]

losses['year'] = losses['Reporting Period Date'].dt.year

agg_dict = {'Original UPB':'last',
            'Lifetime Net Credit Loss Amount':'last'}

losses = losses.groupby(['Loan Number','year']).agg(agg_dict).reset_index()
losses['realizedloss'] = losses['Lifetime Net Credit Loss Amount'].fillna(0)
losses['loss_rate'] = 100*losses['realizedloss']/losses['Original UPB']

### *** LOAN STATUS OVER TIME *** ###

# In foreclosure or REO
foreclosure_REO_mask = (loans['Foreclosure Date'] >= loans['Reporting Period Date']).fillna(False)
loans['in_foreclosure_or_REO'] = foreclosure_REO_mask.astype('int64[pyarrow]')

# Paid off, prepaid, or liquidated
liquidations = loans[['Loan Number','Liquidation/Prepayment Date']].dropna().drop_duplicates()
liquidations['zero_balance_flag'] = 1
liquidations = liquidations.rename(columns = {'Liquidation/Prepayment Date':'Reporting Period Date'})
loans = pd.concat([loans,liquidations]).sort_values(by=['Loan Number','Reporting Period Date']).reset_index(drop=True)
loans['zero_balance_flag'] = loans['zero_balance_flag'].fillna(0)
loans['zero_balance_flag'] = loans.groupby('Loan Number')['zero_balance_flag'].cumsum().clip(0,1).astype('Int64[pyarrow]')

# Defeased, released or substituted
loans['defeased_released_flag'] = (~loans['Defeasance Date'].isna()).astype('Int64[pyarrow]')

# Drop observations from after a loan is defeased
active_mask = ~(loans.groupby('Loan Number')['defeased_released_flag'].cumsum() > 1)
loans = loans[active_mask]

# Evaluate delinquency status of each loan over time
loans = loans.groupby('Loan Number').apply(evaluate_delinquency).reset_index(drop=True)

### *** BUILD ANNUAL PANEL *** ###

agg_dict = {'Reporting Period Date':['min','max'],
            'Note Date':'last',
            'maturitydate':'last',
            'Original UPB':'last',
            'Property ID':'last',
            'Property Name':'last',
            'Property Address':'last',
            'Property City':'last',
            'Property State':'last',
            'Property Zip Code':'last',
            'Property Specific Property Type':'last',
            'Property Total Units':'last'}

panel = loans.groupby('Loan Number').agg(agg_dict)

colnames = list(agg_dict.keys())
colnames.remove('Reporting Period Date')
colnames = ['first_obs','last_obs'] + colnames

panel.columns = colnames

# Drop entries with missing data in key fields
panel = panel.dropna(subset=['Property Specific Property Type','Note Date','first_obs','last_obs'])

# Specify loan vintage (year of origination)
panel['vintage'] = panel['Note Date'].dt.year

# Create one row for each loan-year of observation
panel['year'] = panel.apply(lambda x: np.arange(x['first_obs'].year,x['last_obs'].year+1),axis=1)
panel = panel.explode('year').reset_index()

### *** DELINQUENCY STATUS *** ###

delinquency_status = loans[['Loan Number','Reporting Period Date','D60','D90','in_foreclosure_or_REO','ever_D60','ever_D90','ever_in_foreclosure_or_REO']]
delinquency_status['year'] = delinquency_status['Reporting Period Date'].dt.year

agg_dict = {'D60':'max',
            'D90':'max',
            'in_foreclosure_or_REO':'max',
            'ever_D60':'max',
            'ever_D90':'max',
            'ever_in_foreclosure_or_REO':'max'}

delinquency_status = delinquency_status.groupby(['Loan Number','year']).agg(agg_dict).reset_index()

# Update delinquency fields so that D60 >= D90 >= foreclosed/REO at all timepoints.
delinquency_status['D60'] = (delinquency_status['D60'] + delinquency_status['D90'] + delinquency_status['in_foreclosure_or_REO']).clip(upper=1)
delinquency_status['D90'] = (delinquency_status['D90'] + delinquency_status['in_foreclosure_or_REO']).clip(upper=1)
delinquency_status['ever_D60'] = (delinquency_status['ever_D60'] + delinquency_status['ever_D90'] + delinquency_status['ever_in_foreclosure_or_REO']).clip(upper=1)
delinquency_status['ever_D90'] = (delinquency_status['ever_D90'] + delinquency_status['ever_in_foreclosure_or_REO']).clip(upper=1)

# Attach to panel data
panel = pd.merge(panel,delinquency_status,on=['Loan Number','year'],how='left')

# Also attach information on realized losses
panel = pd.merge(panel,losses[['Loan Number','year','realizedloss','loss_rate']],on=['Loan Number','year'],how='left')

### *** PROPERTY FINANCIALS *** ###

# Get year-end operating statements 
# (drop the small small percentage that have non-standard reporting periods)
operating_statements = operating_statements[operating_statements['statement_ending_date'].dt.month == 12]
operating_statements['year'] = operating_statements['statement_ending_date'].dt.year
operating_statements = operating_statements.drop_duplicates(subset=['Loan Number','year'])

operating_statements['occ'] = operating_statements['occupancy_rate']
operating_statements['rev'] = operating_statements['effective_gross_income']
operating_statements['exp'] = operating_statements['total_operating_expenses']
operating_statements['noi'] = operating_statements['rev'] - operating_statements['exp']

prop_financials = operating_statements[['Loan Number','year','occ','rev','exp','noi']]

# Attach to panel data
panel = pd.merge(panel,prop_financials,on=['Loan Number','year'],how='left')

# Filter panel by years included in study period
study_period_mask = (panel['year'] >= 1998)&(panel['year'] <= 2025)
panel = panel[study_period_mask].reset_index(drop=True)

### *** REMAINING YEARS TO MATURITY *** ###

remaining_maturity = loans[['Loan Number','Reporting Period Date','maturitydate']]
remaining_maturity['year'] = remaining_maturity['Reporting Period Date'].dt.year
remaining_maturity['matyear'] = remaining_maturity['maturitydate'].dt.year
remaining_maturity['remainingterm'] = (remaining_maturity['matyear'] - remaining_maturity['year']).clip(0,None).astype('int64[pyarrow]')
remaining_maturity = remaining_maturity.drop_duplicates(subset=['Loan Number','year'])
remaining_maturity = remaining_maturity[['Loan Number','year','remainingterm']]

panel = pd.merge(panel,remaining_maturity,on=['Loan Number','year'],how='left')

### *** LOAN MODIFICATIONS / WORKOUTS *** ###

modifications = loans[['Loan Number','Most Recent Modification Date']].dropna()
modifications['year'] = modifications['Most Recent Modification Date'].dt.year
modifications = modifications.drop(columns=['Most Recent Modification Date']).drop_duplicates()
modifications['modification_flag'] = 1

panel = pd.merge(panel,modifications[['Loan Number','year','modification_flag']],on=['Loan Number','year'],how='left')
panel['modification_flag'] = panel['modification_flag'].fillna(0).astype('Int64[pyarrow]')

### *** LOAN LIQUIDATIONS / PREPAYMENTS *** ###

payoffs = loans[['Loan Number','Reporting Period Date','zero_balance_flag','defeased_released_flag']]
mask = (payoffs['zero_balance_flag']==1)|(payoffs['defeased_released_flag']==1)
payoffs = payoffs[mask]

payoffs['year'] = payoffs['Reporting Period Date'].dt.year

agg_dict = {'zero_balance_flag':'max',
            'defeased_released_flag':'max'}

payoffs = payoffs.groupby(['Loan Number','year']).agg(agg_dict).reset_index()

panel = pd.merge(panel,payoffs,on=['Loan Number','year'],how='left')
panel['zero_balance_flag'] = panel['zero_balance_flag'].fillna(0)
panel['defeased_released_flag'] = panel['defeased_released_flag'].fillna(0)

### *** ATTACH BUILDING ATTRIBUTES *** ###

# Load buildings
buildings_path = os.path.join(project_root,'fannie_mae/geocoding/property_geospatial_data/matched_buildings')
buildings = gpd.read_parquet(buildings_path).set_geometry('point_geometry').to_crs(config['gis_params']['geographic_crs'])
buildings = buildings.rename(columns={'loan_number':'Loan Number'})
buildings = buildings.sort_values(by=['Loan Number','direct_match','SQMETERS'],ascending=False)

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

building_attributes = buildings.groupby('Loan Number').agg(agg_dict)

building_attributes['FEMA_500y_floodplain_indicator'] = ((building_attributes['FEMA_500y_floodplain_indicator']==1)&(building_attributes['FEMA_100y_floodplain_indicator']==0)).astype(int)
building_attributes['floodzone'] = pd.from_dummies(building_attributes[['FEMA_100y_floodplain_indicator','FEMA_500y_floodplain_indicator']],default_category='outside_FEMA_floodplains')
building_attributes['floodzone'] = building_attributes['floodzone'].str.replace('_indicator','')
building_attributes['lumped_floodzone'] = building_attributes['floodzone'].apply(lambda x: 'inside_FEMA_floodplains' if x != 'outside_FEMA_floodplains' else x)

building_attributes = building_attributes.rename(columns={'BUILD_ID':'num_structures'}).reset_index()

panel = pd.merge(panel,building_attributes,on='Loan Number',how='inner')

# Create 0.1 x 0.1 degree lat/lon gridcell identifier
panel['gridcell'] = panel['latitude'].apply(lambda x: f'{x:0.1f}') + ',' + panel['longitude'].apply(lambda x: f'{x:0.1f}')

### *** ATTACH COUNTY METRO AREA GROUPINGS *** ###

metro_areas_path = os.path.join(project_root,'create_panel/metro_areas/county_metro_area_groupings.parquet')
metro_areas = gpd.read_parquet(metro_areas_path).rename(columns={'GEOID':'countyfips_2022'})
metro_areas = metro_areas[['countyfips_2022','csa_code','csa_title','cbsa_code','cbsa_title','cbsa_type']]

panel = pd.merge(panel,metro_areas,on='countyfips_2022',how='left')

# Drop properties located in areas outside CBSAs
panel = panel.dropna(subset=['cbsa_code']).reset_index(drop=True)

### *** SAVE RESULTS *** ###

# Rename columns
rename_dict = {'zcta_2020':'zipcode',
               'Loan Number':'loanid',
               'Note Date':'origdate',
               'Original UPB':'origloanbal',
               'Property ID':'propid',
               'Property Name':'propname',
               'Property Address':'address',
               'Property City':'city',
               'Property State':'state',
               'Property Zip Code':'zip',
               'Property Specific Property Type':'proptype',
               'Property Total Units':'units'}

panel.rename(columns=rename_dict, inplace=True)

# Reorder columns
columns = ['loanid',
           'year',
           'first_obs',
           'last_obs',
           'origdate',
           'origloanbal',
           'maturitydate',
           'vintage',
           'propid',
           'proptype',
           'units',
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
           'remainingterm',
           'zero_balance_flag',
           'defeased_released_flag',
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

panel = panel[columns]

# Save to file
outname = os.path.join(pwd,'panel_outcome_data_fannie.parquet')
panel.to_parquet(outname)

### *** PRINT SUMMARY FOR USER *** ###

num_loans = len(panel['loanid'].unique())
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