library(glue)
library(here)
library(yaml)
library(optparse)
library(jsonlite)
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
# returns: res: list of data frames containing ATT estimates and bootstrap replicates
#               for leads/lags defined based on event_time_user.

repeated_treatment_effects <- function(mod,
                                       panel_data,
                                       id_col="masterloanidtrepp",
                                       time_col="year",
                                       event_time_user="time_since_treatment_event",
                                       alpha=0.05){
  
  ## Extract pre-treatment effect estimates from fect model object
  
  pre_treatment <- data.frame(mod$est.att)
  pre_treatment[[event_time_user]] <- as.numeric(rownames(pre_treatment)) - 1
  rownames(pre_treatment) <- NULL
  pre_treatment <- pre_treatment[pre_treatment[[event_time_user]] < 0,]
  
  pre_treatment <- pre_treatment %>% rename(
    estimate=ATT,
    se=S.E.,
    ci.lo=CI.lower,
    ci.hi=CI.upper,
    n_cells=count
  )
  
  output_column_order <- c(event_time_user,"estimate","se","ci.lo","ci.hi","n_cells")
  pre_treatment <- pre_treatment[,output_column_order]
  
  ## Calculate ATT during post-treatment periods while accounting for repeated exposure
  
  repeated_event_time <- panel_data[,c(id_col,time_col,event_time_user)]
  
  # Get Y_obs and Y0_hat estimates imputed by fect
  po <- imputed_outcomes(mod)
  po_rep <- imputed_outcomes(mod, replicates=TRUE)
  
  # Attach corrected version of event time that accounts for how time since
  # treatment will "reset" under repeated flood exposure
  po <- left_join(po,repeated_event_time,by=c("id"=id_col,"time"=time_col))
  po_rep <- left_join(po_rep,repeated_event_time,by=c("id"=id_col,"time"=time_col))
  
  ## Aggregate individual treatment effect estimates to produce estimates 
  ## of ATT and associated SEs during each post-treatment period
  
  post_treatment <- po |> 
    group_by(across(all_of(event_time_user))) |> 
    summarise(estimate = mean(eff, na.rm = TRUE), n_cells = dplyr::n())
  
  rep_est <- po_rep |> 
    group_by(across(all_of(c(event_time_user,"replicate")))) |> 
    summarise(estimate = mean(eff, na.rm = TRUE))
  
  se_est <- rep_est |> 
    group_by(across(all_of(event_time_user))) |> 
    summarise(se = sd(estimate))
  
  post_treatment <- left_join(post_treatment,se_est, by=event_time_user)
  
  ## Combine pre- and post-treatment data
  dynamic_treatment_effects <- bind_rows(pre_treatment,post_treatment)
  dynamic_treatment_effects <- dynamic_treatment_effects[,output_column_order]
  
  ## Use standard error estimates to construct confidence intervals
  z <- qnorm(1-alpha/2)
  dynamic_treatment_effects$ci.lo <- dynamic_treatment_effects$estimate - z*dynamic_treatment_effects$se
  dynamic_treatment_effects$ci.hi <- dynamic_treatment_effects$estimate + z*dynamic_treatment_effects$se
  
  # Return:
  # (1) estimated ATTs
  # (2) bootstrapped replicates of estimated ATTs
  # (3) imputed potential outcomes for treated observations
  # (4) bootstrapped replicates of imputed potential outcomes
  res = list(att.est=dynamic_treatment_effects,
             att.rep=rep_est,
             imputed.po.est=po,
             imputed.po.rep=po_rep)
  
  return(res)
}

# Helper function to save ATT estimates and bootstrap replicates returned by
# repeated_treatment_effects function as parquet files. 
#
# FUNCTION INPUT/OUTPUT:
#
# param: res: list of data frames returned by repeated_treatment_effects function
# param: outfolder: path to output folder
# param: proptype: property type
# param: outcome: outcome of interest

save_result_as_parquet <- function(res,outfolder,proptype,outcome){
  
  # Save object as RDS file
  saveRDS(res, file=file.path(outfolder,glue("{params$proptype}_{outcome}_postprocessed.rds")))
  
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

### *** PARSE COMMAND-LINE ARGUMENTS *** ###

# Get name of scenario and property type
option_list <- list(
  make_option("--name", type = "character", default = format(Sys.time(), "%Y-%m-%d_model_run")),
  make_option("--proptype", type = "character", default = "MF")
)

# Load full set of user-defined parameters used in model run
params <- parse_args(OptionParser(option_list = option_list))
fitted_dir <- file.path(pwd,glue("fitted_models/{params$name}/{params$proptype}"))
params <- fromJSON(file.path(fitted_dir,"params.json"))

### *** LOAD FITTED MODELS AND DATA *** ###

panel_data <- readRDS(file.path(fitted_dir,glue("{params$proptype}_data.rds")))
D60_mod <- readRDS(file.path(fitted_dir,glue("{params$proptype}_D60_mod.rds")))
loss_rate_mod <- readRDS(file.path(fitted_dir,glue("{params$proptype}_loss_rate_mod.rds")))
occ_mod <- readRDS(file.path(fitted_dir,glue("{params$proptype}_occ_mod.rds")))
noi_mod <- readRDS(file.path(fitted_dir,glue("{params$proptype}_noi_mod.rds")))
rev_mod <- readRDS(file.path(fitted_dir,glue("{params$proptype}_rev_mod.rds")))
exp_mod <- readRDS(file.path(fitted_dir,glue("{params$proptype}_exp_mod.rds")))

### *** CALCULATE DYNAMIC TREATMENT EFFECTS UNDER REPEATED TREATMENT *** ###

## 60+ days delinquent
D60_res <- repeated_treatment_effects(D60_mod,panel_data,event_time_user=params$event_time)
save_result_as_parquet(D60_res,fitted_dir,params$proptype,"D60")

## Loss rate
loss_rate_res <- repeated_treatment_effects(loss_rate_mod,panel_data,event_time_user=params$event_time)
save_result_as_parquet(loss_rate_res,fitted_dir,params$proptype,"loss_rate")

## Occupancy
occ_res <- repeated_treatment_effects(occ_mod,panel_data,event_time_user=params$event_time)
save_result_as_parquet(occ_res,fitted_dir,params$proptype,"occ")

## Net operating income
noi_res <- repeated_treatment_effects(noi_mod,panel_data,event_time_user=params$event_time)
save_result_as_parquet(noi_res,fitted_dir,params$proptype,"noi")

## Revenues
rev_res <- repeated_treatment_effects(rev_mod,panel_data,event_time_user=params$event_time)
save_result_as_parquet(rev_res,fitted_dir,params$proptype,"rev")

## Expenses
exp_res <- repeated_treatment_effects(exp_mod,panel_data,event_time_user=params$event_time)
save_result_as_parquet(exp_res,fitted_dir,params$proptype,"exp")
