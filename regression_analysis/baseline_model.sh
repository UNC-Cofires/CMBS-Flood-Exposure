#!/bin/bash

#SBATCH -p general
#SBATCH -N 1
#SBATCH -n 8
#SBATCH --mem=200g
#SBATCH -t 2-00:00:00
#SBATCH --mail-type=all
#SBATCH --job-name=baseline_model
#SBATCH --mail-user=kieranf@email.unc.edu
#SBATCH --array=0,1,2,3

module purge
module load r/4.5.0

# List of property types
PROPTYPES=("GSE-MF" "MF" "RT" "OF")

# Specific property type to run
PROPTYPE=${PROPTYPES[$SLURM_ARRAY_TASK_ID]}

# Number of bootstrap replicates drawn when computing SEs
NBOOTS=100

# Base case
Rscript baseline_model.R \
--name "base_case" \
--treatment_scenario "zipcode_base_case" \
--floodzones "FEMA_100y_floodplain,FEMA_500y_floodplain" \
--proptype $PROPTYPE \
--nboots $NBOOTS

Rscript postprocess_baseline_model.R --name "base_case" --proptype $PROPTYPE

# Placebo test for pre-trends
Rscript baseline_model.R \
--name "base_case_placebo" \
--treatment_scenario "zipcode_base_case" \
--treatment_variable "under_placebo" \
--event_time "time_since_placebo_event" \
--filter_var "under_treatment" \
--filter_val 0 \
--floodzones "FEMA_100y_floodplain,FEMA_500y_floodplain" \
--proptype $PROPTYPE \
--nboots $NBOOTS

Rscript postprocess_baseline_model.R --name "base_case_placebo" --proptype $PROPTYPE
Rscript placebo_test_in_time.R --name "base_case_placebo" --proptype $PROPTYPE

# Placebo test for carryover effects
Rscript baseline_model.R \
--name "base_case_carryover" \
--treatment_scenario "zipcode_base_case" \
--treatment_variable "under_carryover" \
--event_time "time_since_carryover_event" \
--filter_var "under_treatment" \
--filter_val 0 \
--floodzones "FEMA_100y_floodplain,FEMA_500y_floodplain" \
--proptype $PROPTYPE \
--nboots $NBOOTS

Rscript postprocess_baseline_model.R --name "base_case_carryover" --proptype $PROPTYPE
Rscript placebo_test_in_time.R --name "base_case_carryover" --proptype $PROPTYPE

# Spatial permutation test
Rscript permutation_test_in_space.R --name "base_case" --proptype $PROPTYPE
