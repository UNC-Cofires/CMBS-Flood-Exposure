#!/bin/bash

#SBATCH -N 1
#SBATCH -n 1
#SBATCH --mem=16g
#SBATCH -t 0-12:00:00
#SBATCH -p l40-gpu
#SBATCH --qos=gpu_access
#SBATCH --gres=gpu:1
#SBATCH --job-name=llm_address_parsing
#SBATCH --mail-user=kieranf@email.unc.edu
#SBATCH --mail-type=all

# Load configuration file
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
source "$PROJECT_ROOT/config.sh"

# Load anaconda module
module purge
module load anaconda

# Activate environment
conda activate $LLM_CONDA_ENV_PATH

# Export environment variables used within python script
export HF_HOME=$HF_HOME
export HUGGING_FACE_HUB_TOKEN=$HUGGING_FACE_HUB_TOKEN
export PYTHONWARNINGS="ignore"

# Parse addresses using Qwen3.5-9B
python3.12 parse_address_local_llm.py "Qwen/Qwen3.5-9B"

# Deactivate environment
conda deactivate
