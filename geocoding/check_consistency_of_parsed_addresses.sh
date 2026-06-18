#!/bin/bash

#SBATCH -p general
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --mem=32g
#SBATCH -t 0-06:00:00
#SBATCH --mail-type=all
#SBATCH --job-name=check_consistency
#SBATCH --mail-user=kieranf@email.unc.edu

module purge
module load anaconda

export PYTHONWARNINGS="ignore"
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
source "$PROJECT_ROOT/config.sh"

conda activate $CRE_CONDA_ENV_PATH

python3.12 check_consistency_of_parsed_addresses.py "cyankiwi/Qwen3.5-9B-AWQ-4bit,cyankiwi/gemma-4-12B-it-AWQ-INT4" > consistency_checks.txt

