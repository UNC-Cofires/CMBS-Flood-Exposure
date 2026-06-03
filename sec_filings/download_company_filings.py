import numpy as np
import pandas as pd
import requests
import time
import os
import sqlite3
from tqdm import tqdm
from src.utils.config import find_project_root, load_config

### *** HELPER FUNCTIONS *** ###

def download_filing(file_url,user_agent):
    """
    This function downloads company filings from SEC EDGAR and saves 
    the result as a plain text file. 

    param: file_url: URL of submission (usually sourced from index files). 
    param: user_agent: parameter used to identify user when querying EDGAR API
    returns: success_status: bool denoting whether download was successful or not.
    returns: content: plain text representation of filing document
    """
    # Initialize status variable
    success_status = False

    # Need to specify user-agent in header when accessing EDGAR via API
    headers = {'User-Agent':user_agent}
    sleep_seconds = 0.1

    # Attempt to donwload file
    res = requests.get(file_url,headers=headers)
    time.sleep(sleep_seconds)

    # If it worked, save result to file
    if res.ok:

        try:
            content = res.text
            success_status = True
            
        except:
            content = None

    else:
        content = None

    return success_status,content

def initialize_database(db_path):
    """
    Creates the SQLite database, the main filings table, and the FTS5
    search index. Safe to re-run — uses CREATE IF NOT EXISTS throughout.

    param db_path: Full path where the .db file should be created.
    returns:       Open sqlite3 connection.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # --- Performance settings ---
    cursor.execute('PRAGMA journal_mode=WAL')     # Better write concurrency
    cursor.execute('PRAGMA synchronous=NORMAL')   # Faster writes, still safe
    cursor.execute('PRAGMA cache_size=-64000')    # 64MB page cache

    # --- Main filings table ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS filings (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            cik              TEXT,
            company_name     TEXT,
            form_type        TEXT,
            date_filed       TEXT,
            accession_number TEXT UNIQUE,
            file_name        TEXT,
            file_url         TEXT,
            download_status  INTEGER DEFAULT 0,
            content          TEXT
        )
    ''')

    # Index on CIK for fast filtering by trust
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cik ON filings(cik)')

    # Index on download_status for efficiently finding pending downloads
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_status ON filings(download_status)'
    )

    # --- FTS5 virtual table ---
    # 'content=filings' means FTS5 reads text from the filings table
    # rather than storing a second copy, saving significant disk space.
    cursor.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS filings_fts
        USING fts5(content, content=filings, content_rowid=id)
    ''')

    conn.commit()
    print(f"Database initialized at: {db_path}")
    return conn

def insert_metadata(conn, index_df):
    """
    Inserts filing metadata from the index dataframe into the database.
    Rows with duplicate accession numbers are silently skipped, so this
    is safe to call more than once.

    param conn:     Open sqlite3 connection.
    param index_df: CMBS index dataframe (with Accession Number and File URL
                    columns already derived).
    """
    cursor = conn.cursor()

    records = [
        (
            row['CIK'],
            row['Company Name'],
            row['Form Type'],
            row['Date Filed'].strftime('%Y-%m-%d') if pd.notna(row['Date Filed']) else None,
            row['Accession Number'],
            row['File Name'],
            row['File URL'],
            0  # download_status: 0 = not yet downloaded
        )
        for _, row in index_df.iterrows()
    ]

    cursor.executemany('''
        INSERT OR IGNORE INTO filings
            (cik, company_name, form_type, date_filed, accession_number,
             file_name, file_url, download_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', records)

    conn.commit()
    print(f"Metadata loaded: {cursor.rowcount} new rows inserted "
          f"({len(records)} total rows in index).")

    return None

def download_all_filings(conn, user_agent, batch_size=500):
    """
    Downloads all pending filings and stores their content in the database.
    Only fetches rows where download_status = 0, so it is safe to re-run
    to resume an interrupted download session.

    param conn:       Open sqlite3 connection.
    param user_agent: Identifier string for the EDGAR API.
    param batch_size: Number of rows to commit per transaction. Larger
                      values are faster but lose more progress if interrupted.
    """
    cursor = conn.cursor()

    cursor.execute('SELECT id, file_url FROM filings WHERE download_status = 0')
    pending = cursor.fetchall()

    if not pending:
        print("No pending filings to download.")
        return

    print(f"Downloading {len(pending)} filings...")

    batch = []
    failed_ids = []
    n_success = 0

    for filing_id, file_url in tqdm(pending, desc="Downloading"):
        success, content = download_filing(file_url, user_agent)

        if success:
            batch.append((content, 1, filing_id))
            n_success += 1
        else:
            # Leave download_status = 0 so this filing is retried next run
            failed_ids.append(filing_id)

        # Commit in batches to avoid losing all progress if interrupted
        if len(batch) >= batch_size:
            cursor.executemany(
                'UPDATE filings SET content = ?, download_status = ? WHERE id = ?',
                batch
            )
            conn.commit()
            batch = []

    # Commit any remaining rows in the final partial batch
    if batch:
        cursor.executemany(
            'UPDATE filings SET content = ?, download_status = ? WHERE id = ?',
            batch
        )
        conn.commit()

    print(f"\nDownload session complete.")
    print(f"  Successful : {n_success}")
    print(f"  Failed     : {len(failed_ids)}")
    if failed_ids:
        print(f"  Re-run download_all_filings() to retry failed downloads.")

    return None

def rebuild_fts_index(conn):
    """
    Rebuilds the FTS5 full-text search index from the current content in
    the filings table. Should be called after all (or a large batch of)
    downloads are complete. Rebuilding in bulk is much faster than
    updating the index row-by-row during downloads.

    param conn: Open sqlite3 connection.
    """
    cursor = conn.cursor()
    print("Rebuilding FTS5 index (this may take a moment for >50k documents)...")
    cursor.execute("INSERT INTO filings_fts(filings_fts) VALUES('rebuild')")
    conn.commit()
    print("FTS5 index rebuilt successfully.")

    return None

### *** INITIAL SETUP *** ###

# Determine root directory of project and load configuration file
project_root = find_project_root()
config = load_config()

# Get current working directory 
pwd = os.getcwd()

# Load index file
CMBS_index_file_path = os.path.join(pwd,'EDGAR/index_files/clean/CMBS_trusts_index_file.parquet')
CMBS_index_file = pd.read_parquet(CMBS_index_file_path)

### *** INITIALIZE DATABASE *** ###

# Create additional columns we'll use when accessing filings
CMBS_index_file['Accession Number'] = CMBS_index_file['File Name'].apply(lambda x: x.split('/')[-1].split('.txt')[0])
CMBS_index_file['File URL'] = 'https://www.sec.gov/Archives/' + CMBS_index_file['File Name']

# Drop duplicate filings (should be small number)
CMBS_index_file = CMBS_index_file.drop_duplicates(subset=['Accession Number']).reset_index(drop=True)

# Adjust column order
CMBS_index_file = CMBS_index_file[['CIK','Company Name','Form Type','Date Filed','Accession Number','File Name','File URL']]

# Create database if it doesn't already exist
outfolder = os.path.join(pwd,'EDGAR/company_filings')
os.makedirs(outfolder,exist_ok=True)
db_path = os.path.join(outfolder,'cmbs_filings.db')
conn = initialize_database(db_path)

# Copy metadata from index file into database if an entry doesn't already exist
insert_metadata(conn, CMBS_index_file)

### *** DOWNLOAD FILINGS *** ###

# Must populate user agent parameter with name and email when querying EDGAR API
user_agent = config['api_info']['edgar_user_agent']

# Download filings into database using EDGAR API
# (Call function multiple times since some will fail on the first pass)
print('Pass #1',flush=True)
download_all_filings(conn, user_agent)
print('Pass #2',flush=True)
download_all_filings(conn, user_agent)
print('Pass #3',flush=True)
download_all_filings(conn, user_agent)

# Build the FTS5 search index for fast lookup of keywords in database
rebuild_fts_index(conn)

conn.close()
print("Done!")