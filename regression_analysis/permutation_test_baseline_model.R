library(glue)
library(here)
library(yaml)
library(optparse)
library(jsonlite)
library(arrow)
library(parallelly)
library(dplyr)
library(panelView)

# Load user-defined functions
source("imputation_estimators.R")

### *** HELPER FUNCTIONS *** ###

permute_treatment_history <- function(data,
                                      treatment_status,
                                      cluster_var,
                                      time_col,
                                      event_time_user,
                                      treatment_variable){
  # panel_data: data used in estimation sample
  # treatment_status: neighborhood-level treatment assignment data frame
  # cluster_var: column name denoting level at which treatment is assigned (e.g., "zipcode")
  # time_col: column name denoting time period (e.g., "year")
  # event_time_user: user-defined event time column name 
  # treatment_variable: user-defined treatment status indicator column name

  clusters <- unique(treatment_status[[cluster_var]])
  
  shuffled_clusters <- data.frame(recipient_cluster=clusters,donor_cluster=clusters)
  shuffled_clusters$donor_cluster <- sample(shuffled_clusters$donor_cluster,replace=FALSE)
  
  shuffled_treatment <- left_join(shuffled_clusters, treatment_status, by = c("donor_cluster" = cluster_var))
  
  shuffled_treatment <- shuffled_treatment %>% 
    rename("{cluster_var}":="recipient_cluster") %>% 
    select(all_of(c(cluster_var,"year",treatment_variable,event_time_user)))
  
  shuffled_data <- panel_data %>% select(-all_of(c(treatment_variable,event_time_user))) %>% left_join(shuffled_treatment,by = c(cluster_var,time_col))
  
  return(shuffled_data)
}

permutation_test <- function(data,
                             id_col="loanid",
                             time_col="year",
                             event_time_col="time_since_treatment_event",
                             under_treatment_col="under_treatment",
                             outcome_col="occ",
                             time_fe_col="region_time",
                             cluster_var="zipcode",
                             nperm=1000,
                             iter=50000,
                             tol=1e-6){

  
  # Compute ATT using actual treatment histories
  res <- impute_did(data,
                    id_col=id_col,
                    time_col=time_col,
                    event_time_col=event_time_col,
                    under_treatment_col=under_treatment_col,
                    outcome_col=outcome_col,
                    time_fe_col=time_fe_col,
                    iter=iter,
                    tol=tol)
  
  att.est <- res$att %>% select(r,ATT) %>% rename(ATT.actual = ATT)
  
  # Use shuffled treatment histories to compute distribution of ATT
  # estimates under sharp null hypothesis. 
  
  data_list <- vector("list", length = nperm)
  
  for (i in 1:nperm){
    
    shuffled_data <- permute_treatment_history(data,
                                               treatment_status,
                                               cluster_var,
                                               time_col,
                                               event_time_col,
                                               under_treatment_col)
    
    res <- impute_did(shuffled_data,
                      id_col=id_col,
                      time_col=time_col,
                      event_time_col=event_time_col,
                      under_treatment_col=under_treatment_col,
                      outcome_col=outcome_col,
                      time_fe_col=time_fe_col,
                      iter=iter,
                      tol=tol)
    
    att.null <- res$att %>% select(r,ATT)
    att.null$replicate <- i
    data_list[[i]] <- att.null
    
    print(glue("{outcome_col} replicate {i} / {nperm}"))
    
  }
  
  # Create indicator variable for instances when permuted treatment history
  # results in an ATT estimate that is more extreme than actual treatment history
  att.null <- bind_rows(data_list) %>% rename(ATT.permuted = ATT)
  att.null <- left_join(att.null,att.est,by="r")
  att.null$permuted.more.extreme <- as.integer(abs(att.null$ATT.permuted) >= abs(att.null$ATT.actual))
  
  # Compute Fisher exact p-value
  perm.p.value <- att.null %>% 
    group_by(r) %>% 
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

# Keep only geographic unit, time, treatment indicators, and event time variables
treatment_status <- treatment_status[,c(params$cluster_var,
                                        "year",params$treatment_variable,
                                        params$treatment_event,
                                        params$event_time)]

### *** CONDUCT PERMUTATION TESTS *** ###

## 60+ days delinquent
res <- permutation_test(panel_data,
                        outcome_col="D60",
                        id_col="loanid",
                        time_col="year",
                        event_time_col=params$event_time,
                        under_treatment_col=params$treatment_variable,
                        time_fe_col="region_time",
                        cluster_var=params$cluster_var,
                        nperm=nperm)

save_result_as_parquet(res,fitted_dir,proptype,"D60")

## Occupancy
res <- permutation_test(panel_data,
                        outcome_col="occ",
                        id_col="loanid",
                        time_col="year",
                        event_time_col=params$event_time,
                        under_treatment_col=params$treatment_variable,
                        time_fe_col="region_time",
                        cluster_var=params$cluster_var,
                        nperm=nperm)

save_result_as_parquet(res,fitted_dir,proptype,"occ")

## Net operating income
res <- permutation_test(panel_data,
                        outcome_col="log_noi",
                        id_col="loanid",
                        time_col="year",
                        event_time_col=params$event_time,
                        under_treatment_col=params$treatment_variable,
                        time_fe_col="region_time",
                        cluster_var=params$cluster_var,
                        nperm=nperm)

save_result_as_parquet(res,fitted_dir,proptype,"noi")

## Revenues
res <- permutation_test(panel_data,
                        outcome_col="log_rev",
                        id_col="loanid",
                        time_col="year",
                        event_time_col=params$event_time,
                        under_treatment_col=params$treatment_variable,
                        time_fe_col="region_time",
                        cluster_var=params$cluster_var,
                        nperm=nperm)

save_result_as_parquet(res,fitted_dir,proptype,"rev")

## Expenses
res <- permutation_test(panel_data,
                        outcome_col="log_exp",
                        id_col="loanid",
                        time_col="year",
                        event_time_col=params$event_time,
                        under_treatment_col=params$treatment_variable,
                        time_fe_col="region_time",
                        cluster_var=params$cluster_var,
                        nperm=nperm)

save_result_as_parquet(res,fitted_dir,proptype,"exp")

## DSCR < 1.0
res <- permutation_test(panel_data,
                        outcome_col="dscr_below_one",
                        id_col="loanid",
                        time_col="year",
                        event_time_col=params$event_time,
                        under_treatment_col=params$treatment_variable,
                        time_fe_col="region_time",
                        cluster_var=params$cluster_var,
                        nperm=nperm)

save_result_as_parquet(res,fitted_dir,proptype,"dscr_below_one")

## Missing NOI data
res <- permutation_test(panel_data,
                        outcome_col="missing_noi",
                        id_col="loanid",
                        time_col="year",
                        event_time_col=params$event_time,
                        under_treatment_col=params$treatment_variable,
                        time_fe_col="region_time",
                        cluster_var=params$cluster_var,
                        nperm=nperm)

save_result_as_parquet(res,fitted_dir,proptype,"missing_noi")
