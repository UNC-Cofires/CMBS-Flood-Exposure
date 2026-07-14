import numpy as np
import pandas as pd
import requests
import time
import os
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
outfolder = os.path.join(pwd,'geocoding_output')
os.makedirs(outfolder,exist_ok=True)
output_data_path = os.path.join(outfolder,'geocoding_output_here_api.parquet')

# Specify chunk size (e.g., save progress every 100 addresses)
CHUNK_SIZE=100

### *** LOAD DATA *** ###

# Addresses to geocode
address_data_path = os.path.join(pwd,'geocoding_input/addresses_to_geocode.parquet')
address_data = pd.read_parquet(address_data_path)
num_addresses = len(address_data)

# Previously-geocoded addresses
if os.path.exists(output_data_path):
    output_data = pd.read_parquet(output_data_path)
    
    # Remove addresses that have already been geocoded
    address_data = pd.concat([address_data,output_data[address_data.columns]]).drop_duplicates(keep=False)
else:
    output_data = None

### *** GEOCODE PROPERTY ADDRESSES *** ###

while len(address_data) > 0:

    # Process chunk of data
    batch = address_data.iloc[:CHUNK_SIZE]

    geocode_list = []
    
    for index, row in batch.iterrows():
            
        geocode_result = geocode_address_using_here_api(row['query_string'],API_KEY)
        geocode_result = dict(row) | geocode_result
        geocode_list.append(geocode_result)
    
    processed_batch = pd.DataFrame(geocode_list)
    
    # Save results
    if output_data is not None:
        output_data = pd.concat([output_data,processed_batch])
    else:
        output_data = processed_batch
    
    output_data.to_parquet(output_data_path)

    # Update list of remaining addresses
    address_data = address_data.iloc[CHUNK_SIZE:]
    
    # Print update
    num_processed = len(output_data)
    percent_processed = 100*(num_processed / num_addresses)
    num_remaining = len(address_data)
    print(f'Number of addresses geocoded: {num_processed} / {num_addresses} ({percent_processed:.2f}%). Number remaining: {num_remaining}',flush=True)

print('Geocoding complete.',flush=True)