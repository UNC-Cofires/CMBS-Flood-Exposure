import numpy as np
import pandas as pd
import requests
import time
import os
from tqdm import tqdm
from src.utils.config import find_project_root, load_config

### *** HELPER FUCNTIONS *** ###

def geocode_address_using_here_api(query_string,API_KEY,base_delay=0.1,max_attempts=5):
    """
    This function geocodes an address using the HERE geocoding and search API. 
    API documentation available at: https://docs.here.com/geocoding-and-search/docs/geocode

    param: query_string: plain text representation of address to be geocoded (e.g., "27 Rogerson Drive, Chapel Hill, NC 27517") [string]
    param: API_KEY: the API key associated with your HERE platform account [string]
    param: base_delay: number of seconds to pause in between requests (used for rate-limiting) [float]
    param: max_attempts: number of times to re-attempt a failed request (increases delay exponentially) [integer]
    returns: geocoded_result: summary of geocoding output [dict]
    """

    geocoded_result = {'queryString':query_string}

    url = 'https://geocode.search.hereapi.com/v1/geocode'
    params = {'q':query_string,'apiKey':API_KEY}

    num_attempts = 0
    status_code = 0

    while (status_code != 200) and (num_attempts < max_attempts):
        try:
            res = requests.get(url,params=params,timeout=10)
            status_code = res.status_code
        except:
            status_code = 0 # Ensure loop retries
        time.sleep(base_delay*(2**num_attempts)) # Increase delay with each failed attempt
        num_attempts += 1
    
    geocoded_result['statusCode'] = status_code

    if status_code == 200:

        # Get metadata on geocoding response
        try:
            results_dict = res.json()
            geocoded_result['numResults'] = len(results_dict['items'])
            results_dict = results_dict['items'][0]
            geocoded_result['resultType'] = results_dict['resultType']
        except:
            geocoded_result['numResults'] = 0
            geocoded_result['resultType'] = pd.NA
            
        # Extract different address components if present
        try:
            geocoded_result['geocodedAddress'] = results_dict['address']['label']
        except:
            geocoded_result['geocodedAddress'] = pd.NA

        try:
            geocoded_result['geocodedCountryCode'] = results_dict['address']['countryCode']
        except:
            geocoded_result['geocodedCountryCode'] = pd.NA

        try:
            geocoded_result['geocodedStateCode'] = results_dict['address']['stateCode']
        except:
            geocoded_result['geocodedStateCode'] = pd.NA

        try:
            geocoded_result['geocodedCounty'] = results_dict['address']['county']
        except:
            geocoded_result['geocodedCounty'] = pd.NA

        try:
            geocoded_result['geocodedCity'] = results_dict['address']['city']
        except:
            geocoded_result['geocodedCity'] = pd.NA

        try:
            geocoded_result['geocodedStreet'] = results_dict['address']['street']
        except:
            geocoded_result['geocodedStreet'] = pd.NA

        try:
            geocoded_result['geocodedPostalCode'] = results_dict['address']['postalCode']
        except:
            geocoded_result['geocodedPostalCode'] = pd.NA

        try:
            geocoded_result['geocodedHouseNumber'] = results_dict['address']['houseNumber']
        except:
            geocoded_result['geocodedHouseNumber'] = pd.NA

        try:
            geocoded_result['geocodedLatitude'] = results_dict['position']['lat']
        except:
            geocoded_result['geocodedLatitude'] = pd.NA

        try:
            geocoded_result['geocodedLongitude'] = results_dict['position']['lng']
        except:
            geocoded_result['geocodedLongitude'] = pd.NA

        # Extract information on precision of geolocation
        try:
            geocoded_result['houseNumberFallback'] = results_dict['houseNumberFallback']
        except: 
            geocoded_result['houseNumberFallback'] = False

        try:
            geocoded_result['queryScore'] = results_dict['scoring']['queryScore']
        except: 
            geocoded_result['queryScore'] = pd.NA

        try:
            geocoded_result['fieldScoreState'] = results_dict['scoring']['fieldScore']['state']
        except: 
            geocoded_result['fieldScoreState'] = pd.NA

        try:
            geocoded_result['fieldScorePostalCode'] = results_dict['scoring']['fieldScore']['postalCode']
        except: 
            geocoded_result['fieldScorePostalCode'] = pd.NA

        try:
            geocoded_result['fieldScoreStreet'] = results_dict['scoring']['fieldScore']['streets'][0]
        except: 
            geocoded_result['fieldScoreStreet'] = pd.NA

        try:
            geocoded_result['fieldScoreHouseNumber'] = results_dict['scoring']['fieldScore']['houseNumber']
        except: 
            geocoded_result['fieldScoreHouseNumber'] = pd.NA

    return geocoded_result

### *** INITIAL SETUP *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

# Get current working directory 
pwd = os.getcwd()

# Get API key for HERE geocoding API
API_KEY = config['api_info']['here_geocoding_api_key']

# Create folder for output
outfolder = os.path.join(pwd,'here_geocoding_api_output')
os.makedirs(outfolder,exist_ok=True)

# Specify chunk size (e.g., save progress every 1000 addresses)
CHUNK_SIZE=1000

### *** LOAD DATA *** ###

# Addresses to geocode
address_data_path = os.path.join(pwd,'geocoding_input/parsed_loan_addresses.parquet')
address_data = pd.read_parquet(address_data_path)

# Break list of addresses into chunks
address_data['chunk'] = (np.arange(len(address_data)) // CHUNK_SIZE) + 1

# Determine which chunks we've already geocoded
completed_chunks = [x for x in os.listdir(outfolder) if x.endswith('parquet')]
completed_chunks = [int(x.split('.parquet')[0].split('_')[-1]) for x in completed_chunks]

# Keep only those addresses that are not yet geocoded
address_data = address_data[~address_data['chunk'].isin(completed_chunks)]
remaining_chunks = address_data['chunk'].unique()

### *** GEOCODE PROPERTY ADDRESSES *** ###

for chunk_number in tqdm(remaining_chunks,desc='Geocoding chunk'):

    chunk_mask = (address_data['chunk']==chunk_number)

    geocode_list = []

    # Process chunk of data
    for index, row in address_data[chunk_mask].iterrows():
        
        propname = row['propname']
        address = row['parsed_address']
        city = row['city']
        state = row['state']
        zip = row['zip']
        
        query_string = f'{address}, {city}, {state} {zip}'
        
        geocode_result = geocode_address_using_here_api(query_string,API_KEY)
        geocode_result = dict(row) | geocode_result
        geocode_list.append(geocode_result)

    # Assemble into dataframe
    geocode_df = pd.DataFrame(geocode_list).drop(columns='chunk')

    # Save results
    outname = os.path.join(outfolder,f'geocoded_loan_addresses_here_api_chunk_{chunk_number:04d}.parquet')
    geocode_df.to_parquet(outname)