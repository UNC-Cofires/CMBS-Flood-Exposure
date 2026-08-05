#!/bin/bash

#SBATCH -p general
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --mem=32g
#SBATCH -t 0-01:00:00
#SBATCH --output=logs/render-%j.log
#SBATCH --mail-type=all
#SBATCH --job-name=render_quarto
#SBATCH --mail-user=kieranf@email.unc.edu

module purge

export PYTHONWARNINGS="ignore"
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
source "$PROJECT_ROOT/config.sh"

module load positron/2026.05.2-3

quarto render --to pdf

