library(glue)
library(here)
library(yaml)
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

# Read command-line arguments
args <- commandArgs(trailingOnly = TRUE)

scenario <- args[1]
proptype <- args[2]
nboots <- as.integer(args[3])

num_cores <- availableCores()
print(glue("scenario={scenario}, proptype={proptype}, nboots={nboots}, num_cores={num_cores}"))

# Create folder for output
outfolder <- file.path(pwd,glue("fitted_models/{scenario}/{proptype}"))
dir.create(outfolder,recursive=TRUE)

### *** LOAD DATA *** ###

# Longitudinal data on property financial outcomes
panel_data_path <- file.path(project_root,"create_panel/panel_outcome_data.parquet")
panel_data <- read_parquet(panel_data_path)

# Zipcode-level treatment status
treatment_status_dir <- file.path(project_root,"exposure_measures/zipcode_exposure")
treatment_status_filename <- glue("zipcode_treatment_status_{scenario}.parquet")
treatment_status_path <- file.path(treatment_status_dir,treatment_status_filename)
treatment_status <- read_parquet(treatment_status_path)
treatment_status <- treatment_status %>% rename(zcta_2020 = zipcode, year = calendar_time)

# Merge outcome and treatment status data
panel_data <- left_join(panel_data, treatment_status, by = c("zcta_2020","year"))

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

### *** SUBSET DATA *** ###

# For now, limit to properties inside the FEMA 100-year or 500-year floodplain. 
# This reduces the number of observations (making models much faster to fit) and 
# is also likely to be where we see the strongest effects. 
# Eventually will fit models for properties outside the floodplain as well
# once we're done debugging. 
floodplain_mask <- (panel_data$FEMA_100y_floodplain_indicator == 1)|(panel_data$FEMA_500y_floodplain_indicator == 1)
panel_data <- panel_data[floodplain_mask,]

# Subset by property type of interest
proptype_mask <- (panel_data$cssaproptype == proptype)
panel_data <- panel_data[proptype_mask,]

### *** FIT MODELS *** ###

## Save input data
saveRDS(panel_data, file=file.path(outfolder,glue("{proptype}_data.rds")))

## Currently 60+ days delinquent
D60_mod <- fect(D60 ~ under_treatment, data = panel_data,
                index = c("masterloanidtrepp","year","region_time"),
                method = "cfe", force = "two-way", r=0, min.T0 = 1,
                se = TRUE, parallel = TRUE, cores = num_cores, nboots = nboots,
                keep.sims = TRUE)

saveRDS(D60_mod, file=file.path(outfolder,glue("{proptype}_D60_mod.rds")))

## Ever 60+ days delinquent
ever_D60_mod <- fect(ever_D60 ~ under_treatment, data = panel_data,
                     index = c("masterloanidtrepp","year","region_time"),
                     method = "cfe", force = "two-way", r=0, min.T0 = 1,
                     se = TRUE, parallel = TRUE, cores = num_cores, nboots = nboots,
                     keep.sims = TRUE)

saveRDS(ever_D60_mod, file=file.path(outfolder,glue("{proptype}_ever_D60_mod.rds")))

## Loss rate (100 x realized losses / original loan balance)
loss_rate_mod <- fect(loss_rate ~ under_treatment, data = panel_data,
                      index = c("masterloanidtrepp","year","region_time"),
                      method = "cfe", force = "two-way", r=0, min.T0 = 1,
                      se = TRUE, parallel = TRUE, cores = num_cores, nboots = nboots,
                      keep.sims = TRUE)

saveRDS(loss_rate_mod, file=file.path(outfolder,glue("{proptype}_loss_rate_mod.rds")))

## Revenues
rev_mod <- fect(log_rev ~ under_treatment, data = panel_data,
                index = c("masterloanidtrepp","year","region_time"),
                method = "cfe", force = "two-way", r=0, min.T0 = 1,
                se = TRUE, parallel = TRUE, cores = num_cores, nboots = nboots,
                keep.sims = TRUE)

saveRDS(rev_mod, file=file.path(outfolder,glue("{proptype}_rev_mod.rds")))

## Expenses
exp_mod <- fect(log_exp ~ under_treatment, data = panel_data,
                index = c("masterloanidtrepp","year","region_time"),
                method = "cfe", force = "two-way", r=0, min.T0 = 1,
                se = TRUE, parallel = TRUE, cores = num_cores, nboots = nboots,
                keep.sims = TRUE)

saveRDS(exp_mod, file=file.path(outfolder,glue("{proptype}_exp_mod.rds")))

## Net operating income
noi_mod <- fect(log_noi ~ under_treatment, data = panel_data,
                index = c("masterloanidtrepp","year","region_time"),
                method = "cfe", force = "two-way", r=0, min.T0 = 1,
                se = TRUE, parallel = TRUE, cores = num_cores, nboots = nboots,
                keep.sims = TRUE)

saveRDS(noi_mod, file=file.path(outfolder,glue("{proptype}_noi_mod.rds")))

## Occupancy
occ_mod <- fect(occ ~ under_treatment, data = panel_data,
                index = c("masterloanidtrepp","year","region_time"),
                method = "cfe", force = "two-way", r=0, min.T0 = 1,
                se = TRUE, parallel = TRUE, cores = num_cores, nboots = nboots,
                keep.sims = TRUE)

saveRDS(occ_mod, file=file.path(outfolder,glue("{proptype}_occ_mod.rds")))

## Missing NOI
miss_noi_mod <- fect(missing_noi ~ under_treatment, data = panel_data,
                     index = c("masterloanidtrepp","year","region_time"),
                     method = "cfe", force = "two-way", r=0, min.T0 = 1,
                     se = TRUE, parallel = TRUE, cores = num_cores, nboots = nboots,
                     keep.sims = TRUE)

saveRDS(miss_noi_mod, file=file.path(outfolder,glue("{proptype}_miss_noi_mod.rds")))

## Missing occupancy
miss_occ_mod <- fect(missing_occ ~ under_treatment, data = panel_data,
                     index = c("masterloanidtrepp","year","region_time"),
                     method = "cfe", force = "two-way", r=0, min.T0 = 1,
                     se = TRUE, parallel = TRUE, cores = num_cores, nboots = nboots,
                     keep.sims = TRUE)

saveRDS(miss_occ_mod, file=file.path(outfolder,glue("{proptype}_miss_occ_mod.rds")))
