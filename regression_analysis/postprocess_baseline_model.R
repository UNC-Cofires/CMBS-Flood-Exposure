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
#             loo=TRUE,             # For pre-treatment periods, perform placebo test using leave-period-out approach.
#             group=groupatt,       # If calculating group-wise ATTs, column denoting group membership. 
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
# param: groupatt: column denoting group membership if calculating group-wise ATTs. 
#        Defaults to NULL. 
# param: alpha: significance level (alpha=0.05 for 95% CIs)
#
# returns: dynamic_treatment_effects: dataframe of dynamic treatment
#          effect estimates with leads/lags defined based on event_time_user.

repeated_treatment_effects <- function(mod,
                                       panel_data,
                                       id_col="masterloanidtrepp",
                                       time_col="year",
                                       event_time_user="time_since_treatment_event",
                                       groupatt=NULL,
                                       alpha=0.05){
  
  
  
  ## Extract pre-treatment effect estimates from fect model object
  
  # Overall
  
  pre_treatment <- data.frame(mod$pre.est.att)
  pre_treatment[[event_time_user]] <- as.numeric(rownames(pre_treatment)) - 1
  rownames(pre_treatment) <- NULL
  
  pre_treatment <- pre_treatment %>% rename(
    estimate=ATT,
    se=S.E.,
    ci.lo=CI.lower,
    ci.hi=CI.upper,
    n_cells=count.on
  )
  
  output_column_order <- c(event_time_user,"estimate","se","ci.lo","ci.hi","n_cells")
  pre_treatment <- pre_treatment[,output_column_order]
  
  # By group
  
  if (!is.null(groupatt)){
    
    groups <- names(mod$pre.est.group.output)
    
    overall_group_name <- paste(groups, collapse = " OR ")
    pre_treatment[[groupatt]] <- overall_group_name
    output_column_order <- c(groupatt,event_time_user,"estimate","se","ci.lo","ci.hi","n_cells")
    
    for (group in groups){
      
      group_pre_treatment <- data.frame(mod$pre.est.group.output[[group]]$pre.est.att)
      
      group_pre_treatment[[event_time_user]] <- as.numeric(rownames(group_pre_treatment)) - 1
      rownames(group_pre_treatment) <- NULL
      
      group_pre_treatment <- group_pre_treatment %>% rename(
        estimate=ATT,
        se=S.E.,
        ci.lo=CI.lower,
        ci.hi=CI.upper,
        n_cells=count.on
      )
      
      group_pre_treatment[[groupatt]] <- group
      group_pre_treatment <- group_pre_treatment[,output_column_order]
      
      pre_treatment <- bind_rows(pre_treatment,group_pre_treatment)
      
    }
    
  }
  
  ## Calculate ATT during post-treatment periods while accounting for repeated exposure
  
  if (!is.null(groupatt)){
    repeated_event_time <- panel_data[,c(id_col,time_col,event_time_user,groupatt)]
  }else{
    repeated_event_time <- panel_data[,c(id_col,time_col,event_time_user)]
  }
  
  # Get Y_obs and Y0_hat estimates imputed by fect
  po <- imputed_outcomes(mod)
  po_rep <- imputed_outcomes(mod, replicates=TRUE)
  
  # Attach corrected version of event time that accounts for how time since
  # treatment will "reset" under repeated flood exposure
  po <- left_join(po,repeated_event_time,by=c("id"=id_col,"time"=time_col))
  po_rep <- left_join(po_rep,repeated_event_time,by=c("id"=id_col,"time"=time_col))
  
  ## Aggregate individual treatment effect estimates to produce estimates 
  ## of ATT and associated SEs during each post-treatment period
  
  # Overall
  
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
  
  # Use standard error estimates to construct confidence intervals
  z <- qnorm(1-alpha/2)
  post_treatment$ci.lo <- post_treatment$estimate - z*post_treatment$se
  post_treatment$ci.hi <- post_treatment$estimate + z*post_treatment$se
  
  
  # By group
  
  if (!is.null(groupatt)){
    
    post_treatment[[groupatt]] <- overall_group_name
    
    group_post_treatment <- po |> 
      group_by(across(all_of(c(groupatt,event_time_user)))) |> 
      summarise(estimate = mean(eff, na.rm = TRUE), n_cells = dplyr::n())
    
    group_rep_est <- po_rep |> 
      group_by(across(all_of(c(groupatt,event_time_user,"replicate")))) |> 
      summarise(estimate = mean(eff, na.rm = TRUE))
    
    group_se_est <- group_rep_est |> 
      group_by(across(all_of(c(groupatt,event_time_user)))) |> 
      summarise(se = sd(estimate))
    
    group_post_treatment <- left_join(group_post_treatment,group_se_est, by=c(groupatt,event_time_user))
    
    # Construct confidence intervals by group
    z <- qnorm(1-alpha/2)
    group_post_treatment$ci.lo <- group_post_treatment$estimate - z*group_post_treatment$se
    group_post_treatment$ci.hi <- group_post_treatment$estimate + z*group_post_treatment$se
    
    # Join to overall estimates
    post_treatment <- bind_rows(post_treatment,group_post_treatment)
  }
  
  ## Combine pre- and post-treatment data
  dynamic_treatment_effects <- bind_rows(pre_treatment,post_treatment)
  dynamic_treatment_effects <- dynamic_treatment_effects[,output_column_order]
  
  if (!is.null(groupatt)){
    
    dynamic_treatment_effects[[groupatt]] <- as.factor(dynamic_treatment_effects[[groupatt]])
    dynamic_treatment_effects[[groupatt]] <- relevel(dynamic_treatment_effects[[groupatt]], ref=overall_group_name)
    dynamic_treatment_effects <- dynamic_treatment_effects |> arrange(!!!rlang::syms(c(groupatt,event_time_user)))
    
  }
  
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
floodzone <- args[2]
groupatt <- args[3]
proptype <- args[4]

print(glue("scenario={scenario}, floodzone={floodzone}, groupatt={groupatt}, proptype={proptype}"))

### *** LOAD FITTED MODELS AND DATA *** ###

fitted_dir <- file.path(pwd,glue("fitted_models/{scenario}/{floodzone}/{groupatt}/{proptype}"))

panel_data <- readRDS(file.path(fitted_dir,glue("{proptype}_data.rds")))
D60_mod <- readRDS(file.path(fitted_dir,glue("{proptype}_D60_mod.rds")))
noi_mod <- readRDS(file.path(fitted_dir,glue("{proptype}_noi_mod.rds")))
occ_mod <- readRDS(file.path(fitted_dir,glue("{proptype}_occ_mod.rds")))

### *** CALCULATE DYNAMIC TREATMENT EFFECTS UNDER REPEATED TREATMENT *** ###

## 60+ days delinquent
D60_dynamic_effects <- repeated_treatment_effects(D60_mod,panel_data,groupatt=groupatt)
write_parquet(D60_dynamic_effects, sink=file.path(fitted_dir,glue("{proptype}_D60_dynamic_effects.parquet")))

## Net operating income
noi_dynamic_effects <- repeated_treatment_effects(noi_mod,panel_data,groupatt=groupatt)
write_parquet(noi_dynamic_effects, sink=file.path(fitted_dir,glue("{proptype}_noi_dynamic_effects.parquet")))

## Occupancy
occ_dynamic_effects <- repeated_treatment_effects(occ_mod,panel_data,groupatt=groupatt)
write_parquet(occ_dynamic_effects, sink=file.path(fitted_dir,glue("{proptype}_occ_dynamic_effects.parquet")))
