#!/bin/bash

#SBATCH -p general
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --mem=32g
#SBATCH -t 0-06:00:00
#SBATCH --mail-type=all
#SBATCH --job-name=treatment_status
#SBATCH --mail-user=kieranf@email.unc.edu

module purge
module load anaconda

export PYTHONWARNINGS="ignore"
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
source "$PROJECT_ROOT/config.sh"

conda activate $CRE_CONDA_ENV_PATH

# Zipcode-level flood treatment exposure
python3.12 treatment_status.py "NFIP_claim_rate_by_zipcode.parquet" "zipcode" "zcta_neighbors" 0.10 5 "zipcode_base_case"
python3.12 treatment_status.py "NFIP_claim_rate_by_zipcode.parquet" "zipcode" "zcta_neighbors" 0.05 5 "zipcode_lower_threshold"
python3.12 treatment_status.py "NFIP_claim_rate_by_zipcode.parquet" "zipcode" "zcta_neighbors" 0.20 5 "zipcode_higher_threshold"
python3.12 treatment_status.py "NFIP_claim_rate_by_zipcode.parquet" "zipcode" "zcta_neighbors" 0.10 3 "zipcode_shorter_duration"
python3.12 treatment_status.py "NFIP_claim_rate_by_zipcode.parquet" "zipcode" "zcta_neighbors" 0.10 7 "zipcode_longer_duration"

