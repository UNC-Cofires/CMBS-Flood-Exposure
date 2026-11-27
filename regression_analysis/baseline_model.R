library(glue)
library(here)
library(yaml)
library(optparse)
library(jsonlite)
library(arrow)
library(parallelly)
library(dplyr)
library(panelView)
library(fixest)

# Load user-defined functions for imputing potential outcomes
source("imputation_estimators.R")

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

# Function to save results
save_result_as_parquet <- function(res,outfolder,proptype,outcome){
  
  # Save object as RDS file
  saveRDS(res, file=file.path(outfolder,glue("{params$proptype}_{outcome}_did.rds")))
  
  att.est <- res$att.est
  att.rep <- res$att.rep
  imputed.po.est <- res$imputed.po.est
  imputed.po.rep <- res$imputed.po.rep
  
  # Save data as parquet file
  write_parquet(att.est, sink=file.path(outfolder,glue("{params$proptype}_{outcome}_att_est.parquet")))
  write_parquet(att.rep, sink=file.path(outfolder,glue("{params$proptype}_{outcome}_att_rep.parquet")))
  write_parquet(imputed.po.est, sink=file.path(outfolder,glue("{params$proptype}_{outcome}_imputed_po_est.parquet")))
  write_parquet(imputed.po.rep, sink=file.path(outfolder,glue("{params$proptype}_{outcome}_imputed_po_rep.parquet")))
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
  make_option("--name", type = "character", default = format(Sys.time(), "%Y-%m-%d_model_run")),
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

### *** LOG-TRANSFORM PROPERTY CASHFLOW MEAURES *** ###

# In rare cases, financial metrics like NOI can be negative.
# This is incompatible with a log-linear model specification. 
# To address this problem, truncate NOI at a minimum of $1 so 
# that we can still apply a log transformation.
panel_data$log_rev <- log(pmax(panel_data$rev,1))
panel_data$log_exp <- log(pmax(panel_data$exp,1))
panel_data$log_noi <- log(pmax(panel_data$noi,1))

### *** CREATE INDICATOR FOR DSCR < 1.0 *** ###

panel_data$dscr_below_one <- as.integer(panel_data$dscr < 1.0)

### *** CREATE INDICATORS FOR MISSING FINANCIAL METRICS *** ###

# Property financials are typically not reported for the first 
# and last year of the loan. As such, only count as missing during
# intermediate years of the loan's life. 
first_year <- as.integer(format(panel_data$first_obs, "%Y"))
last_year <- as.integer(format(panel_data$last_obs, "%Y"))

# If a loan is paid off early in the year (e.g., January) then 
# it's likely that the financial data is also missing for the preceding year.
last_month <- as.integer(format(panel_data$last_obs, "%m"))
last_year[last_month <= 6] <- last_year[last_month <= 6] - 1

available_year_mask <- (panel_data$year > first_year) & (panel_data$year < last_year)

# Record for whether a loan is missing NOI during a year when we'd expect to have it
missing_noi_mask <- (available_year_mask) & (is.na(panel_data$noi))
panel_data$missing_noi <- as.integer(missing_noi_mask)

### *** STRATIFY TIME FIXED EFFECTS BY METRO *** ###

# Region x Time
panel_data$region_time <- interaction(panel_data$cbsa_title, panel_data$year)

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

# Save input data
saveRDS(panel_data, file=file.path(outfolder,glue("{params$proptype}_data.rds")))
write_parquet(panel_data, sink=file.path(outfolder,glue("{params$proptype}_data.parquet")))

# Save command-line arguments as JSON
write(
  toJSON(params, pretty = TRUE, auto_unbox = TRUE),
  file.path(outfolder, "params.json")
)

### *** FIT MODELS *** ###

## 60+ days delinquent
D60_res <- did_counterfactual_imputation(panel_data,
                                         outcome_col="D60",
                                         id_col="loanid",
                                         time_col="year",
                                         event_time_col=params$event_time,
                                         under_treatment_col=params$treatment_variable,
                                         time_fe_col="region_time",
                                         cluster_var=geog_unit,
                                         nboot=params$nboots)

save_result_as_parquet(D60_res,outfolder,params$proptype,"D60")

## Occupancy
occ_res <- did_counterfactual_imputation(panel_data,
                                         outcome_col="occ",
                                         id_col="loanid",
                                         time_col="year",
                                         event_time_col=params$event_time,
                                         under_treatment_col=params$treatment_variable,
                                         time_fe_col="region_time",
                                         cluster_var=geog_unit,
                                         nboot=params$nboots)

save_result_as_parquet(occ_res,outfolder,params$proptype,"occ")

## Net operating income
noi_res <- did_counterfactual_imputation(panel_data,
                                         outcome_col="log_noi",
                                         id_col="loanid",
                                         time_col="year",
                                         event_time_col=params$event_time,
                                         under_treatment_col=params$treatment_variable,
                                         time_fe_col="region_time",
                                         cluster_var=geog_unit,
                                         nboot=params$nboots)

save_result_as_parquet(noi_res,outfolder,params$proptype,"noi")

## Revenues
rev_res <- did_counterfactual_imputation(panel_data,
                                         outcome_col="log_rev",
                                         id_col="loanid",
                                         time_col="year",
                                         event_time_col=params$event_time,
                                         under_treatment_col=params$treatment_variable,
                                         time_fe_col="region_time",
                                         cluster_var=geog_unit,
                                         nboot=params$nboots)

save_result_as_parquet(rev_res,outfolder,params$proptype,"rev")

## Expenses
exp_res <- did_counterfactual_imputation(panel_data,
                                         outcome_col="log_exp",
                                         id_col="loanid",
                                         time_col="year",
                                         event_time_col=params$event_time,
                                         under_treatment_col=params$treatment_variable,
                                         time_fe_col="region_time",
                                         cluster_var=geog_unit,
                                         nboot=params$nboots)

save_result_as_parquet(exp_res,outfolder,params$proptype,"exp")

## DSCR < 1.0
dscr_below_one_res <- did_counterfactual_imputation(panel_data,
                                                    outcome_col="dscr_below_one",
                                                    id_col="loanid",
                                                    time_col="year",
                                                    event_time_col=params$event_time,
                                                    under_treatment_col=params$treatment_variable,
                                                    time_fe_col="region_time",
                                                    cluster_var=geog_unit,
                                                    nboot=params$nboots)

save_result_as_parquet(dscr_below_one_res,outfolder,params$proptype,"dscr_below_one")

## Missing NOI data
missing_noi_res <- did_counterfactual_imputation(panel_data,
                                                 outcome_col="missing_noi",
                                                 id_col="loanid",
                                                 time_col="year",
                                                 event_time_col=params$event_time,
                                                 under_treatment_col=params$treatment_variable,
                                                 time_fe_col="region_time",
                                                 cluster_var=geog_unit,
                                                 nboot=params$nboots)

save_result_as_parquet(missing_noi_res,outfolder,params$proptype,"missing_noi")


