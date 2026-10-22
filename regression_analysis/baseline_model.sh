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
NBOOTS=500

# Base case: SFHA
Rscript baseline_model.R \
--name "base_case_sfha" \
--treatment_scenario "zipcode_base_case" \
--floodzones "FEMA_100y_floodplain" \
--proptype $PROPTYPE \
--nboots $NBOOTS

Rscript postprocess_baseline_model.R --name "base_case_sfha" --proptype $PROPTYPE

# In-time placebo test for pre-trends: SFHA

Rscript baseline_model.R \
--name "placebo_pretrend_sfha" \
--treatment_scenario "zipcode_base_case" \
--treatment_variable "under_placebo" \
--event_time "time_since_placebo_event" \
--filter_var "under_treatment" \
--filter_val 0 \
--floodzones "FEMA_100y_floodplain" \
--proptype $PROPTYPE \
--nboots $NBOOTS

Rscript postprocess_baseline_model.R --name "placebo_pretrend_sfha" --proptype $PROPTYPE
Rscript placebo_test_in_time.R --name "placebo_pretrend_sfha" --proptype $PROPTYPE

# In-time placebo test for carryover effects: SFHA

Rscript baseline_model.R \
--name "placebo_carryover_sfha" \
--treatment_scenario "zipcode_base_case" \
--treatment_variable "under_carryover" \
--event_time "time_since_carryover_event" \
--filter_var "under_treatment" \
--filter_val 0 \
--floodzones "FEMA_100y_floodplain" \
--proptype $PROPTYPE \
--nboots $NBOOTS

Rscript postprocess_baseline_model.R --name "placebo_carryover_sfha" --proptype $PROPTYPE
Rscript placebo_test_in_time.R --name "placebo_carryover_sfha" --proptype $PROPTYPE

# Test for spatial spillover effects: SFHA

Rscript baseline_model.R \
--name "spillover_sfha" \
--treatment_scenario "zipcode_base_case" \
--treatment_variable "under_spillover" \
--event_time "time_since_spillover_event" \
--filter_var "under_treatment" \
--filter_val 0 \
--floodzones "FEMA_100y_floodplain" \
--proptype $PROPTYPE \
--nboots $NBOOTS

Rscript postprocess_baseline_model.R --name "spillover_sfha" --proptype $PROPTYPE

# Gridcell: SFHA
Rscript baseline_model.R \
--name "gridcell_sfha" \
--treatment_scenario "gridcell_base_case" \
--floodzones "FEMA_100y_floodplain" \
--proptype $PROPTYPE \
--nboots $NBOOTS

Rscript postprocess_baseline_model.R --name "gridcell_sfha" --proptype $PROPTYPE

# Base case: Non-SFHA
Rscript baseline_model.R \
--name "base_case_nonsfha" \
--treatment_scenario "zipcode_base_case" \
--floodzones "FEMA_500y_floodplain,outside_FEMA_floodplains" \
--proptype $PROPTYPE \
--nboots $NBOOTS

Rscript postprocess_baseline_model.R --name "base_case_nonsfha" --proptype $PROPTYPE

# In-time placebo test for pre-trends: Non-SFHA

Rscript baseline_model.R \
--name "placebo_pretrend_nonsfha" \
--treatment_scenario "zipcode_base_case" \
--treatment_variable "under_placebo" \
--event_time "time_since_placebo_event" \
--filter_var "under_treatment" \
--filter_val 0 \
--floodzones "FEMA_500y_floodplain,outside_FEMA_floodplains" \
--proptype $PROPTYPE \
--nboots $NBOOTS

Rscript postprocess_baseline_model.R --name "placebo_pretrend_nonsfha" --proptype $PROPTYPE
Rscript placebo_test_in_time.R --name "placebo_pretrend_nonsfha" --proptype $PROPTYPE

# In-time placebo test for carryover effects: Non-SFHA

Rscript baseline_model.R \
--name "placebo_carryover_nonsfha" \
--treatment_scenario "zipcode_base_case" \
--treatment_variable "under_carryover" \
--event_time "time_since_carryover_event" \
--filter_var "under_treatment" \
--filter_val 0 \
--floodzones "FEMA_500y_floodplain,outside_FEMA_floodplains" \
--proptype $PROPTYPE \
--nboots $NBOOTS

Rscript postprocess_baseline_model.R --name "placebo_carryover_nonsfha" --proptype $PROPTYPE
Rscript placebo_test_in_time.R --name "placebo_carryover_nonsfha" --proptype $PROPTYPE

# Test for spatial spillover effects: Non-SFHA

Rscript baseline_model.R \
--name "spillover_nonsfha" \
--treatment_scenario "zipcode_base_case" \
--treatment_variable "under_spillover" \
--event_time "time_since_spillover_event" \
--filter_var "under_treatment" \
--filter_val 0 \
--floodzones "FEMA_500y_floodplain,outside_FEMA_floodplains" \
--proptype $PROPTYPE \
--nboots $NBOOTS

Rscript postprocess_baseline_model.R --name "spillover_nonsfha" --proptype $PROPTYPE

# Gridcell: Non-SFHA
Rscript baseline_model.R \
--name "gridcell_nonsfha" \
--treatment_scenario "gridcell_base_case" \
--floodzones "FEMA_500y_floodplain,outside_FEMA_floodplains" \
--proptype $PROPTYPE \
--nboots $NBOOTS

Rscript postprocess_baseline_model.R --name "gridcell_nonsfha" --proptype $PROPTYPE
