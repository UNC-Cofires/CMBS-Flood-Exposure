library(glue)
library(here)
library(yaml)
library(arrow)
library(parallelly)
library(dplyr)
library(fect)


### *** HELPER FUNCTIONS *** ###

# This function calculates dynamic treatment effects under repeated treatment.
# To accomplish this, the default event time variable created by FEct is replaced
# with a user-defined event time variable. This allows for greater flexibility
# when defining event time; for example, users can define an event time variable
# that "resets" with each successive treatment event occurring within a defined period. 
#
# For pre-treatment periods, we will use the default effect estimates produced by
# FEct; for post-treatment periods, effects are re-calculated by aggregating imputed
# counterfactual outcomes by user-defined event time. Standard errors are calculated
# by repeating this procedure on bootstrapped replicates created during the initial
# model fitting process.
#
# This procedure is based on the examples provided in the "custom estimands" section
# of the FEct user manual: https://yiqingxu.org/packages/fect/03-estimands.html#custom-estimands
#
# When initially fitting the model, please ensure the following options are enabled: 
#
# mod <- fect(Y ~ D, 
#             data = panel_data, 
#             se=TRUE, 
#             ci.method="normal",   # CI: θ ± z*SE where z is the 1-α/2 quantile of a standard normal distribution.
#             nboots=200,           # Need at least 200 replicates to reliably estimate SEs.
#             keep.sims=TRUE)       # Save bootstrapped replicates so we can re-calculate SEs for custom estimands. 
#
# FUNCTION INPUT/OUTPUT:
#
# param: mod: fitted fect model object
# param: panel_data: data used to fit fect model object. 
# param: id_col: column identifying units in panel_data. 
# param: time_col: column corresponding to calendar time in panel_data. 
# param: event_time_user: user-defined event time column in panel_data.
#        Zero should correspond to period in which treatment event occurs. 
# param: alpha: significance level (alpha=0.05 for 95% CIs)
#
# returns: dynamic_treatment_effects: dataframe of dynamic treatment
#          effect estimates with leads/lags defined based on event_time_user.

repeated_treatment_effects <- function(mod,
                                       panel_data,
                                       id_col="masterloanidtrepp",
                                       time_col="year",
                                       event_time_user="time_since_treatment_event",
                                       alpha=0.05){
  
  ## Extract pre-treatment effect estimates from fect model object
  
  pre_treatment <- estimand(mod,type="att",by="event.time")
  
  # Create a column where zero corresponds to period of treatment event.
  # (by default, fect codes period of treatment as 1)
  pre_treatment[[event_time_user]] <- pre_treatment$event.time - 1
  
  # Filter for pre-treatment periods
  pre_treatment_mask <- (pre_treatment[[event_time_user]] < 0)
  pre_treatment <- pre_treatment[pre_treatment_mask,c(event_time_user,"estimate","se","ci.lo","ci.hi","n_cells")]
  
  ## Calculate ATT during post-treatment periods while accounting for repeated exposure
  
  # Get Y_obs and Y0_hat estimates imputed by fect
  repeated_event_time <- panel_data[,c(id_col,time_col,event_time_user)]
  po <- imputed_outcomes(mod)
  po_rep <- imputed_outcomes(mod, replicates=TRUE)
  
  # Attach corrected version of event time that accounts for how time since
  # treatment will "reset" under repeated flood exposure
  po <- left_join(po,repeated_event_time,by=c("id"=id_col,"time"=time_col))
  po_rep <- left_join(po_rep,repeated_event_time,by=c("id"=id_col,"time"=time_col))
  
  # Aggregate individual treatment effect estimates to produce estimates 
  # of ATT and associated SEs during each post-treatment period
  post_treatment <- po |> 
    group_by(across(all_of(event_time_user))) |> 
    summarise(estimate = mean(eff, na.rm = TRUE), n_cells = dplyr::n())
  
  rep_est <- po_rep |> 
    group_by(across(all_of(c(event_time_user,"replicate")))) |> 
    summarise(estimate = mean(eff, na.rm = TRUE))
  
  se_est <- rep_est |> 
    group_by(across(all_of(event_time_user))) |> 
    summarise(se = sd(estimate))
  
  post_treatment <- left_join(post_treatment,se_est)
  
  # Use standard error estimates to construct confidence intervals
  z <- qnorm(1-alpha/2)
  post_treatment$ci.lo <- post_treatment$estimate - z*post_treatment$se
  post_treatment$ci.hi <- post_treatment$estimate + z*post_treatment$se
  
  ## Combine pre- and post-treatment data
  dynamic_treatment_effects <- bind_rows(pre_treatment,post_treatment)
  
  # Return the output
  return(dynamic_treatment_effects)
}

### *** INITIAL SETUP *** ###

# Get current working directory and project root
pwd <- here::here()
project_root <- dirname(pwd)

# Load configuration file
config_path <- file.path(project_root,"config.yaml")
config <- read_yaml(config_path)

# Get scenario and property type
args <- commandArgs(trailingOnly = TRUE)
scenario <- args[1]
proptype <- args[2]

print(glue("scenario={scenario}, proptype={proptype}"))

### *** LOAD FITTED MODELS AND DATA *** ###

fitted_dir <- file.path(pwd,glue("fitted_models/{scenario}/{proptype}"))

panel_data <- readRDS(file.path(fitted_dir,glue("{proptype}_data.rds")))
D60_mod <- readRDS(file.path(fitted_dir,glue("{proptype}_D60_mod.rds")))
ever_D60_mod <- readRDS(file.path(fitted_dir,glue("{proptype}_ever_D60_mod.rds")))
loss_rate_mod <- readRDS(file.path(fitted_dir,glue("{proptype}_loss_rate_mod.rds")))
rev_mod <- readRDS(file.path(fitted_dir,glue("{proptype}_rev_mod.rds")))
exp_mod <- readRDS(file.path(fitted_dir,glue("{proptype}_exp_mod.rds")))
noi_mod <- readRDS(file.path(fitted_dir,glue("{proptype}_noi_mod.rds")))
occ_mod <- readRDS(file.path(fitted_dir,glue("{proptype}_occ_mod.rds")))
miss_noi_mod <- readRDS(file.path(fitted_dir,glue("{proptype}_miss_noi_mod.rds")))
miss_occ_mod <- readRDS(file.path(fitted_dir,glue("{proptype}_miss_occ_mod.rds")))

### *** CALCULATE DYNAMIC TREATMENT EFFECTS UNDER REPEATED TREATMENT *** ###

## Currently 60+ days delinquent
D60_dynamic_effects <- repeated_treatment_effects(D60_mod,panel_data)
write_parquet(D60_dynamic_effects, sink=file.path(fitted_dir,glue("{proptype}_D60_dynamic_effects.parquet")))

## Ever 60+ days delinquent
ever_D60_dynamic_effects <- repeated_treatment_effects(ever_D60_mod,panel_data)
write_parquet(ever_D60_dynamic_effects, sink=file.path(fitted_dir,glue("{proptype}_ever_D60_dynamic_effects.parquet")))

## Loss rate (100 x realized losses / original loan balance)
loss_rate_dynamic_effects <- repeated_treatment_effects(loss_rate_mod,panel_data)
write_parquet(loss_rate_dynamic_effects, sink=file.path(fitted_dir,glue("{proptype}_loss_rate_dynamic_effects.parquet")))

## Revenues
rev_dynamic_effects <- repeated_treatment_effects(rev_mod,panel_data)
write_parquet(rev_dynamic_effects, sink=file.path(fitted_dir,glue("{proptype}_rev_dynamic_effects.parquet")))

## Expenses
exp_dynamic_effects <- repeated_treatment_effects(exp_mod,panel_data)
write_parquet(exp_dynamic_effects, sink=file.path(fitted_dir,glue("{proptype}_exp_dynamic_effects.parquet")))

## Net operating income
noi_dynamic_effects <- repeated_treatment_effects(noi_mod,panel_data)
write_parquet(noi_dynamic_effects, sink=file.path(fitted_dir,glue("{proptype}_noi_dynamic_effects.parquet")))

## Occupancy
occ_dynamic_effects <- repeated_treatment_effects(occ_mod,panel_data)
write_parquet(occ_dynamic_effects, sink=file.path(fitted_dir,glue("{proptype}_occ_dynamic_effects.parquet")))

## Missing NOI
miss_noi_dynamic_effects <- repeated_treatment_effects(miss_noi_mod,panel_data)
write_parquet(miss_noi_dynamic_effects, sink=file.path(fitted_dir,glue("{proptype}_miss_noi_dynamic_effects.parquet")))

## Missing occupancy
miss_occ_dynamic_effects <- repeated_treatment_effects(miss_occ_mod,panel_data)
write_parquet(miss_occ_dynamic_effects, sink=file.path(fitted_dir,glue("{proptype}_miss_occ_dynamic_effects.parquet")))