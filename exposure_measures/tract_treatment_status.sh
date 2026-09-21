#!/bin/bash

#SBATCH -p general
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --mem=32g
#SBATCH -t 0-06:00:00
#SBATCH --mail-type=all
#SBATCH --job-name=zipcode_treatment_status
#SBATCH --mail-user=kieranf@email.unc.edu

module purge
module load anaconda

export PYTHONWARNINGS="ignore"
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
source "$PROJECT_ROOT/config.sh"

conda activate $CRE_CONDA_ENV_PATH

python3.12 zipcode_treatment_status.py "NFIP_claim_rate_by_zipcode.parquet" 0.10 5 "base_case"
python3.12 zipcode_treatment_status.py "NFIP_claim_rate_by_zipcode.parquet" 0.20 5 "higher_threshold"
python3.12 zipcode_treatment_status.py "NFIP_claim_rate_by_zipcode.parquet" 0.05 5 "lower_threshold"
python3.12 zipcode_treatment_status.py "NFIP_claim_rate_by_zipcode.parquet" 0.10 10 "longer_duration"
python3.12 zipcode_treatment_status.py "NFIP_claim_rate_by_zipcode.parquet" 0.10 3 "shorter_duration"
