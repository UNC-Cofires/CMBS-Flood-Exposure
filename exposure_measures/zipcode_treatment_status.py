import numpy as np
import pandas as pd
import sys
import os
from src.utils.config import find_project_root, load_config

### *** HELPER FUNCTIONS *** ###

def evaluate_treatment_status(event_timeseries,calendar_time,treatment_duration):
    """
    This function evaluates the treatment status of an individual unit over time in a manner
    that can accomodate repeated treatment and treatment reversal. 

    param: event_timeseries: Binary vector denoting whether an event occurred in each period.
                             (e.g., [0,0,1,0,1,0,0] denotes events occuring in years 3 and 5).
                             Can be a pandas series, numpy array, list, or other array-like object. 
    param: calendar_time: vector denoting specific period of each observation (e.g., [2000,2001,2002,...,2025])
    param: treatment_duration: Number of periods for a which the unit will be marked as "treated" following exposure.
                               After this amount of time has elapsed, the unit will revert to untreated. 
                                
    returns: df: pandas dataframe denoting the unit's time-varying treatment status and the time relative to 
                 treatment onset and cessation. 
    """

    # Calculate number of flood events over previous n years
    event_timeseries = pd.Series(event_timeseries)
    number_of_events = event_timeseries.rolling(window=treatment_duration,min_periods=1,center=False).sum()
    
    # Create indicator for whether more than one event occurred in the past n years
    multiple_events = (number_of_events > 1).astype(int)

    # Create indicator for repetitive treatment event
    repeat_treatment_event = ((event_timeseries == 1)&(multiple_events == 1)).astype(int)
    number_of_repeat_events = repeat_treatment_event.rolling(window=treatment_duration,min_periods=1,center=False).sum()
    
    # Create indicator for whether an event occurred in the past n years. 
    # This is used to determine treatment status. 
    under_treatment = (number_of_events > 0).astype(int)
    under_repeat_treatment = (number_of_repeat_events > 0).astype(int)
    
    # Record the index position where a 1 occurs, NaN everywhere else, then forward fill
    idx_vals = np.arange(len(event_timeseries))
    treatment_event_idx = pd.Series(np.where(event_timeseries == 1, idx_vals, np.nan)).ffill()
    
    # Periods since treatment event (lags)
    time_since_treatment_event = pd.Series(idx_vals) - treatment_event_idx
    
    # Now calculate years preceding treatment event (leads)
    pre_treatment_event_idx = pd.Series(np.where(event_timeseries == 1, idx_vals, np.nan)).bfill()
    time_preceding_treatment_event = pd.Series(idx_vals) - pre_treatment_event_idx

     # Mask lags exceeding treatment duration 
    time_since_treatment_event = time_since_treatment_event.where(time_since_treatment_event < treatment_duration)
    
    # Incorporate into relative time vector
    pre_treatment_mask = time_since_treatment_event.isna()
    time_since_treatment_event[pre_treatment_mask] = time_preceding_treatment_event[pre_treatment_mask]

    # For repeat treatment events, create variable that tracks the time between the most recent event
    # and the previous event
    repeat_treatment_offset = (time_since_treatment_event.shift()+1).where(repeat_treatment_event==1)
    repeat_treatment_offset = repeat_treatment_offset.ffill().where(under_repeat_treatment == 1)
    
    # Write to dataframe
    data = {'calendar_time':calendar_time,
            'treatment_event':event_timeseries,
            'repeat_treatment_event': repeat_treatment_event.to_numpy(),
            'under_treatment':under_treatment.to_numpy(),
            'under_repeat_treatment':under_repeat_treatment.to_numpy(),
            'repeat_treatment_offset':repeat_treatment_offset.to_numpy(),
            'time_since_treatment_event':time_since_treatment_event.to_numpy()}
    
    df = pd.DataFrame(data)

    # Cast as nullable int data type
    df['time_since_treatment_event'] = df['time_since_treatment_event'].astype('int64[pyarrow]')
    df['repeat_treatment_offset'] = df['repeat_treatment_offset'].astype('int64[pyarrow]')

    # Set index as calendar time
    df.set_index('calendar_time',inplace=True)
    
    return df

### *** INITIAL SETUP *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

# Get current working directory
pwd = os.getcwd()

# Create folder for output
outfolder = os.path.join(pwd,'zipcode_exposure')
os.makedirs(outfolder,exist_ok=True)

# Get command-line arguments 
claim_rate_path = sys.argv[1]
claim_rate_threshold = float(sys.argv[2])
treatment_duration = int(sys.argv[3])
scenario_name = sys.argv[4]

# Describe key inputs used to determine treatment status
treatment_description = f'scenario={scenario_name}, claim_rate_threshold={claim_rate_threshold}, treatment_duration={treatment_duration}, claim_rate_path={claim_rate_path}'

# Load data
claim_rate = pd.read_parquet(claim_rate_path).rename(columns={'reportedZipCode':'zipcode'})
claim_rate['claimRate'] = claim_rate['claimRate'].fillna(0)

### *** EVALUATE TREATMENT STATUS *** ###

claim_rate['flood_event'] = (claim_rate['claimRate'] > claim_rate_threshold).astype(int)
treatment_status = claim_rate.groupby('zipcode').apply(lambda x: evaluate_treatment_status(x['flood_event'],x['year'],treatment_duration))
treatment_status = treatment_status.reset_index()
treatment_status['treatment_description'] = treatment_description

### *** SAVE RESULTS *** ###

outname = os.path.join(outfolder,f'zipcode_treatment_status_{scenario_name}.parquet')
treatment_status.to_parquet(outname)

