#!/bin/bash

#SBATCH -p general
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --mem=120g
#SBATCH -t 2-00:00:00
#SBATCH --mail-type=all
#SBATCH --job-name=baseline_model
#SBATCH --mail-user=kieranf@email.unc.edu
#SBATCH --array=2

module purge
module load r/4.5.0

# List of property types
PROPTYPES=("GSE-MF" "MF" "RT" "OF")

# Specific property type to run
PROPTYPE=${PROPTYPES[$SLURM_ARRAY_TASK_ID]}

# Number of bootstrap replicates drawn when computing SEs
NBOOTS=200

# Base case
Rscript baseline_model.R \
--name "base_case" \
--treatment_scenario "zipcode_base_case" \
--floodzones "FEMA_100y_floodplain,FEMA_500y_floodplain" \
--proptype $PROPTYPE \
--nboots $NBOOTS

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

Rscript placebo_test_baseline_model.R --name "base_case_placebo" --proptype $PROPTYPE

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

Rscript placebo_test_baseline_model.R --name "base_case_carryover" --proptype $PROPTYPE

# Placebo test for spillover effects
Rscript baseline_model.R \
--name "base_case_spillover" \
--treatment_scenario "zipcode_base_case" \
--treatment_variable "under_spillover" \
--event_time "time_since_spillover_event" \
--filter_var "under_treatment" \
--filter_val 0 \
--floodzones "FEMA_100y_floodplain,FEMA_500y_floodplain" \
--proptype $PROPTYPE \
--nboots $NBOOTS

Rscript placebo_test_baseline_model.R --name "base_case_spillover" --proptype $PROPTYPE
