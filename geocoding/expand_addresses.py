import numpy as np
import pandas as pd
import os
import json
from src.utils.config import find_project_root, load_config

### *** HELPER FUNCTIONS *** ###

def is_nonnegative_integer(n):
    """
    Helper function to check if a number is a non-negative integer.
    """
    
    return (isinstance(n,int) and n >= 0)
    
def unabbreviate_range(n1,n2):
    """
    Helper function to fix appreviated ranges
    (e.g., 3351-56 --> 3351-3356). 

    This adjustment will only be performed when the following conditions are true: 
    (1) The second number in the range contains fewer digits than the first
    (2) The second number in the range will be larger than the first if it is "unnabreviated"

    So, 3351-56 will be changed to 3351-3356, but 3351-46 will be left unchanged. 
    """
    
    n1_str = str(n1)
    n2_str = str(n2)
    
    n1_num_digits = len(n1_str)
    n2_num_digits = len(n2_str)
    max_num_digits = max(n1_num_digits,n2_num_digits)
    
    if (n2_num_digits < n1_num_digits) and (max_num_digits > 2):
        n2_candidate = int(n1_str[:-n2_num_digits] + n2_str)
        if n2_candidate > n1:
            n2 = n2_candidate
    
    return n1,n2

def test_increment(first_building_number,last_building_number,increment,max_elements=101):
    """
    This helper function tests whether you can enumerate a range of building numbers in a given
    increment (e.g., 1, 2, 10, 100, etc.) while staying under the number of elements specified
    by max_elements. 
    """

    is_valid = False

    if (first_building_number % increment) == (last_building_number % increment):
        num_elements = 1 + np.abs((last_building_number - first_building_number) / increment)
        if num_elements <= max_elements: 
            is_valid = True

    return is_valid

def format_exact_address(component):
    """
    Helper function to format address components of type "exact"
    """

    building_number = component['first_building_number']
    street = component['street']

    if is_nonnegative_integer(building_number):
        formatted_string = f'{building_number} {street}'
        return [formatted_string]
    else:
        return []

def format_queens_exact_address(component):
    """
    Helper function to format address components of type "queens_exact"
    """

    cross_street = component['cross_street']
    building_number = component['first_building_number']
    street = component['street']

    if is_nonnegative_integer(cross_street) and is_nonnegative_integer(building_number):
        formatted_string = f'{cross_street}-{building_number:02d} {street}'
        return [formatted_string]
    else:
        return []

def format_range_address(component):
    """
    Helper function to format address components of type "range"
    """
    first_building_number = component['first_building_number']
    last_building_number = component['last_building_number']
    street = component['street']

    # Check whether start/end of range are valid building numbers
    if is_nonnegative_integer(first_building_number) and is_nonnegative_integer(last_building_number):
    
        # Check whether we're dealing with an abbreviated range. 
        # If so, it will be "unnabreviated" (e.g., 3351-56 --> 3351-3356)
        first_building_number,last_building_number = unabbreviate_range(first_building_number,last_building_number)
        
        # If the first number in the range is larger, flip the order
        first_building_number,last_building_number = np.sort([first_building_number,last_building_number])
        
        # Check if start and end of range contain a mix of even and odd numbers. 
        # If they're both even or both odd, we'll include only even or only odd numbers in the expanded range. 
        # If one is even and one is odd, we'll include a mix of even/odd numbers in the expanded range. 
        # We do this because building numbers in the United States are typically all even or all odd on 
        # a given side of the street. 
        if (first_building_number % 2) == (last_building_number % 2): 
            smallest_increment = 2
        else:
            smallest_increment = 1
        
        # Test whether we can expand this range while staying under the 
        # maximum allowed number of elements. If it doesn't work, try 
        # falling back to larger increments of 10 or 100.
        found_increment = False
        for increment in [smallest_increment,10,100]:
            if test_increment(first_building_number,last_building_number,increment):
                found_increment = True
                break
        
        # If we found an increment that works, expand the building number range
        if found_increment:
            building_numbers = np.arange(first_building_number,last_building_number+1,increment)
        
        # If we couldn't find an increment that works, return either end of range but nothing in between
        else:
            building_numbers = [first_building_number,last_building_number]
        
        # Format strings for each element in range and return result
        return [f'{n} {street}' for n in building_numbers]
        
    else:
        return []

def format_queens_range_address(component):
    """
    Helper function to format address components of type "queens_range"
    """
    cross_street = component['cross_street']
    first_building_number = component['first_building_number']
    last_building_number = component['last_building_number']
    street = component['street']

    # Check whether start/end of range are valid building numbers
    if is_nonnegative_integer(cross_street) and is_nonnegative_integer(first_building_number) and is_nonnegative_integer(last_building_number):
    
        # Check whether we're dealing with an abbreviated range. 
        # If so, it will be "unnabreviated" (e.g., 3351-56 --> 3351-3356)
        first_building_number,last_building_number = unabbreviate_range(first_building_number,last_building_number)
        
        # If the first number in the range is larger, flip the order
        first_building_number,last_building_number = np.sort([first_building_number,last_building_number])
        
        # Check if start and end of range contain a mix of even and odd numbers. 
        # If they're both even or both odd, we'll include only even or only odd numbers in the expanded range. 
        # If one is even and one is odd, we'll include a mix of even/odd numbers in the expanded range. 
        # We do this because building numbers in the United States are typically all even or all odd on 
        # a given side of the street. 
        if (first_building_number % 2) == (last_building_number % 2): 
            smallest_increment = 2
        else:
            smallest_increment = 1
        
        # Test whether we can expand this range while staying under the 
        # maximum allowed number of elements. If it doesn't work, try 
        # falling back to larger increments of 10 or 100.
        found_increment = False
        for increment in [smallest_increment,10,100]:
            if test_increment(first_building_number,last_building_number,increment):
                found_increment = True
                break
        
        # If we found an increment that works, expand the building number range
        if found_increment:
            building_numbers = np.arange(first_building_number,last_building_number+1,increment)
        
        # If we couldn't find an increment that works, return either end of range but nothing in between
        else:
            building_numbers = [first_building_number,last_building_number]
        
        # Format strings for each element in range and return result
        return [f'{cross_street}-{n:02d} {street}' for n in building_numbers]
        
    else:
        return []

def build_address_list(address_components):
    """
    Helper function to format address components based on their address_type classification. 
    """

    address_list = []

    for component in json.loads(address_components):
    
        if component['address_type'] == 'exact':
            address_list += format_exact_address(component)
        elif component['address_type'] == 'range':
            address_list += format_range_address(component)
        elif component['address_type'] == 'queens_exact':
            address_list += format_queens_exact_address(component)
        elif component['address_type'] == 'queens_range':
            address_list += format_queens_range_address(component)
        else:
            address_list += []

    return address_list

### *** INITIAL SETUP *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

# Get current working directory 
pwd = os.getcwd()

# Specify path to parsed address data
address_dir = os.path.join(pwd,'geocoding_input')
address_data_path = os.path.join(address_dir,'filtered_loans_parsed_address_data.parquet')
address_data = pd.read_parquet(address_data_path)

# Get starting number of loans
starting_num_loans = len(address_data['masterloanidtrepp'].unique())

### *** CREATE BUILDING-LEVEL ADDRESS LIST *** ###

# Expand range-type address components into list
address_data['parsed_address'] = address_data['address_components'].apply(build_address_list)
address_data.drop(columns=['address_components'],inplace=True)

# Create one row for each potential building address associated with loans
address_data = address_data.explode('parsed_address')

# Drop loans whose parsed address is NA. 
# This will occur if the address_type is "approximate" (e.g., "Corner of Main Street and Oak Blvd")
address_data = address_data[~address_data['parsed_address'].isna()].drop_duplicates().reset_index(drop=True)

# Add informaation on city, state, and zip to string that we'll pass to the geocoder
address_data['query_string'] = address_data.apply(lambda x: f'{x['parsed_address']}, {x['city']}, {x['state']} {x['zip']}',axis=1)

# Check how how many loans / addresses are in final dataset
final_num_loans = len(address_data['masterloanidtrepp'].unique())
num_addresses = len(address_data)

### *** SAVE RESULTS *** ###

# Print update to console
percent_included = 100*final_num_loans/starting_num_loans
print(f'Number of loans included in set to be geocoded: {final_num_loans} / {starting_num_loans} ({percent_included:.2f}%)')
print(f'Number of potential addresses associated with loans: {num_addresses}')

outname = os.path.join(address_dir,'addresses_to_geocode.parquet')
address_data.to_parquet(outname)