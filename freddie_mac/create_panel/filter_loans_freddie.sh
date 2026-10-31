#!/bin/bash

#SBATCH -p general
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --mem=250g
#SBATCH -t 1-00:00:00
#SBATCH --mail-type=all
#SBATCH --job-name=filter_loans_freddie
#SBATCH --mail-user=kieranf@email.unc.edu

module purge
module load anaconda

export PYTHONWARNINGS="ignore"
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
source "$PROJECT_ROOT/config.sh"

conda activate $CRE_CONDA_ENV_PATH

python3.12 freddie_trepp_deal_matching.py > deal_matching.txt
python3.12 filter_loans_freddie.py > selection_flow.txt
python3.12 filter_properties_freddie.py