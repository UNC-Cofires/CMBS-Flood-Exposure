import numpy as np
import pandas as pd
import glob
import json
import os
from python_calamine import CalamineWorkbook
from src.utils.config import find_project_root, load_config

### *** HELPER FUNCTIONS *** ###

def cell_to_index(address: str) -> list[int]:
    """
    Convert an Excel-style cell address (e.g., "A3") 
    to [row, column] zero-based indices.
    """
    
    letters = address.rstrip("0123456789")
    row = int(address[len(letters):])

    col = 0
    for ch in letters.upper():
        col = col * 26 + (ord(ch) - ord("A") + 1)

    return [row - 1, col - 1]

def process_operating_statement_report(path, sheet_name, mapping, last_row=100):
    """
    Extract data on property income and expenses from Fannie Mae operating
    statement analysis report excel workbooks. 

    param: path: path to excel workbook
    param: sheet_name: name of sheet in excel workbook to extract data from
    param: mapping: python dictionary describing layout of line items in operating statement
    param: last_row: maximum number of rows to read into memory
    """
    
    wb = CalamineWorkbook.from_path(path)
    sheet = wb.get_sheet_by_name(sheet_name)
    data = sheet.to_python(skip_empty_area=False, nrows=last_row + 1)
    
    extracted_data = []
    
    row,col = cell_to_index(mapping['asofdate_coord'])
    as_of_date = data[row][col].strip('as of ')
    
    for excel_col in mapping['period_cols']:
    
        period_data = {}
        period_data['as_of_date'] = as_of_date
        
        for attribute_name,excel_row in mapping['outcome_rows'].items():
    
            row,col = cell_to_index(f'{excel_col}{excel_row}')
            period_data[attribute_name] = data[row][col]
    
        extracted_data.append(period_data)
    
    extracted_data = pd.DataFrame(extracted_data)
    date_cols = ['as_of_date','statement_ending_date']
    float_cols = [x for x in extracted_data.columns if x not in date_cols]
    
    for col in date_cols:
        extracted_data[col] = pd.to_datetime(extracted_data[col],errors='coerce',format='%m/%d/%Y').astype('date32[day][pyarrow]')
    
    for col in float_cols:
        extracted_data[col] = pd.to_numeric(extracted_data[col],errors='coerce').astype('double[pyarrow]')

    return extracted_data

def process_transaction(transaction_info,multifamily_excel_mapping,healthcare_excel_mapping):
    """
    Extract and concatenate the operating statement analysis reports from different
    periods for a given Fannie Mae MBS transaction. 

    param: transaction_info: pandas dataframe containing information on operating statements
                             associated with a given transaction. 
    """

    failed_extracts = []
    transaction_data = []
    
    for report_info in transaction_info.to_dict(orient='records'):

        if report_info['Property Specific Property Type']=='Seniors':
            mapping = healthcare_excel_mapping
        else:
            mapping = multifamily_excel_mapping
    
        try:
            data = process_operating_statement_report(report_info['filepath'], report_info['sheet_name'], mapping)
            data['Security Transaction ID'] = report_info['Security Transaction ID']
            data['Loan Number'] = report_info['Loan Number']
            data['Property ID'] = report_info['Property ID']
            data['filepath'] = report_info['filepath']
            data['sheet_name'] = report_info['sheet_name']
            transaction_data.append(data)
            
        except:
            failed_extracts.append(report_info)
    
    if len(transaction_data) > 0:
        transaction_data = pd.concat(transaction_data)
        transaction_data = transaction_data.set_index(['Security Transaction ID','Loan Number', 'Property ID','filepath','sheet_name']).reset_index()

    return(transaction_data,failed_extracts)

### *** INITIAL SETUP *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

# Get current working directory 
pwd = os.getcwd()

# Create folder for output
outfolder = os.path.join(pwd,'operating_statement_data')
if not os.path.exists(outfolder):
    os.makedirs(outfolder)

# Specify filenames for output
data_outname = os.path.join(outfolder,'extracted_data.parquet')
failed_outname = os.path.join(outfolder,'failed_extracts.parquet')
cleaned_outname = os.path.join(outfolder,'fannie_operating_statement_data_clean.parquet')

# Specify batch size
batch_size = 500

### *** LOAD DATA *** ###

# Cell mappings for operating statements
with open('multifamily_operating_statement_excel_mappings.json','r',encoding="utf-8") as f:
    multifamily_excel_mapping = json.load(f)

with open('healthcare_operating_statement_excel_mappings.json','r',encoding="utf-8") as f:
    healthcare_excel_mapping = json.load(f)

# Included Fannie Mae MBS loans
loans = pd.read_parquet('filtered_loans_fannie.parquet')
loans['Property ID'] = loans['Property ID'].astype('int64[pyarrow]') 

filenames = pd.Series(np.sort(os.listdir(config['paths']['fannie_operating_statement_excels'])))
filepaths = filenames.apply(lambda x: os.path.join(config['paths']['fannie_operating_statement_excels'],x))
transaction_ids = filenames.apply(lambda x: x.split(' ')[0])

operating_statement_excels = pd.DataFrame({'Security Transaction ID':transaction_ids,'filepath':filepaths})
operating_statement_excels = operating_statement_excels[operating_statement_excels['Security Transaction ID'].isin(loans['Security Transaction ID'])]
transaction_ids = pd.Series(operating_statement_excels['Security Transaction ID'].unique())

relevant_cols = ['Security Transaction ID',
                 'Security Number of Loans - Issuance',
                 'Security Number of Properties - Issuance',
                 'Loan Number',
                 'Property ID',
                 'Property Specific Property Type']

operating_statement_excels = pd.merge(operating_statement_excels,loans[relevant_cols].drop_duplicates(),how='left',on='Security Transaction ID')
operating_statement_excels['sheet_name'] = operating_statement_excels.apply(lambda x: f'Healthcare {x['Property ID']}' if x['Property Specific Property Type']=='Seniors' else f'Multifamily {x['Property ID']}',axis=1)
operating_statement_excels = operating_statement_excels.groupby('Security Transaction ID')

### *** PROCESS OPERATING STATEMENTS IN BATCHES *** ###

# Each batch is saved to its own files in outfolder/batches. A batch counts as complete
# only once its "_done.parquet" file (the list of transaction IDs it attempted) exists.
# That file is written last, so an interrupted batch is simply redone on the next run.
# When every transaction is done, the batch files are combined into data_outname
# and failed_outname.

batch_folder = os.path.join(outfolder, 'batches')
os.makedirs(batch_folder, exist_ok=True)

# Find which transactions were already attempted in earlier runs
done_files = sorted(glob.glob(os.path.join(batch_folder, 'batch_*_done.parquet')))
completed_ids = set()
for f in done_files:
    completed_ids.update(pd.read_parquet(f)['Security Transaction ID'])

batch_num = max((int(os.path.basename(f).split('_')[1]) for f in done_files), default=-1) + 1
remaining_ids = [t for t in transaction_ids if t not in completed_ids]

print(f'{len(completed_ids)} / {len(transaction_ids)} transactions already processed; '
      f'{len(remaining_ids)} remaining', flush=True)

for start in range(0, len(remaining_ids), batch_size):

    batch_ids = remaining_ids[start:start + batch_size]
    stem = os.path.join(batch_folder, f'batch_{batch_num:05d}')

    # Remove leftover files from an earlier, unfinished attempt at this batch
    for f in glob.glob(stem + '_*.parquet'):
        os.remove(f)

    batch_data_list = []
    batch_failed_list = []

    for transaction_id in batch_ids:
        transaction_info = operating_statement_excels.get_group(transaction_id)
        transaction_data, failed_extracts = process_transaction(
            transaction_info, multifamily_excel_mapping, healthcare_excel_mapping
        )

        if len(transaction_data) > 0:
            batch_data_list.append(transaction_data)
        batch_failed_list.extend(failed_extracts)  # failed_extracts is a list of dicts

    if batch_data_list:
        pd.concat(batch_data_list, ignore_index=True).to_parquet(stem + '_data.parquet')
    if batch_failed_list:
        pd.DataFrame(batch_failed_list).to_parquet(stem + '_failed.parquet')

    # Written last: marks the batch as complete
    pd.DataFrame({'Security Transaction ID': batch_ids}).to_parquet(stem + '_done.parquet')

    completed_ids.update(batch_ids)
    batch_num += 1
    print(f'Processed {len(completed_ids)} / {len(transaction_ids)} transactions', flush=True)

### *** COMBINE BATCHES *** ###

# Only reached once no transactions remain. Re-running after completion just rebuilds the outputs.
done_stems = sorted(f[:-len('_done.parquet')] for f in glob.glob(os.path.join(batch_folder, 'batch_*_done.parquet')))

for suffix, outname in (('_data.parquet', data_outname), ('_failed.parquet', failed_outname)):
    paths = [p for p in (s + suffix for s in done_stems) if os.path.exists(p)]
    if paths:
        combined = pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)
        combined.to_parquet(outname)
        print(f'Wrote {len(combined)} rows to {outname}', flush=True)

### *** CREATE CLEANED VERSION OF DATASET *** ###

cleaned_data = pd.read_parquet(data_outname)

# By default, extraction script tries to extract data from trailing three years from each excel. 
# Sometimes less than three years of data is present (e.g., newly originated loans). 
# Drop rows corresponding to reporting periods with no data, as well as duplicated reports (keeping newest). 
cleaned_data = cleaned_data.dropna(subset=['as_of_date','statement_ending_date'])
cleaned_data = cleaned_data.sort_values(by=['Loan Number','Property ID','as_of_date','statement_ending_date'],ascending=False)
cleaned_data = cleaned_data.drop_duplicates(subset=['Loan Number','Property ID','as_of_date','statement_ending_date'])
cleaned_data = cleaned_data.reset_index(drop=True)
cleaned_data.to_parquet(cleaned_outname)
print(f'Wrote {len(cleaned_data)} rows to {cleaned_outname}', flush=True)