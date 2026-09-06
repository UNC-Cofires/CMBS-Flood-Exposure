#!/bin/bash

#SBATCH -p general
#SBATCH -N 1
#SBATCH -n 6
#SBATCH --mem=64g
#SBATCH -t 1-00:00:00
#SBATCH --mail-type=all
#SBATCH --job-name=baseline_model
#SBATCH --mail-user=kieranf@email.unc.edu

module purge
module load r/4.5.0

Rscript baseline_model.R "base_case" "MF" 200
Rscript baseline_model.R "base_case" "RT" 200
Rscript baseline_model.R "base_case" "OF" 200
Rscript baseline_model.R "base_case" "IN" 200
Rscript baseline_model.R "base_case" "LO" 200
