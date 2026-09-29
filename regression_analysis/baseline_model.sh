#!/bin/bash

#SBATCH -p general
#SBATCH -N 1
#SBATCH -n 8
#SBATCH --mem=200g
#SBATCH -t 2-00:00:00
#SBATCH --mail-type=all
#SBATCH --job-name=baseline_model
#SBATCH --mail-user=kieranf@email.unc.edu
#SBATCH --array=0,1

module purge
module load r/4.5.0

# List of property types
PROPTYPES=("MF" "RT" "OF" "IN" "LO")

# Specific property type to run
PROPTYPE=${PROPTYPES[$SLURM_ARRAY_TASK_ID]}

# Number of bootstrap replicates drawn when computing SEs
NBOOT=200

# Base case
Rscript baseline_model.R "zipcode_base_case" "both" "lumped_floodzone" $PROPTYPE $NBOOT
Rscript postprocess_baseline_model.R "zipcode_base_case" "both" "lumped_floodzone" $PROPTYPE

# Subset to floodplain
Rscript baseline_model.R "zipcode_base_case" "inside" "floodzone" $PROPTYPE $NBOOT
Rscript postprocess_baseline_model.R "zipcode_base_case" "inside" "floodzone" $PROPTYPE

# Shorter duration
Rscript baseline_model.R "zipcode_shorter_duration" "both" "lumped_floodzone" $PROPTYPE $NBOOT
Rscript postprocess_baseline_model.R "zipcode_shorter_duration" "both" "lumped_floodzone" $PROPTYPE

# Higher threshold
Rscript baseline_model.R "zipcode_higher_threshold" "both" "lumped_floodzone" $PROPTYPE $NBOOT
Rscript postprocess_baseline_model.R "zipcode_higher_threshold" "both" "lumped_floodzone" $PROPTYPE
