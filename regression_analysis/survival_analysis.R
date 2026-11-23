library(glue)
library(here)
library(yaml)
library(optparse)
library(jsonlite)
library(arrow)
library(parallelly)
library(dplyr)
library(tidyr)
library(fixest)

# Load user-defined functions for building discrete-time hazard models
source("discrete_time_hazard_model.R")

### *** HELPER FUNCTIONS *** ###

# Function to execute user-defined filtering operation

apply_filter <- function(df, var, op, val) {
  if (!var %in% names(df)) stop("Filter variable not found in data: ", var)
  if (!op %in% c("eq", "lt", "gt", "in")) {
    stop("--filter_op must be one of: eq, lt, gt, in")
  }
  
  col <- df[[var]]
  v <- trimws(strsplit(val, ",", fixed = TRUE)[[1]])
  
  # Convert the value(s) to numeric if the column is numeric
  if (is.numeric(col)) {
    v <- suppressWarnings(as.numeric(v))
    if (anyNA(v)) stop("Non-numeric value supplied for numeric variable '", var, "'")
  }
  
  if (op != "in" && length(v) != 1) {
    stop("Operator '", op, "' takes exactly one value; use 'in' for several.")
  }
  
  keep <- switch(op,
                 eq   = col == v,
                 lt   = col <  v,
                 gt   = col >  v,
                 "in" = col %in% v
  )
  keep <- keep & !is.na(keep)   # drop rows with NA, as dplyr::filter() does
  
  message(sprintf("Filter (%s %s %s): kept %d of %d rows",
                  var, op, val, sum(keep), nrow(df)))
  
  return(df[keep, , drop = FALSE])
}

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
  make_option("--name", type = "character", default = format(Sys.time(), "%Y-%m-%d_hazard_model")),
  make_option("--treatment_scenario", type = "character", default = "zipcode_base_case"),
  make_option("--treatment_variable", type = "character", default = "under_treatment"),
  make_option("--event_time", type = "character", default = "time_since_treatment_event"),
  make_option("--floodzones", type = "character", default = "FEMA_100y_floodplain,FEMA_500y_floodplain"),
  make_option("--filter_var", type = "character", default = NULL), 
  make_option("--filter_op", type = "character", default = "eq"),
  make_option("--filter_val", type = "character", default = NULL),
  make_option("--proptype", type = "character", default = "MF"),
  make_option("--nboots",    type = "integer",   default = 200)
)

params <- parse_args(OptionParser(option_list = option_list))

# Create folder for output
outfolder <- file.path(pwd,glue("fitted_models/{params$name}/{params$proptype}"))
dir.create(outfolder,recursive=TRUE)

### *** LOAD DATA *** ###

# Longitudinal data on property financial outcomes
panel_data_path <- file.path(project_root,"create_panel/panel_outcome_data_combined.parquet")
panel_data <- read_parquet(panel_data_path)

# Neighborhood-level treatment status
treatment_status_dir <- file.path(project_root,"exposure_measures/treatment_status")
treatment_status_filename <- glue("{params$treatment_scenario}_treatment_status.parquet")
treatment_status_path <- file.path(treatment_status_dir,treatment_status_filename)
treatment_status <- read_parquet(treatment_status_path)
treatment_status <- treatment_status %>% rename(year = calendar_time)

# Get geographic unit at which treatment is assigned
geog_unit <- colnames(treatment_status)[1]
params$cluster_var <- geog_unit

# Merge outcome and treatment status data
panel_data <- left_join(panel_data, treatment_status, by = c(geog_unit,"year"))

### *** CREATE VINTAGE AND LOAN TERM VARIABLES *** ###

# Loan term in years
panel_data$loan_term <- round(as.integer(panel_data$maturitydate - panel_data$origdate)/365)

# Vintage x Term
panel_data$vintage_term <- interaction(panel_data$vintage,panel_data$loan_term)

# Small number of loans have missing vintage or loan term data -- drop them
panel_data <- panel_data[complete.cases(panel_data[,c("vintage","loan_term","vintage_term")]),]

### *** FILTER AND SUBSET DATA *** ###

# Flood zone
included_floodzones <- strsplit(params$floodzones,",")[[1]]
floodzone_mask <- (panel_data$floodzone %in% included_floodzones)
panel_data <- panel_data[floodzone_mask,]

# Property type
proptype_mask <- (panel_data$proptype == params$proptype)
panel_data <- panel_data[proptype_mask,]

# Additional filters
if (!is.null(params$filter_var) & !is.null(params$filter_val)) {
  panel_data <- apply_filter(panel_data, params$filter_var, params$filter_op, params$filter_val)
}

### *** SAVE COMMAND-LINE ARGUMENTS *** ###

### *** FIT DISCRETE TIME HAZARD MODEL *** ###

res <- counterfactual_cumulative_incidence(panel_data,
                                           target_outcome="D60",
                                           competing_outcomes=c("zero_balance_flag","defeased_released_flag"),
                                           baseline_hazard_strata = "vintage_term",
                                           region_strata = "cbsa_title")
res$att
