import numpy as np
import pandas as pd
import datetime as dt
import os
import time
import mediacloud.api
from src.utils.config import find_project_root, load_config

### *** HELPER FUNCTIONS *** ###

def query_mediacloud(query_string,start_date,end_date,collection_ids,api_key,max_retries=5,base_delay=1.0):
    """
    This function performs a news media search using the mediacloud API. 
    Documentation available at: https://www.mediacloud.org/ and https://github.com/mediacloud

    param: query_string: string representation of keyword search (e.g., '(flood* OR hurricane) AND damage*')
    param: start_date: start date of publication range
    param: end_date: end_date of publication range
    param: collection_ids: list of news media collection ids (e.g., [38381390] for North Carolina State and Local News)
    param: api_key: API key associated with your mediacloud account
    param: max_retries: number of times to retry downloading data
    param: base_delay: default backoff time (increases exponentially with number of failed attempts) 
    """

    # Initialize API search object
    search_api = mediacloud.api.SearchApi(api_key)

    # Fetch list of all stories matching query published during date range
    all_stories = []
    more_stories = True
    pagination_token = None
    
    while more_stories:

        attempt = 0

        try:
            
            page, pagination_token = search_api.story_list(query_string, start_date, end_date,
                                                           collection_ids=collection_ids,
                                                           pagination_token=pagination_token)
            all_stories += page
            more_stories = pagination_token is not None
            time.sleep(base_delay*(2**attempt))
            
        except Exception as e:
            
            attempt += 1

            if attempt >= max_retries:
                raise # Give up after reaching maximum number of retries
            else:
                time.sleep(base_delay*(2**attempt))
            
    # Return result as dataframe
    df = pd.DataFrame(all_stories)

    # Pause between function calls
    time.sleep(base_delay)
    
    return(df)

### *** INITIAL SETUP *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

# Get current working directory 
pwd = os.getcwd()

# Create folder for output
outfolder = os.path.join(pwd,'search_results')
os.makedirs(outfolder,exist_ok=True)

### *** CONSTRUCT QUERY *** ###

# Get API key
api_key = config['api_info']['mediacloud_api_key']

# Specify ids of collections to use
USA_STATE_LOCAL = 38379429
USA_NATIONAL = 34412234
collection_ids = [USA_STATE_LOCAL,USA_NATIONAL]

# Specify query string
query_string = '(flood* OR hurricane OR "tropical cyclone" OR "tropical storm") AND damage*'

# Break downloads into chunks by month
periods = pd.period_range('2008-01','2026-05',freq='M')

# Exclude months that we've already downloaded
previous_downloads = [x[:7] for x in os.listdir(outfolder) if x.endswith('.parquet')]
periods = [p for p in periods if str(p) not in previous_downloads]

### *** FETCH RESULTS *** ###

print(f'Mediacloud search string: {query_string}\n',flush=True)

for period in periods:

    start_date = period.start_time.date()
    end_date = period.end_time.date()
    period_string = period.strftime('%Y-%m')

    try: 

        df = query_mediacloud(query_string,start_date,end_date,collection_ids,api_key)
        num_results = len(df)
    
        outname = os.path.join(outfolder,f'{period_string}_search_results.parquet')
        df.to_parquet(outname)
    
        print(f'Fetched {num_results} stories published in {period_string}.',flush=True)
        
    except:
        
        print(f'Failed to fetch results for {period_string}.',flush=True)