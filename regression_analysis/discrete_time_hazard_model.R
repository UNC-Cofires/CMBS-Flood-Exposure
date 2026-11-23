library(dplyr)
library(tidyr)
library(fixest)

# Function to estimate the causal effect of flood exposure 
# on the cumulative incidence function (CIF) under competing risks

counterfactual_cumulative_incidence <- function(data,
                                                id_col="loanid",
                                                time_col="year",
                                                event_time_col="time_since_treatment_event",
                                                treatment_event_col="treatment_event",
                                                under_treatment_col="under_treatment",
                                                target_outcome="D60",
                                                competing_outcomes=c("zero_balance_flag","defeased_released_flag"),
                                                baseline_hazard_strata="vintage_term",
                                                region_strata="cbsa_title",
                                                iter=50000,
                                                tol=1e-6){
  
  # Make sure required columns are present
  required_cols <- c(id_col,
                     time_col,
                     treatment_event_col,
                     under_treatment_col,
                     baseline_hazard_strata,
                     region_strata,
                     target_outcome)
  
  required_cols <- c(required_cols,competing_outcomes)
  
  data <- data[complete.cases(data[,required_cols]),]
  
  # Create cleaned version of id and time columns
  data$id <- data[[id_col]]
  data$t <- data[[time_col]]
  
  # Create variables baseline hazard and region
  data$baseline_hazard_strata <- as.factor(data[[baseline_hazard_strata]])
  data$region <- as.factor(data[[region_strata]])
  
  # Create cleaned version of treatment columns
  data$D <- data[[under_treatment_col]]
  data$D_new <- data[[treatment_event_col]]
  data$r <- data[[event_time_col]]
  
  # Get duration of treatment
  treatment_duration <- max(data$r,na.rm = TRUE) + 1
  
  # Create indicator variables for event of interest + competing events
  data$Y_target <- as.integer(data[[target_outcome]] == 1)
  data$Y_competing <- as.integer(rowSums(data[,competing_outcomes]) >= 1)
  data$Y_competing <- as.integer((data$Y_competing == 1)&(data$Y_target != 1))
  data$Y_any <- as.integer((data$Y_target==1)|(data$Y_competing == 1))
  
  # Get columns of interest
  relevant_cols <- c(c("id","t","baseline_hazard_strata","region","D","D_new","r","Y_target","Y_competing","Y_any"))
  data <- data[,relevant_cols]
  
  # Drop entries after outcome occurs
  data <- data %>%
    group_by(id) %>%
    filter(cumsum(lag(Y_any == 1, default = FALSE)) == 0) %>%
    ungroup()
  
  # Create indicator for censoring
  data <- data %>%
    group_by(id) %>%
    mutate(censored = ifelse(row_number() == n() & Y_any == 0, 1, 0)) %>%
    ungroup()
  
  # Split into treated and untreated observations
  untreated_obs <- data[data$D==0,]
  treated_obs <- data[data$D==1,]
  
  # Create treatment cohorts
  treatment_cohorts <- treated_obs[treated_obs$D_new==1,c("id","t","baseline_hazard_strata","region")]
  treatment_cohorts <- treatment_cohorts %>% rename(g = t)
  
  # Explode cohorts dataframe so that each loan has one row per potential year under treatment
  treatment_cohorts$r <- list(seq(treatment_duration)-1)
  treatment_cohorts <- treatment_cohorts %>% unnest(r)
  treatment_cohorts$t <- treatment_cohorts$g + treatment_cohorts$r
  
  # Clean exploded dataframe
  censored_times <- treated_obs[treated_obs$censored == 1,c("id","t")] %>% rename(T_censored = t)
  treatment_cohorts <- left_join(treatment_cohorts,censored_times,by="id") %>% 
    filter(t <= T_censored | is.na(T_censored)) %>% 
    select(-T_censored)
  
  # To avoid double-counting with repetitive flood exposures, treat second flood as censoring event
  treatment_cohorts <- treatment_cohorts %>% arrange(id,t,desc(g))
  treatment_cohorts <- treatment_cohorts %>%
    group_by(id,t) %>%
    slice_head(n = 1) %>%
    ungroup() %>% 
    arrange(id,t)
  
  # Calculate observed cumulative incidence of target event
  treatment_cohorts <- left_join(treatment_cohorts,treated_obs[,c("id","t","Y_target")],by=join_by(id, t))
  
  treatment_cohorts <- treatment_cohorts %>% 
    group_by(id) %>% 
    fill(Y_target) %>% 
    rename(F_obs=Y_target) %>% 
    ungroup()
  
  # Create FEs for baseline hazard
  treatment_cohorts$baseline_hazard <- interaction(treatment_cohorts$baseline_hazard_strata,treatment_cohorts$t)
  untreated_obs$baseline_hazard <- interaction(untreated_obs$baseline_hazard_strata,untreated_obs$t)
  
  # Drop treated observations whose baseline hazard strata doesn't show up in untreated
  bh_mask <- (treatment_cohorts$baseline_hazard %in% untreated_obs$baseline_hazard)
  rg_mask <- (treatment_cohorts$region %in% untreated_obs$region)
  treatment_cohorts <- treatment_cohorts[bh_mask & rg_mask,]
  
  treatment_cohorts$baseline_hazard <- factor(treatment_cohorts$baseline_hazard,
                                              levels=levels(untreated_obs$baseline_hazard))
  
  treatment_cohorts$region <- factor(treatment_cohorts$region,
                                     levels=levels(untreated_obs$region))
  
  # Fit outcome models using untreated observations
  
  # Target event
  target_mod <- feglm(Y_target ~ 1 | baseline_hazard + region,
                      data = untreated_obs,
                      family = binomial(link="logit"),
                      fixef.iter = iter, fixef.tol = tol, fixef.rm = "none")
  
  # Competing events
  competing_mod <- feglm(Y_competing ~ 1 | baseline_hazard + region,
                         data = untreated_obs,
                         family = binomial(link="logit"),
                         fixef.iter = iter, fixef.tol = tol, fixef.rm = "none")
  
  # Use outcome models to predict counterfactual hazard for treated observations
  p_target <- predict(target_mod, newdata = treatment_cohorts)
  p_competing <- predict(competing_mod, newdata = treatment_cohorts)
  p_any <- p_target + p_competing
  
  # Because we fit separate binomial models, sum of all-cause probabilities
  # can sometimes exceed one. This is very rare, but when it happens, we'll need
  # to re-normalize the output probabilities while preserving relative share of
  # each event cause.
  adjusted_mask <- (p_any > 1.0)
  p_target[adjusted_mask] <- p_target[adjusted_mask]/p_any[adjusted_mask]
  p_competing[adjusted_mask] <- p_competing[adjusted_mask]/p_any[adjusted_mask]
  p_any[adjusted_mask] <- 1.0
  
  # Save counterfactual hazard estimates
  treatment_cohorts$adjustd_prob <- adjusted_mask
  treatment_cohorts$h0_target <- p_target
  treatment_cohorts$h0_competing <- p_competing
  treatment_cohorts$h0_any <- p_any
  
  # Impute counterfactual cumulative incidence of target event
  treatment_cohorts <- treatment_cohorts %>% 
    group_by(id,g) %>% 
    mutate(S0 = lag(cumprod(1 - h0_any), n = 1, default = 1.0),
           F0 = cumsum(S0*h0_target),
           F_delta = F_obs - F0) %>%
    ungroup()
  
  # Aggregate by relative time since treatment
  att.est <- treatment_cohorts %>% 
    group_by(r) %>% 
    summarize(
      F1 = mean(F_obs),
      F0 = mean(F0),
      ATT = mean(F_obs - F0),
      n = n())
  
  # Save results
  res <- list()
  res$att <- att.est
  res$imputed.po <- treatment_cohorts
  
  return(res)
}