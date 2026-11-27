library(dplyr)
library(tidyr)
library(tibble)
library(fixest)

# Function to re-sample data by cluster with replacement

cluster_bootstrap <- function(data,cluster_var="zipcode",unit_id="loanid"){
  
  cluster_ids <- unique(data[[cluster_var]])
  num_clusters <- length(cluster_ids)
  
  resampled_data <- data.frame(
    draw_id = paste0("draw",seq(1:num_clusters)),
    cluster_id = sample(cluster_ids, size = num_clusters, replace = TRUE)
  )
  
  resampled_data <- left_join(resampled_data,
                              data,
                              by=c("cluster_id" = cluster_var),
                              relationship = "many-to-many")
  
  resampled_data$pseudo_id <- paste(resampled_data$draw_id,resampled_data[[unit_id]],sep="-")
  
  return(resampled_data)
}

# Function to implement the imputation-based DiD estimator described by 
# Liu, Wang, & Xu (2024) and Borusyak, Jaravel & Spiess (2024)
impute_did <- function(data,
                       id_col="loanid",
                       time_col="year",
                       event_time_col="time_since_treatment_event",
                       under_treatment_col="under_treatment",
                       outcome_col="occ",
                       time_fe_col="region_time",
                       iter=50000,
                       tol=1e-6){
  
  # Make sure required columns are present
  required_cols <- unique(c(id_col,
                            time_col,
                            under_treatment_col,
                            outcome_col,
                            time_fe_col))
  
  data <- data[complete.cases(data[,required_cols]),]

  # Create cleaned version of id and time columns
  data$id <- data[[id_col]]
  data$t <- data[[time_col]]
  
  # Create cleaned version of treatment, event time, and outcome columns
  data$D <- data[[under_treatment_col]]
  data$r <- data[[event_time_col]]
  data$Y <- data[[outcome_col]]
  
  # Create unit and time FE columns
  data$unit_fe <- as.factor(data[[id_col]])
  data$time_fe <- as.factor(data[[time_fe_col]])
  
  # Get duration of treatment
  treatment_duration <- max(data$r,na.rm = TRUE) + 1
  
  # Get columns of interest
  relevant_cols <- c("id","t","unit_fe","time_fe","D","r","Y")
  data <- data[,relevant_cols]
  
  # Separate out untreated observations
  untreated_obs <- data[data$D==0,]
  
  # Separate out treated observations plus untreated leads
  leads_lags <- seq(from=-1*treatment_duration,to=treatment_duration-1,by=1)
  treated_obs <- data[data$r %in% leads_lags,]
  
  # Drop treated observations whose fixed effects don't show up in untreated dataframe
  unit_fe_mask <- (treated_obs$unit_fe %in% untreated_obs$unit_fe)
  time_fe_mask <- (treated_obs$time_fe %in% untreated_obs$time_fe)
  treated_obs <- treated_obs[unit_fe_mask & time_fe_mask,]
  
  treated_obs$unit_fe <- factor(treated_obs$unit_fe,
                                levels=levels(untreated_obs$unit_fe))
  
  treated_obs$time_fe <- factor(treated_obs$time_fe,
                                levels=levels(untreated_obs$time_fe))
  
  # Fit outcome model using untreated observations
  outcome_mod <- feols(Y ~ 1 | unit_fe + time_fe,
                       data = untreated_obs,
                       fixef.iter = iter, fixef.tol = tol, fixef.rm = "none")
  
  # Predict counterfactual outcomes for treated observations
  treated_obs$Y0_hat <- predict(outcome_mod, newdata = treated_obs)
  treated_obs <- treated_obs %>% rename(Y_obs = Y)
  treated_obs$Y_delta <- treated_obs$Y_obs - treated_obs$Y0_hat
  
  # Aggregate by relative time since treatment
  att.est <- treated_obs %>% 
    group_by(r) %>% 
    summarize(
      Y_obs = mean(Y_obs),
      Y0_hat = mean(Y0_hat),
      ATT = mean(Y_obs - Y0_hat),
      n = n())
  
  # Save data and results as list
  res <- list(att=att.est,
              imputed.po=treated_obs)
  
  return(res)
}

# Function to calculate ATTs and SEs for the imputation-based DiD estimator 
# described by Liu, Wang, & Xu (2024) and Borusyak, Jaravel & Spiess (2024)

did_counterfactual_imputation <- function(data,
                                          id_col="loanid",
                                          time_col="year",
                                          event_time_col="time_since_treatment_event",
                                          under_treatment_col="under_treatment",
                                          outcome_col="occ",
                                          time_fe_col="region_time",
                                          cluster_var="zipcode",
                                          nboot=200,
                                          alpha=0.05,
                                          iter=50000,
                                          tol=1e-6){
  
  # Get point estimate of ATT
  res <- impute_did(data,
                    id_col=id_col,
                    time_col=time_col,
                    event_time_col=event_time_col,
                    under_treatment_col=under_treatment_col,
                    outcome_col=outcome_col,
                    time_fe_col=time_fe_col,
                    iter=iter,
                    tol=tol)
  
  att.est <- res$att
  imputed.po.est <- res$imputed.po
  
  # Get bootstrap replicates of ATT
  att.boot.list <- vector("list", length = nboot)
  imputed.po.boot.list <- vector("list", length = nboot)
  
  for (i in 1:nboot){
    
    replicate_data <- cluster_bootstrap(data,cluster_var=cluster_var,unit_id=id_col)
    
    res <- impute_did(replicate_data,
                      id_col="pseudo_id",
                      time_col=time_col,
                      event_time_col=event_time_col,
                      under_treatment_col=under_treatment_col,
                      outcome_col=outcome_col,
                      time_fe_col=time_fe_col,
                      iter=iter,
                      tol=tol)
    
    att.rep <- res$att
    imputed.po.rep <- res$imputed.po
    
    # Replace pseudo unit ids with actual unit ids
    id_lookup <- distinct(replicate_data[,c(id_col,"pseudo_id")]) %>% rename(id := !!id_col)
    
    imputed.po.rep <- imputed.po.rep %>%
      rename(pseudo_id = id) %>%
      left_join(id_lookup,by="pseudo_id") %>%
      select(-pseudo_id) %>% 
      relocate(id)
    
    att.rep$replicate <- i
    imputed.po.rep$replicate <- i
    
    att.boot.list[[i]] <- att.rep
    imputed.po.boot.list[[i]] <- imputed.po.rep
    
  }
  
  # Concatenate bootstrapped estimates
  att.rep <- bind_rows(att.boot.list)
  imputed.po.rep <- bind_rows(imputed.po.boot.list)
  
  # Rename columns
  att.est <- att.est %>% select(c("r","Y_obs","Y0_hat","ATT","n")) %>% rename(n_cells = n)
  att.rep <- att.rep %>% select(c("r","Y_obs","Y0_hat","ATT","replicate"))
  
  # Calculate bootstrapped SEs, CIs, and p-values for ATT estimates
  se.est <- att.rep %>%
    group_by(r) %>%
    summarize(se = sd(ATT))
  
  att.est <- left_join(att.est,se.est,by="r")
  
  z <- qnorm(1-alpha/2)
  att.est$ci.lo <- att.est$ATT - z*att.est$se
  att.est$ci.hi <- att.est$ATT + z*att.est$se
  
  z_stat = att.est$ATT/att.est$se
  att.est$p.value <- 2 * pnorm(-abs(z_stat))
  
  att.est <- att.est %>% relocate(n_cells, .after = last_col())
  
  # Combine data into a single object and return results 
  res <- list(att.est=att.est,
              att.rep=att.rep,
              imputed.po.est=imputed.po.est,
              imputed.po.rep=imputed.po.rep)
  
  return(res)
}


# Function to impute the untreated cumulative incidence function 
# of the target event under competing risks. 

impute_cif <- function(data,
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
  data$Y_competing <- as.integer(rowSums(data[,competing_outcomes, drop = FALSE]) >= 1)
  data$Y_competing <- as.integer((data$Y_competing == 1)&(data$Y_target != 1))
  data$Y_any <- as.integer((data$Y_target==1)|(data$Y_competing == 1))
  
  # Get columns of interest
  relevant_cols <- c("id","t","baseline_hazard_strata","region","D","D_new","r","Y_target","Y_competing","Y_any")
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
  # can sometimes exceed one. Assuming you have a numerically-stable and well-fit
  # outcome model, then this occurence should be rare. However, when it happens, 
  # we'll need to to normalize the output probabilities while preserving share of
  # each event cause.
  adjusted_mask <- (p_any > 1.0)
  p_target[adjusted_mask] <- p_target[adjusted_mask]/p_any[adjusted_mask]
  p_competing[adjusted_mask] <- p_competing[adjusted_mask]/p_any[adjusted_mask]
  p_any[adjusted_mask] <- 1.0
  
  # Save counterfactual hazard estimates
  treatment_cohorts$adjusted_prob <- adjusted_mask
  treatment_cohorts$h0_target <- p_target
  treatment_cohorts$h0_competing <- p_competing
  treatment_cohorts$h0_any <- p_any
  
  # Impute counterfactual cumulative incidence of target event
  treatment_cohorts <- treatment_cohorts %>% 
    group_by(id,g) %>% 
    mutate(S0 = lag(cumprod(1 - h0_any), n = 1, default = 1.0),
           F0_hat = cumsum(S0*h0_target),
           F_delta = F_obs - F0_hat) %>%
    ungroup()
  
  # Aggregate by relative time since treatment
  att.est <- treatment_cohorts %>% 
    group_by(r) %>% 
    summarize(
      F_obs = mean(F_obs),
      F0_hat = mean(F0_hat),
      ATT = mean(F_obs - F0_hat),
      n = n())
  
  # Save data and results as list
  res <- list(att=att.est,
              imputed.po=treatment_cohorts)
  
  return(res)
}

# Function to estimate the effect of treatment on the cumulative incidence
# of the target event, plus associated standard errors. 

cif_counterfactual_imputation <- function(data,
                                          id_col="loanid",
                                          time_col="year",
                                          event_time_col="time_since_treatment_event",
                                          treatment_event_col="treatment_event",
                                          under_treatment_col="under_treatment",
                                          target_outcome="D60",
                                          competing_outcomes=c("zero_balance_flag","defeased_released_flag"),
                                          baseline_hazard_strata="vintage_term",
                                          region_strata="cbsa_title",
                                          cluster_var="zipcode",
                                          nboot=200,
                                          alpha=0.05,
                                          iter=50000,
                                          tol=1e-6){
  
  # Get point estimate of ATT
  res <- impute_cif(data,
                    id_col=id_col,
                    time_col=time_col,
                    event_time_col=event_time_col,
                    treatment_event_col=treatment_event_col,
                    under_treatment_col=under_treatment_col,
                    target_outcome=target_outcome,
                    competing_outcomes=competing_outcomes,
                    baseline_hazard_strata=baseline_hazard_strata,
                    region_strata=region_strata,
                    iter=iter,
                    tol=tol)
  
  att.est <- res$att
  imputed.po.est <- res$imputed.po
  
  # Get bootstrap replicates of ATT
  att.boot.list <- vector("list", length = nboot)
  imputed.po.boot.list <- vector("list", length = nboot)
  
  for (i in 1:nboot){
    
    replicate_data <- cluster_bootstrap(data,cluster_var=cluster_var,unit_id=id_col)
    
    res <- impute_cif(replicate_data,
                      id_col="pseudo_id",
                      time_col=time_col,
                      event_time_col=event_time_col,
                      treatment_event_col=treatment_event_col,
                      under_treatment_col=under_treatment_col,
                      target_outcome=target_outcome,
                      competing_outcomes=competing_outcomes,
                      baseline_hazard_strata=baseline_hazard_strata,
                      region_strata=region_strata,
                      iter=iter,
                      tol=tol)
    
    att.rep <- res$att
    imputed.po.rep <- res$imputed.po
    
    # Replace pseudo unit ids with actual unit ids
    id_lookup <- distinct(replicate_data[,c(id_col,"pseudo_id")]) %>% rename(id := !!id_col)
    
    imputed.po.rep <- imputed.po.rep %>%
      rename(pseudo_id = id) %>%
      left_join(id_lookup,by="pseudo_id") %>%
      select(-pseudo_id) %>% 
      relocate(id)
    
    att.rep$replicate <- i
    imputed.po.rep$replicate <- i
    
    att.boot.list[[i]] <- att.rep
    imputed.po.boot.list[[i]] <- imputed.po.rep
    
  }
  
  # Concatenate bootstrapped estimates
  att.rep <- bind_rows(att.boot.list)
  imputed.po.rep <- bind_rows(imputed.po.boot.list)
  
  # Rename columns
  att.est <- att.est %>% select(c("r","F_obs","F0_hat","ATT","n")) %>% rename(n_cells = n)
  att.rep <- att.rep %>% select(c("r","F_obs","F0_hat","ATT","replicate"))
  
  # Calculate bootstrapped SEs, CIs, and p-values for ATT estimates
  se.est <- att.rep %>%
    group_by(r) %>%
    summarize(se = sd(ATT))
  
  att.est <- left_join(att.est,se.est,by="r")
  
  z <- qnorm(1-alpha/2)
  att.est$ci.lo <- att.est$ATT - z*att.est$se
  att.est$ci.hi <- att.est$ATT + z*att.est$se
  
  z_stat = att.est$ATT/att.est$se
  att.est$p.value <- 2 * pnorm(-abs(z_stat))
  
  att.est <- att.est %>% relocate(n_cells, .after = last_col())
  
  # Combine data into a single object and return results 
  res <- list(att.est=att.est,
              att.rep=att.rep,
              imputed.po.est=imputed.po.est,
              imputed.po.rep=imputed.po.rep)
  
  return(res)
}


wald_pre_test <- function(b_hat, V, G) {
  # b_hat: numeric vector of k pre-period ATT estimates (original sample)
  # V:     k x k bootstrap covariance matrix, same order as b_hat
  # G:     number of clusters (zip codes) in the estimation sample
  
  # Convert estimates to a plain numeric vector / matrix (drops names)
  b <- as.numeric(b_hat)
  V <- unname(as.matrix(V))
  
  # Number of pre-period coefficients being tested jointly
  k <- length(b)
  
  # Wald statistic: W = b' V^-1 b
  # solve(V, b) computes V^-1 b without forming the explicit inverse
  # crossprod(b, x) computes t(b) %*% x
  # drop() converts the 1x1 matrix result to a plain number
  W <- drop(crossprod(b, solve(V, b)))
  
  # Collect the results in a list
  list(
    k = k,                                          # numerator df / number of restrictions
    W = W,                                          # Wald statistic, ~ chi-square(k) under H0
    F = W / k,                                      # F statistic: Wald statistic divided by k
    df1 = k,                                        # F numerator degrees of freedom
    df2 = G - 1,                                    # F denominator df (cluster-robust convention)
    p_F = pf(W / k, k, G - 1, lower.tail = FALSE),  # p-value from F(k, G - 1), upper tail
    p_chisq = pchisq(W, k, lower.tail = FALSE)      # p-value from chi-square(k), upper tail
  )
}

in_time_placebo_test <- function(res, panel_data, cluster_var, alpha=0.05) {
  # res: list containing ATT estimates and bootstrap replicates
  # panel_data: data used in estimation sample
  # cluster_var: level at which to cluster SEs (affects degrees of freedom)
  # alpha: significance level used when constructing TOST minimum equivalence range
  
  att.est <- res$att.est %>% select(c(r,ATT,se))
  att.rep <- res$att.rep %>% select(c(r,ATT,replicate))
  
  # Filter for periods under placebo treatment
  att.est <- att.est[att.est$r >= 0,]
  att.rep <- att.rep[att.rep$r >= 0,]
  
  ### --- t-test p-value --- ###
  # Tests the joint null hypothesis that ATT = 0 for all placebo periods.
  # Rejecting H0 provides evidence against parallel trends assumption. 
  
  # Create matrix of ATT estimates where rows correspond to bootstrap replicates
  # and columns correspond to event time. 
  att.wide <- att.rep %>%
    pivot_wider(names_from = r, values_from = ATT) %>%
    column_to_rownames(var="replicate")
  
  # Calculate variance-covariance matrix
  V  <- cov(as.matrix(att.wide))
  
  # Get point estimates
  b_hat <- att.est$ATT
  
  # Get number of clusters (needed for calculating degrees of freedom)
  G <- length(unique(panel_data[[cluster_var]]))
  
  # Conduct Wald and F-test
  placebo_test_results <- wald_pre_test(b_hat, V, G)
  
  ### --- two one-sided tests (TOST) equivalence range --- ###
  # Tests the null hypothesis that ATT < -delta or ATT > delta. 
  # Rejecting H0 provides evidence for parallel trends assumption. 
  
  # Note that because we are doing two one-sided tests, the critical value
  # is determined based on 1-alpha instead of 1-alpha/2. 
  z <- qnorm(1-alpha)
  att.est$ci.lo <- att.est$ATT - z*att.est$se
  att.est$ci.hi <- att.est$ATT + z*att.est$se
  
  # Following the approach of Hartman & Hidalgo (2018), the minimum equivalence range
  # delta is equal to the the maximum absolute value of the 100*(1-alpha)% CI. When 
  # the number of placebo periods is large, this approach is conservative. 
  delta <- max(max(abs(att.est$ci.lo)),max(abs(att.est$ci.hi)))
  
  placebo_test_results$TOST_alpha <- alpha
  placebo_test_results$TOST_delta <- delta
  
  return(placebo_test_results)
}
