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

# Get treatment status scenario to run
scenario <- "base_case"
nboots <- 200
num_cores <- availableCores()
print(glue("scenario={scenario}, nboots={nboots}, num_cores={num_cores}"))

# Create folder for output
outfolder <- file.path(pwd,glue("fitted_models/{scenario}"))
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

### *** CREATE INTERACTION VARIABLES *** ###

# Region x Time
panel_data$region_time <- interaction(panel_data$cbsa_title, panel_data$year)

# Vintage x Time
panel_data$vintage_time <- interaction(panel_data$vintage, panel_data$year)

### *** SUBSET DATA BY PROPERTY TYPE *** ###

# For now, limit to properties inside the FEMA 100-year or 500-year floodplain. 
# This reduces the number of observations (making models much faster to fit) and 
# is also likely to be where we see the strongest effects. 
# Eventually will fit models for properties outside the floodplain as well
# once we're done debugging. 
floodplain_mask <- (panel_data$FEMA_100y_floodplain_indicator == 1)|(panel_data$FEMA_500y_floodplain_indicator == 1)
panel_data <- panel_data[floodplain_mask,]

# Subset by property type of interest
mf_data <- panel_data[panel_data$cssaproptype == "MF",]
rt_data <- panel_data[panel_data$cssaproptype == "RT",]

### *** FIT MODELS *** ###

## Multifamily Properties

saveRDS(mf_data, file=file.path(outfolder,"mf_data.rds"))

# Revenues
mf_rev_mod <- fect(log_rev ~ under_treatment, data = mf_data,
                   index = c("masterloanidtrepp","year","region_time"),
                   method = "cfe", force = "two-way", r=0, min.T0 = 1,
                   se = TRUE, parallel = TRUE, cores = num_cores, nboots = nboots,
                   keep.sims = TRUE)

saveRDS(mf_rev_mod, file=file.path(outfolder,"mf_rev_mod.rds"))

# Expenses
mf_exp_mod <- fect(log_exp ~ under_treatment, data = mf_data,
                   index = c("masterloanidtrepp","year","region_time"),
                   method = "cfe", force = "two-way", r=0, min.T0 = 1,
                   se = TRUE, parallel = TRUE, cores = num_cores, nboots = nboots,
                   keep.sims = TRUE)

saveRDS(mf_exp_mod, file=file.path(outfolder,"mf_exp_mod.rds"))

# Net Operating Income
mf_noi_mod <- fect(log_noi ~ under_treatment, data = mf_data,
                   index = c("masterloanidtrepp","year","region_time"),
                   method = "cfe", force = "two-way", r=0, min.T0 = 1,
                   se = TRUE, parallel = TRUE, cores = num_cores, nboots = nboots,
                   keep.sims = TRUE)

saveRDS(mf_noi_mod, file=file.path(outfolder,"mf_noi_mod.rds"))

# Occupancy
mf_occ_mod <- fect(occ ~ under_treatment, data = mf_data,
                   index = c("masterloanidtrepp","year","region_time"),
                   method = "cfe", force = "two-way", r=0, min.T0 = 1,
                   se = TRUE, parallel = TRUE, cores = num_cores, nboots = nboots,
                   keep.sims = TRUE)

saveRDS(mf_occ_mod, file=file.path(outfolder,"mf_occ_mod.rds"))

# 60-day delinquency
mf_D60_mod <- fect(ever_D60 ~ under_treatment, data = mf_data,
                   index = c("masterloanidtrepp","year","region_time"),
                   method = "cfe", force = "two-way", r=0, min.T0 = 1,
                   se = TRUE, parallel = TRUE, cores = num_cores, nboots = nboots,
                   keep.sims = TRUE)

saveRDS(mf_D60_mod, file=file.path(outfolder,"mf_D60_mod.rds"))

## Retail Properties

saveRDS(rt_data, file=file.path(outfolder,"rt_data.rds"))

# Revenues
rt_rev_mod <- fect(log_rev ~ under_treatment, data = rt_data,
                   index = c("masterloanidtrepp","year","region_time"),
                   method = "cfe", force = "two-way", r=0, min.T0 = 1,
                   se = TRUE, parallel = TRUE, cores = num_cores, nboots = nboots,
                   keep.sims = TRUE)

saveRDS(rt_rev_mod, file=file.path(outfolder,"rt_rev_mod.rds"))

# Expenses
rt_exp_mod <- fect(log_exp ~ under_treatment, data = rt_data,
                   index = c("masterloanidtrepp","year","region_time"),
                   method = "cfe", force = "two-way", r=0, min.T0 = 1,
                   se = TRUE, parallel = TRUE, cores = num_cores, nboots = nboots,
                   keep.sims = TRUE)

saveRDS(rt_exp_mod, file=file.path(outfolder,"rt_exp_mod.rds"))

# Net Operating Income
rt_noi_mod <- fect(log_noi ~ under_treatment, data = rt_data,
                   index = c("masterloanidtrepp","year","region_time"),
                   method = "cfe", force = "two-way", r=0, min.T0 = 1,
                   se = TRUE, parallel = TRUE, cores = num_cores, nboots = nboots,
                   keep.sims = TRUE)

saveRDS(rt_noi_mod, file=file.path(outfolder,"rt_noi_mod.rds"))

# Occupancy
rt_occ_mod <- fect(occ ~ under_treatment, data = rt_data,
                   index = c("masterloanidtrepp","year","region_time"),
                   method = "cfe", force = "two-way", r=0, min.T0 = 1,
                   se = TRUE, parallel = TRUE, cores = num_cores, nboots = nboots,
                   keep.sims = TRUE)

saveRDS(rt_occ_mod, file=file.path(outfolder,"rt_occ_mod.rds"))

# 60-day delinquency
rt_D60_mod <- fect(ever_D60 ~ under_treatment, data = rt_data,
                   index = c("masterloanidtrepp","year","region_time"),
                   method = "cfe", force = "two-way", r=0, min.T0 = 1,
                   se = TRUE, parallel = TRUE, cores = num_cores, nboots = nboots,
                   keep.sims = TRUE)

saveRDS(rt_D60_mod, file=file.path(outfolder,"rt_D60_mod.rds"))