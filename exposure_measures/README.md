# Flood Treatment Status

This folder contains scripts for determining the flood exposure and treatment status of US census tracts based on National Flood Insurance Program (NFIP) claim rates. The pipeline proceeds in the order described below.

Each step includes a Python script (`.py`) and a corresponding SLURM batch script (`.sh`) for cluster submission.

---

## Execution Order

### Step 1 — `build_crosswalks` (.py / .sh)
Constructs one-to-one geographic crosswalks between census block groups and census tracts across different decennial vintages (2000, 2010, 2020). For each source block group, the target tract is selected by maximizing the number of buildings with overlapping assignments, using building footprint data from the geocoding pipeline. All crosswalks are saved as both Parquet and CSV files.

**Prerequisite:** Requires `structure_info/` output from the geocoding pipeline.

**Output** (`crosswalks/`):
- `bg2020_tr2010_crosswalk` — 2020 block groups → 2010 tracts
- `bg2000_tr2010_crosswalk` — 2000 block groups → 2010 tracts
- `bg2010_tr2020_crosswalk` — 2010 block groups → 2020 tracts
- `bg2000_tr2020_crosswalk` — 2000 block groups → 2020 tracts

---

### Step 2 — `calculate_claim_rate` (.py / .sh)
Calculates annual NFIP flood claim rates at the 2010 census tract level. OpenFEMA policy and claim records report census block group GEOIDs without specifying the decennial vintage; this script infers the most likely vintage for each record year by comparing match rates against 2000, 2010, and 2020 block group GEOIDs. Records are then mapped to 2010 census tracts using the crosswalks from Step 1. Claim rates are expressed as claims per policy-year, where policy-year is derived from the daily count of policies in force aggregated to the tract-year level.

**Output:**
- `NFIP_claim_rate_by_tract.parquet` — annual claim rate per policy-year by 2010 census tract
- `census_vintage_match_rate_claims.parquet` — census vintage match rates for claim records by year
- `census_vintage_match_rate_policies.parquet` — census vintage match rates for policy records by year

---

### Step 3 — `tract_treatment_status` (.py / .sh)
Assigns time-varying flood treatment and spillover status to each census tract using the claim rate data from Step 2. A tract is classified as "treated" (flood-exposed) in any year where its claim rate exceeds a specified threshold, and remains treated for a specified number of subsequent years. Spillover status is separately assigned to tracts neighboring a treated tract (but not themselves treated) using a graph-based representation of tract adjacency. The script also tracks repeated treatment events and time elapsed since treatment onset.

The batch script runs the script multiple times to produce results under different claim rate threshold and treatment duration scenarios.

**Output** (`tract_exposure/`):
- `{scenario_name}_treatment_status.parquet` — one file per scenario
