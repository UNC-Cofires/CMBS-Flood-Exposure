#!/bin/bash

#SBATCH -p general
#SBATCH -N 1
#SBATCH -n 8
#SBATCH --mem=150g
#SBATCH -t 3-00:00:00
#SBATCH --mail-type=all
#SBATCH --job-name=baseline_model
#SBATCH --mail-user=kieranf@email.unc.edu

module purge
module load r/4.5.0

# Number of bootstrap replicates drawn when computing SEs
NBOOT=500

# Baseline model - Properties inside FEMA floodplains
Rscript baseline_model.R "base_case" "inside" "MF" $NBOOT
Rscript baseline_model.R "base_case" "inside" "RT" $NBOOT
Rscript baseline_model.R "base_case" "inside" "OF" $NBOOT
Rscript baseline_model.R "base_case" "inside" "IN" $NBOOT
Rscript baseline_model.R "base_case" "inside" "LO" $NBOOT
Rscript postprocess_baseline_model.R "base_case" "inside" "MF"
Rscript postprocess_baseline_model.R "base_case" "inside" "RT"
Rscript postprocess_baseline_model.R "base_case" "inside" "OF"
Rscript postprocess_baseline_model.R "base_case" "inside" "IN"
Rscript postprocess_baseline_model.R "base_case" "inside" "LO"

# Baseline model - Properties outside FEMA floodplains
Rscript baseline_model.R "base_case" "outside" "MF" $NBOOT
Rscript baseline_model.R "base_case" "outside" "RT" $NBOOT
Rscript baseline_model.R "base_case" "outside" "OF" $NBOOT
Rscript baseline_model.R "base_case" "outside" "IN" $NBOOT
Rscript baseline_model.R "base_case" "outside" "LO" $NBOOT
Rscript postprocess_baseline_model.R "base_case" "outside" "MF"
Rscript postprocess_baseline_model.R "base_case" "outside" "RT"
Rscript postprocess_baseline_model.R "base_case" "outside" "OF"
Rscript postprocess_baseline_model.R "base_case" "outside" "IN"
Rscript postprocess_baseline_model.R "base_case" "outside" "LO"

# Baseline model - All properties inside and outside FEMA floodplains
Rscript baseline_model.R "base_case" "both" "MF" $NBOOT
Rscript baseline_model.R "base_case" "both" "RT" $NBOOT
Rscript baseline_model.R "base_case" "both" "OF" $NBOOT
Rscript baseline_model.R "base_case" "both" "IN" $NBOOT
Rscript baseline_model.R "base_case" "both" "LO" $NBOOT
Rscript postprocess_baseline_model.R "base_case" "both" "MF"
Rscript postprocess_baseline_model.R "base_case" "both" "RT"
Rscript postprocess_baseline_model.R "base_case" "both" "OF"
Rscript postprocess_baseline_model.R "base_case" "both" "IN"
Rscript postprocess_baseline_model.R "base_case" "both" "LO"
