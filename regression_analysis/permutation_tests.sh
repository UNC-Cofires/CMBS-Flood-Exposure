#!/bin/bash

#SBATCH -p general
#SBATCH -N 1
#SBATCH -n 8
#SBATCH --mem=200g
#SBATCH -t 2-00:00:00
#SBATCH --mail-type=all
#SBATCH --job-name=perm_tests
#SBATCH --mail-user=kieranf@email.unc.edu
#SBATCH --array=0,1,2,3

module purge
module load r/4.5.0

# List of property types
PROPTYPES=("GSE-MF" "MF" "RT" "OF")

# Specific property type to run
PROPTYPE=${PROPTYPES[$SLURM_ARRAY_TASK_ID]}

# Spatial permutation test for property financial outcomes
Rscript permutation_test_baseline_model.R --name "base_case" --proptype $PROPTYPE
