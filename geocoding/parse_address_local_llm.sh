#!/bin/bash

#SBATCH -N 1
#SBATCH -n 1
#SBATCH --mem=24g
#SBATCH -t 1-00:00:00
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

# Parse addresses using quantized version of Qwen3.5-9B
python3.12 parse_address_local_llm.py "cyankiwi/Qwen3.5-9B-AWQ-4bit"

# Parse addresses using quantized version of gemma-4-12B-it
python3.12 parse_address_local_llm.py "cyankiwi/gemma-4-12B-it-AWQ-INT4"

# Deactivate environment
conda deactivate
