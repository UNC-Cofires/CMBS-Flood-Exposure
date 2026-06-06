#!/bin/bash

#SBATCH -p general
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --mem=8g
#SBATCH -t 3-00:00:00
#SBATCH --mail-type=all
#SBATCH --job-name=search_mediacloud
#SBATCH --mail-user=kieranf@email.unc.edu

module purge
module load anaconda

export PYTHONWARNINGS="ignore"
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
source "$PROJECT_ROOT/config.sh"

conda activate $CONDA_ENVIRONMENT_PATH

python3.12 search_mediacloud.py
