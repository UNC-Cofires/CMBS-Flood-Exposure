#!/bin/bash

#SBATCH -p general
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --mem=32g
#SBATCH -t 1-00:00:00
#SBATCH --mail-type=all
#SBATCH --job-name=combine_buildings_parcels
#SBATCH --mail-user=kieranf@email.unc.edu
#SBATCH --array=0-50

module purge
module load anaconda

export PYTHONWARNINGS="ignore"
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
source "$PROJECT_ROOT/config.sh"

conda activate $CRE_CONDA_ENV_PATH

python3.12 combine_buildings_parcels.py