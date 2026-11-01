#!/bin/bash

#SBATCH -p general
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --mem=16g
#SBATCH -t 0-01:00:00
#SBATCH --mail-type=all
#SBATCH --job-name=combine_parsed
#SBATCH --mail-user=kieranf@email.unc.edu

module purge
module load anaconda

export PYTHONWARNINGS="ignore"
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
source "$PROJECT_ROOT/config.sh"

conda activate $CRE_CONDA_ENV_PATH

python3.12 combine_parsed_address_data.py