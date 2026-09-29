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
floodzone <- args[2]
groupatt <- args[3]
proptype <- args[4]
nboots <- as.integer(args[5])

num_cores <- availableCores()
print(glue("scenario={scenario}, floodzone={floodzone}, groupatt={groupatt}, proptype={proptype}, nboots={nboots}, num_cores={num_cores}"))

# Create folder for output
outfolder <- file.path(pwd,glue("fitted_models/{scenario}/{floodzone}/{groupatt}/{proptype}"))
dir.create(outfolder,recursive=TRUE)

### *** LOAD DATA *** ###

# Longitudinal data on property financial outcomes
panel_data_path <- file.path(project_root,"create_panel/panel_outcome_data.parquet")
panel_data <- read_parquet(panel_data_path)

# Neighborhood-level treatment status
treatment_status_dir <- file.path(project_root,"exposure_measures/treatment_status")
treatment_status_filename <- glue("{scenario}_treatment_status.parquet")
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

### *** SUBSET DATA *** ###

# Subset by inside/outside FEMA 100-year and 500-year floodplain
floodplain_mask <- (panel_data$lumped_floodzone == "inside_FEMA_floodplains")

if (floodzone == "inside") {
  
  # Filter for properties inside FEMA floodplains
  panel_data <- panel_data[floodplain_mask,]
  
} else if (floodzone == "outside") {
  
  # Filter for properties outside FEMA floodplains
  panel_data <- panel_data[!floodplain_mask,]
  
}

# Subset by property type of interest
proptype_mask <- (panel_data$cssaproptype == proptype)
panel_data <- panel_data[proptype_mask,]

### *** FIT MODELS *** ###

## Save input data
saveRDS(panel_data, file=file.path(outfolder,glue("{proptype}_data.rds")))

## 60-day delinquency
D60_mod <- fect(D60 ~ under_treatment, data = panel_data, group = groupatt,
                index = c("masterloanidtrepp","year","region_time"),
                method = "cfe", force = "two-way", r=0, min.T0 = 1,
                se = TRUE, loo = TRUE, parallel = TRUE, cores = num_cores, 
                nboots = nboots, keep.sims = TRUE)

saveRDS(D60_mod, file=file.path(outfolder,glue("{proptype}_D60_mod.rds")))

## Net operating income
noi_mod <- fect(log_noi ~ under_treatment, data = panel_data, group = groupatt,
                index = c("masterloanidtrepp","year","region_time"),
                method = "cfe", force = "two-way", r=0, min.T0 = 1,
                se = TRUE, loo = TRUE, parallel = TRUE, cores = num_cores, 
                nboots = nboots, keep.sims = TRUE)

saveRDS(noi_mod, file=file.path(outfolder,glue("{proptype}_noi_mod.rds")))

## Occupancy
occ_mod <- fect(occ ~ under_treatment, data = panel_data, group = groupatt,
                index = c("masterloanidtrepp","year","region_time"),
                method = "cfe", force = "two-way", r=0, min.T0 = 1,
                se = TRUE, loo = TRUE, parallel = TRUE, cores = num_cores, 
                nboots = nboots, keep.sims = TRUE)

saveRDS(occ_mod, file=file.path(outfolder,glue("{proptype}_occ_mod.rds")))