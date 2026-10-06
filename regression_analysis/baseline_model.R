library(glue)
library(here)
library(yaml)
library(optparse)
library(jsonlite)
library(arrow)
library(parallelly)
library(dplyr)
library(panelView)
library(fect)

### *** INITIAL SETUP *** ###

# Get current working directory and project root
pwd <- here::here()
project_root <- dirname(pwd)

# Load configuration file
config_path <- file.path(project_root,"config.yaml")
config <- read_yaml(config_path)

# Get number of available cores
num_cores <- availableCores()

### *** PARSE COMMAND-LINE ARGUMENTS *** ###

option_list <- list(
  make_option("--name", type = "character", default = format(Sys.time(), "%Y-%m-%d_model_run")),
  make_option("--treatment", type = "character", default = "zipcode_base_case"),
  make_option("--floodzones", type = "character", default = "FEMA_100y_floodplain,FEMA_500y_floodplain"),
  make_option("--groupatt", type = "character", default = NULL),
  make_option("--proptype", type = "character", default = "MF"),
  make_option("--nboots",    type = "integer",   default = 200)
)

params <- parse_args(OptionParser(option_list = option_list))

# Create folder for output
outfolder <- file.path(pwd,glue("fitted_models/{params$name}/{params$proptype}"))
dir.create(outfolder,recursive=TRUE)

# Save command-line arguments as JSON
write(
  toJSON(params, pretty = TRUE, auto_unbox = TRUE),
  file.path(outfolder, "params.json")
)

### *** LOAD DATA *** ###

# Longitudinal data on property financial outcomes
panel_data_path <- file.path(project_root,"create_panel/panel_outcome_data.parquet")
panel_data <- read_parquet(panel_data_path)

# Neighborhood-level treatment status
treatment_status_dir <- file.path(project_root,"exposure_measures/treatment_status")
treatment_status_filename <- glue("{params$treatment}_treatment_status.parquet")
treatment_status_path <- file.path(treatment_status_dir,treatment_status_filename)
treatment_status <- read_parquet(treatment_status_path)
treatment_status <- treatment_status %>% rename(year = calendar_time)

# Get geographic unit at which treatment is assigned
geog_unit <- colnames(treatment_status)[1]

# Merge outcome and treatment status data
panel_data <- left_join(panel_data, treatment_status, by = c(geog_unit,"year"))

### *** LOG-TRANSFORM PROPERTY CASHFLOW MEAURES *** ###

# In rare cases, financial metrics like NOI can be negative.
# This is incompatible with a log-linear model specification. 
# To address this problem, truncate NOI at a minimum of $1 so 
# that we can still apply a log transformation.
panel_data$log_rev <- log(pmax(panel_data$rev,1))
panel_data$log_exp <- log(pmax(panel_data$exp,1))
panel_data$log_noi <- log(pmax(panel_data$noi,1))

### *** CREATE INDICATORS FOR MISSING FINANCIAL METRICS *** ###

panel_data$missing_rev <- as.integer(is.na(panel_data$rev))
panel_data$missing_exp <- as.integer(is.na(panel_data$exp))
panel_data$missing_noi <- as.integer(is.na(panel_data$noi))
panel_data$missing_occ <- as.integer(is.na(panel_data$occ))

### *** CREATE INTERACTION VARIABLES *** ###

# Region x Time
panel_data$region_time <- interaction(panel_data$cbsa_title, panel_data$year)

# Vintage x Time
panel_data$vintage_time <- interaction(panel_data$vintage, panel_data$year)

### *** FILTER AND SUBSET DATA *** ###

# Flood zone
included_floodzones <- strsplit(params$floodzones,",")[[1]]
floodzone_mask <- (panel_data$floodzone %in% included_floodzones)
panel_data <- panel_data[floodzone_mask,]

# Property type
proptype_mask <- (panel_data$cssaproptype == params$proptype)
panel_data <- panel_data[proptype_mask,]

# Save input data
saveRDS(panel_data, file=file.path(outfolder,glue("{params$proptype}_data.rds")))

### *** FIT MODELS *** ###

## 60-day delinquency
D60_mod <- fect(D60 ~ under_treatment, data = panel_data, group = params$groupatt,
                index = c("masterloanidtrepp","year","region_time"),
                method = "cfe", force = "two-way", r=0, min.T0 = 1,
                se = TRUE, loo = TRUE, parallel = TRUE, cores = num_cores, 
                nboots = params$nboots, keep.sims = TRUE)

saveRDS(D60_mod, file=file.path(outfolder,glue("{params$proptype}_D60_mod.rds")))

## Net operating income
noi_mod <- fect(log_noi ~ under_treatment, data = panel_data, group = params$groupatt,
                index = c("masterloanidtrepp","year","region_time"),
                method = "cfe", force = "two-way", r=0, min.T0 = 1,
                se = TRUE, loo = TRUE, parallel = TRUE, cores = num_cores, 
                nboots = params$nboots, keep.sims = TRUE)

saveRDS(noi_mod, file=file.path(outfolder,glue("{params$proptype}_noi_mod.rds")))

## Occupancy
occ_mod <- fect(occ ~ under_treatment, data = panel_data, group = params$groupatt,
                index = c("masterloanidtrepp","year","region_time"),
                method = "cfe", force = "two-way", r=0, min.T0 = 1,
                se = TRUE, loo = TRUE, parallel = TRUE, cores = num_cores, 
                nboots = params$nboots, keep.sims = TRUE)

saveRDS(occ_mod, file=file.path(outfolder,glue("{params$proptype}_occ_mod.rds")))