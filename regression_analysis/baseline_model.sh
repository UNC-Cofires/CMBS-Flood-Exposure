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
NBOOTS=200

# Base case: SFHA
Rscript baseline_model.R \
--name "base_case_sfha" \
--treatment "zipcode_base_case" \
--floodzones "FEMA_100y_floodplain" \
--proptype $PROPTYPE \
--nboots $NBOOTS

# Base case: Non-SFHA
Rscript baseline_model.R \
--name "base_case_nonsfha" \
--treatment "zipcode_base_case" \
--floodzones "FEMA_500y_floodplain,outside_FEMA_floodplains" \
--proptype $PROPTYPE \
--nboots $NBOOTS

# Gridcell: SFHA
Rscript baseline_model.R \
--name "gridcell_sfha" \
--treatment "gridcell_base_case" \
--floodzones "FEMA_100y_floodplain" \
--proptype $PROPTYPE \
--nboots $NBOOTS

# Gridcell: Non-SFHA
Rscript baseline_model.R \
--name "gridcell_nonsfha" \
--treatment "gridcell_base_case" \
--floodzones "FEMA_500y_floodplain,outside_FEMA_floodplains" \
--proptype $PROPTYPE \
--nboots $NBOOTS
