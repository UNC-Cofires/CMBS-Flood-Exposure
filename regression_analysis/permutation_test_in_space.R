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

### *** HELPER FUNCTIONS *** ###

permute_treatment_history <- function(panel_data,treatment_status,params){
  # panel_data: data used in estimation sample
  # treatment_status: neighborhood-level treatment assignment data frame
  # params: named list containing options used in model fitting process
  
  cluster_var <- params$cluster_var
  event_time_user <- params$event_time
  clusters <- unique(treatment_status[[cluster_var]])
  
  shuffled_clusters <- data.frame(recipient_cluster=clusters,donor_cluster=clusters)
  shuffled_clusters$donor_cluster <- sample(shuffled_clusters$donor_cluster,replace=FALSE)
  
  shuffled_treatment <- left_join(shuffled_clusters, treatment_status, by = c("donor_cluster" = cluster_var))
  
  shuffled_treatment <- shuffled_treatment %>% 
    rename("{cluster_var}":="recipient_cluster") %>% 
    select(all_of(c(cluster_var,"year","D",event_time_user)))
  
  shuffled_data <- panel_data %>% select(-all_of(c("D",event_time_user))) %>% left_join(shuffled_treatment,by = c(cluster_var,"year"))
  
  return(shuffled_data)
}

# This function re-estimates the model without computing standard errors
estimate_model <- function(outcome_var,panel_data,params,num_cores){
  # param: outcome_var: outcome variable
  # param: data: data used in estimation sample
  # param: params: named list of options used in model fitting workflow
  # param: num_cores: number of available CPU cores
  
  panel_data$Y <- panel_data[[outcome_var]]
  
  # Fit fect model object
  mod <- fect(Y ~ D, data = panel_data, index = params$fixed_effects,
              method = "cfe", force = "two-way", r=0, min.T0 = 1,
              se = FALSE, parallel = TRUE, cores = num_cores)
  
  # Calculate ATT during post-treatment periods while accounting for repeated exposure
  id_col <- params$fixed_effects[1]
  time_col <- params$fixed_effects[2]
  event_time_user <- params$event_time
  repeated_event_time <- panel_data[,c(id_col,time_col,event_time_user)]
  
  # Get Y_obs and Y0_hat estimates imputed by fect
  po <- imputed_outcomes(mod)
  
  # Attach corrected version of event time that accounts for how time since
  # treatment will "reset" under repeated flood exposure
  po <- left_join(po,repeated_event_time,by=c("id"=id_col,"time"=time_col))
  
  ## Aggregate ITEs to estimate ATT during each post-treatment period
  
  dynamic_effects <- po |> 
    group_by(across(all_of(event_time_user))) |> 
    summarise(estimate = mean(eff, na.rm = TRUE))
  
  return(dynamic_effects)
}

permutation_test <- function(outcome_var,panel_data,treatment_status,params,nperm,num_cores){
  # outcome_var: outcome variable of interest
  # panel_data: data used in estimation sample
  # treatment_status: neighborhood-level treatment assignment data frame
  # params: named list containing options used in model fitting process
  # nperm: number of times to permute treatment assignments
  # num_cores: number of available CPU cores
  
  # Compute ATT using actual treatment histories
  att.est <- estimate_model(outcome_var,panel_data,params,num_cores)
  att.est <- att.est %>% rename(estimate.actual=estimate)
  
  # Use shuffled treatment histories to compute distribution of ATT
  # estimates under sharp null hypothesis. 
  
  data_list <- vector("list", length = nperm)
  
  for (i in 1:nperm){
    shuffled_data <- permute_treatment_history(panel_data,treatment_status,params)
    att.null <- estimate_model(outcome_var,shuffled_data,params,num_cores)
    att.null$replicate <- i
    data_list[[i]] <- att.null
    
    print(glue("{outcome_var} replicate {i} / {nperm}"))
  }
  
  # Create indicator variable for instances when permuted treatment history
  # results in an ATT estimate that is more extreme than actual treatment history
  att.null <- bind_rows(data_list) %>% rename(estimate.permuted = estimate)
  att.null <- left_join(att.null,att.est,by=params$event_time)
  att.null$permuted.more.extreme <- as.integer(abs(att.null$estimate.permuted) >= abs(att.null$estimate.actual))
  
  # Compute Fisher exact p-value
  perm.p.value <- att.null %>% 
    group_by(across(all_of(params$event_time))) %>% 
    summarise(p.value = mean(permuted.more.extreme, na.rm = TRUE),
              n.perm.more.extreme = sum(permuted.more.extreme, na.rm = TRUE),
              n.perm = n())
  
  # Return null distribution of ATTs and period-specific Fisher exact p-values
  res <- list(att.null=att.null,perm.p.value=perm.p.value)
  return(res)
}

save_result_as_parquet <- function(res,outfolder,proptype,outcome){
  
  att.null <- res$att.null
  perm.p.value <- res$perm.p.value
  
  # Save data as parquet file
  write_parquet(att.null, sink=file.path(outfolder,glue("{params$proptype}_{outcome}_permutation_test_null_dist.parquet")))
  write_parquet(perm.p.value, sink=file.path(outfolder,glue("{params$proptype}_{outcome}_permutation_test_p_value.parquet")))
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

# Get name of scenario and property type
option_list <- list(
  make_option("--name", type = "character", default = format(Sys.time(), "%Y-%m-%d_model_run")),
  make_option("--proptype", type = "character", default = "MF"),
  make_option("--nperm",    type = "integer",   default = 1000)
  )

# Load full set of user-defined parameters used in model run
params <- parse_args(OptionParser(option_list = option_list))
nperm <- params$nperm
fitted_dir <- file.path(pwd,glue("fitted_models/{params$name}/{params$proptype}"))
params <- fromJSON(file.path(fitted_dir,"params.json"))

### *** LOAD DATA *** ###

# Property financial data
panel_data <- readRDS(file.path(fitted_dir,glue("{params$proptype}_data.rds")))

# Neighborhood-level treatment status
treatment_status_dir <- file.path(project_root,"exposure_measures/treatment_status")
treatment_status_filename <- glue("{params$treatment_scenario}_treatment_status.parquet")
treatment_status_path <- file.path(treatment_status_dir,treatment_status_filename)
treatment_status <- read_parquet(treatment_status_path)
treatment_status <- treatment_status %>% rename(year = calendar_time)

# Keep only geographic unit, time, treatment indicator, and event time variables
treatment_status$D <- treatment_status[[params$treatment_variable]]
treatment_status <- treatment_status[,c(params$cluster_var,"year","D",params$event_time)]

### *** CONDUCT PERMUTATION TESTS *** ###

## 60+ days delinquent
res <- permutation_test("D60",panel_data,treatment_status,params,nperm,num_cores)
save_result_as_parquet(res,fitted_dir,proptype,"D60")

## Loss rate
res <- permutation_test("loss_rate",panel_data,treatment_status,params,nperm,num_cores)
save_result_as_parquet(res,fitted_dir,proptype,"loss_rate")

## Occupancy
res <- permutation_test("occ",panel_data,treatment_status,params,nperm,num_cores)
save_result_as_parquet(res,fitted_dir,proptype,"occ")

## Net operating income
res <- permutation_test("log_noi",panel_data,treatment_status,params,nperm,num_cores)
save_result_as_parquet(res,fitted_dir,proptype,"noi")

## Revenues
res <- permutation_test("log_rev",panel_data,treatment_status,params,nperm,num_cores)
save_result_as_parquet(res,fitted_dir,proptype,"rev")

## Expenses
res <- permutation_test("log_exp",panel_data,treatment_status,params,nperm,num_cores)
save_result_as_parquet(res,fitted_dir,proptype,"exp")


