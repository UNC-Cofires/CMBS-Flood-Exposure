library(glue)
library(here)
library(yaml)
library(optparse)
library(jsonlite)
library(arrow)
library(parallelly)
library(car)
library(dplyr)
library(tidyr)
library(tibble)
library(fect)

### *** HELPER FUNCTIONS *** ###

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

in_time_placebo_test <- function(res, panel_data, params, alpha=0.05) {
  # res: list containing postprocessed fect ATT estimates and bootstrap replicates
  # panel_data: data used in estimation sample
  # params: list containing options used when fitting model
  #         (e.g., variable used to define clusters when calculating SEs)
  # alpha: significance level used when constructing TOST minimum equivalence range
  
  att.est <- res$att.est
  att.rep <- res$att.rep
  event_time_user <- params$event_time

  # Filter for periods under placebo treatment
  att.est <- att.est[att.est[[event_time_user]] >= 0,]
  
  ### --- t-test p-value --- ###
  # Tests the joint null hypothesis that ATT = 0 for all placebo periods.
  # Rejecting H0 provides evidence against parallel trends assumption. 
  
  # Create matrix of ATT estimates where rows correspond to bootstrap replicates
  # and columns correspond to event time. 
  att.wide <- att.rep %>%
    pivot_wider(names_from = all_of(event_time_user), values_from = estimate) %>%
    column_to_rownames(var="replicate")
  
  # Calculate variance-covariance matrix
  V  <- cov(as.matrix(att.wide))
  
  # Get point estimates
  b_hat <- att.est$estimate
  
  # Get number of clusters (needed for calculating degrees of freedom)
  G <- length(unique(panel_data[[params$cluster_var]]))
  
  # Conduct Wald and F-test
  placebo_test_results <- wald_pre_test(b_hat, V, G)
  
  ### --- two one-sided tests (TOST) equivalence range --- ###
  # Tests the null hypothesis that ATT < -delta or ATT > delta. 
  # Rejecting H0 provides evidence for parallel trends assumption. 
  
  # Note that because we are doing two one-sided tests, the critical value
  # is determined based on 1-alpha instead of 1-alpha/2. 
  z <- qnorm(1-alpha)
  att.est$ci.lo <- att.est$estimate - z*att.est$se
  att.est$ci.hi <- att.est$estimate + z*att.est$se
  
  # Following the approach of Hartman & Hidalgo (2018), the minimum equivalence range
  # delta is equal to the the maximum absolute value of the 100*(1-alpha)% CI. When 
  # the number of placebo periods is large, this approach is conservative. 
  delta <- max(max(abs(att.est$ci.lo)),max(abs(att.est$ci.hi)))
  
  placebo_test_results$TOST_alpha <- alpha
  placebo_test_results$TOST_delta <- delta
  
  return(placebo_test_results)
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

### *** LOAD DATA *** ###

# Data used in estimation sample
panel_data <- readRDS(file.path(fitted_dir,glue("{params$proptype}_data.rds")))

# Postprocessed ATT estimates and bootstrap replicates
D60_res <- readRDS(file.path(fitted_dir,glue("{params$proptype}_D60_postprocessed.rds")))
loss_rate_res <- readRDS(file.path(fitted_dir,glue("{params$proptype}_loss_rate_postprocessed.rds")))
occ_res <- readRDS(file.path(fitted_dir,glue("{params$proptype}_occ_postprocessed.rds")))
noi_res <- readRDS(file.path(fitted_dir,glue("{params$proptype}_noi_postprocessed.rds")))
rev_res <- readRDS(file.path(fitted_dir,glue("{params$proptype}_rev_postprocessed.rds")))
exp_res <- readRDS(file.path(fitted_dir,glue("{params$proptype}_exp_postprocessed.rds")))

### *** CONDUCT IN-TIME PLACEBO TESTS FOR PRE-TRENDS / CARRYOVER EFFECTS *** ###

# Initialize empty list
placebo_test_results <- list()

# Conduct in-time placebo tests for each outcome
placebo_test_results$D60 <- in_time_placebo_test(D60_res, panel_data, params)
placebo_test_results$loss_rate <- in_time_placebo_test(loss_rate_res, panel_data, params)
placebo_test_results$occ <- in_time_placebo_test(occ_res, panel_data, params)
placebo_test_results$noi <- in_time_placebo_test(noi_res, panel_data, params)
placebo_test_results$rev <- in_time_placebo_test(rev_res, panel_data, params)
placebo_test_results$exp <- in_time_placebo_test(exp_res, panel_data, params)

### *** SAVE RESULTS *** ###

write(
  toJSON(placebo_test_results, pretty = TRUE, auto_unbox = TRUE),
  file.path(fitted_dir, "placebo_test_in_time.json")
)





