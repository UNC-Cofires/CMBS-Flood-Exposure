library(glue)
library(here)
library(yaml)
library(optparse)
library(jsonlite)
library(arrow)
library(parallelly)
library(dplyr)
library(tidyr)
library(tibble)

# Load user-defined functions
source("imputation_estimators.R")

### *** INITIAL SETUP *** ###

# Get current working directory and project root
pwd <- here::here()
project_root <- dirname(pwd)

# Load configuration file
config_path <- file.path(project_root,"config.yaml")
config <- read_yaml(config_path)

### *** PARSE COMMAND-LINE ARGUMENTS *** ###

# Get name of scenario and property type
option_list <- list(
  make_option("--name", type = "character", default = format(Sys.time(), "%Y-%m-%d_hazard_model")),
  make_option("--proptype", type = "character", default = "MF")
)

# Load full set of user-defined parameters used in model run
params <- parse_args(OptionParser(option_list = option_list))
fitted_dir <- file.path(pwd,glue("fitted_models/{params$name}/{params$proptype}"))
params <- fromJSON(file.path(fitted_dir,"params.json"))

### *** LOAD DATA *** ###

# Data used in estimation sample
panel_data <- readRDS(file.path(fitted_dir,glue("{params$proptype}_data.rds")))

# ATT estimates and bootstrap replicates
D60_res <- readRDS(file.path(fitted_dir,glue("{params$proptype}_D60_survival.rds")))
modification_res <- readRDS(file.path(fitted_dir,glue("{params$proptype}_modification_survival.rds")))
vol_prepay_res <- readRDS(file.path(fitted_dir,glue("{params$proptype}_vol_prepay_survival.rds")))
zero_balance_res <- readRDS(file.path(fitted_dir,glue("{params$proptype}_zero_balance_survival.rds")))
defeasance_res <- readRDS(file.path(fitted_dir,glue("{params$proptype}_defeasance_survival.rds")))

### *** CONDUCT IN-TIME PLACEBO TESTS FOR PRE-TRENDS / CARRYOVER EFFECTS *** ###

# Initialize empty list
placebo_test_results <- list()

# Conduct in-time placebo tests for each outcome
placebo_test_results$D60 <- in_time_placebo_test(D60_res, panel_data, params$cluster_var)
placebo_test_results$modification <- in_time_placebo_test(modification_res, panel_data, params$cluster_var)
placebo_test_results$vol_prepay <- in_time_placebo_test(vol_prepay_res, panel_data, params$cluster_var)
placebo_test_results$zero_balance <- in_time_placebo_test(zero_balance_res, panel_data, params$cluster_var)
placebo_test_results$defeasance <- in_time_placebo_test(defeasance_res, panel_data, params$cluster_var)

### *** SAVE RESULTS *** ###

write(
  toJSON(placebo_test_results, pretty = TRUE, auto_unbox = TRUE),
  file.path(fitted_dir, "placebo_test_in_time.json")
)
