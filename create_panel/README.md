# Create Panel

This folder contains scripts for selecting CMBS loans that meet the study's inclusion criteria and assembling a longitudinal dataset of loan-year observations with property outcomes and attributes. The pipeline proceeds in the order described below.

Each step includes a Python script (`.py`) and a corresponding SLURM batch script (`.sh`) for cluster submission.

---

## Execution Order

### Step 1 — `filter_loans` and `filter_properties` (.py / .sh)
Both scripts are run sequentially by `filter_loans.sh` and should be submitted together using that batch script.

**`filter_loans.py`** loads all loans from a specified list of public conduit CMBS deals originated between 1998 and 2025 and applies the following inclusion criteria in sequence:

1. **Non-delinquent at first observation** — excludes loans already in default when they first appear in the data
2. **Single-property** — excludes loans collateralized by multiple properties
3. **Single-note** — excludes loans that are part of a multi-note capital structure (e.g., A/B note splits, pari passu notes)
4. **Included states** — excludes loans collateralized by properties outside the list of included states

A stepwise selection flow is printed to `selection_flow.txt`.

**`filter_properties.py`** then retrieves all Trepp property records associated with the filtered loans and saves them as a separate file.

**Output:**
- `filtered_loans.parquet`
- `filtered_properties.parquet`
- `selection_flow.txt` — stepwise loan counts at each filtering stage

---

### Step 2 — `delineate_metro_areas` (.py / .sh)
Assigns Core-Based Statistical Area (CBSA) and Combined Statistical Area (CSA) codes to US counties using official OMB delineation files. Both metropolitan statistical areas (MSAs) and micropolitan statistical areas (µSAs) are included. Output is used in Step 3 to attach metro area groupings to each property. **This step has no dependency on Step 1 and can be run in parallel.**

**Output:** `metro_areas/county_metro_area_groupings.parquet`

---

### Step 3 — `assemble_panel_outcome_data` (.py / .sh)
Constructs a balanced loan-year panel for the study period (1998–2025) and attaches property-level outcomes and attributes. The script performs the following operations:

- **Delinquency outcomes** — derives indicators for 60-day delinquency (D60), 90-day delinquency (D90), and foreclosure/REO status, as well as "ever" versions of each that flag whether a loan has reached a given delinquency threshold at any prior point in time. Entries where a loan skips directly to D90+ without a recorded D60 are corrected so that delinquency thresholds are always nested (D60 ≥ D90 ≥ foreclosure/REO).
- **Realized losses** — attaches annual realized loss amounts and loss rates (as a percentage of original loan balance).
- **Property financials** — attaches revenues, operating expenses, net operating income (NOI), and occupancy rate for each loan-year.
- **Building attributes** — joins geocoded building footprint data from the geocoding pipeline, including coordinates, county FIPS code, 2010 census tract, 2020 ZCTA, number of matched structures, and FEMA flood zone indicators (100-year and 500-year floodplain).
- **Metro area groupings** — attaches CSA and CBSA codes and titles from Step 2. Loans collateralized by properties outside a CBSA are dropped from the panel.

A summary of the resulting panel is printed to `panel_summary.txt`. 

**Prerequisites:** Requires output from Steps 1 and 2, as well as matched building footprint data from [Step 12](https://github.com/UNC-Cofires/CMBS-Flood-Exposure/tree/main/geocoding#step-12--combine_buildings_parcels-py--sh) of the geocoding pipeline.

**Output:**
- `panel_outcome_data.parquet` — loan-year panel with all outcome and attribute variables
- `panel_summary.txt` — loan and loan-year counts, and population rates for key outcome fields
 