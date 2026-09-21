# Geocoding

This folder contains scripts for parsing, geocoding, and spatially matching commercial property addresses from CMBS loan data to building footprints and land parcels. The pipeline proceeds in the order described below.

Each step includes a Python script (`.py`) and a corresponding SLURM batch script (`.sh`) for cluster submission. Jupyter notebooks (`.ipynb`) are run interactively and process cases in configurable batches (default: 10 per session), saving progress automatically so sessions can be paused and resumed.

---

## Execution Order

### Step 1 — `create_address_list` (.py / .sh)
Extracts loan-level address fields (property name, address, city, state, zip) from the filtered loans dataset and saves a deduplicated address list for use in subsequent steps.

**Output:** `geocoding_input/filtered_loans_address_data.parquet`

---

### Step 2 — `parse_address_local_llm` (.py / .sh)
Uses two quantized local LLMs (Qwen3.5-9B and Gemma-4-12B) running via vLLM to parse raw address strings into structured JSON components (e.g., building numbers, street names, address type). Processes addresses in chunks and saves results incrementally. The prompts and few-shot examples used for parsing are defined in `llm_address_parsing_prompts.py`, which is imported automatically and does not need to be run directly.

**Output:** `llm_address_parsing/{MODEL_NAME}/parsed_address_data_chunk_*.parquet`

---

### Step 3 — `check_consistency_of_parsed_addresses` (.py / .sh)
Compares parsed addresses across both LLMs to identify consistent and inconsistent results. Saves three output files: addresses on which the models agreed, a random sample of 500 consistent addresses for accuracy validation, and addresses flagged for manual review due to model disagreement or parsing failure.

**Output:**
- `geocoding_input/consistent_parsed_addresses.parquet`
- `geocoding_input/consistent_parsed_addresses_random_sample.parquet`
- `geocoding_input/manual_review_parsed_addresses.parquet`

---

### Step 4 — `manual_review_inconsistent_addresses` (Jupyter notebook)
Interactive notebook for manually resolving addresses where the two LLMs produced different parsed outputs. Presents both model outputs side-by-side and prompts the reviewer to select the correct parse or enter a custom response. Input is validated against the address component schema before submission.

**Input:** `geocoding_input/manual_review_parsed_addresses.parquet`  
**Output:** `manual_review/inconsistent_address_parsing/review_results.parquet`

---

### Step 4b *(Optional)* — `manual_review_consistent_addresses` (Jupyter notebook)
Interactive notebook for validating a random sample of consistently-parsed addresses. The reviewer independently parses each address string and their result is compared against the LLM output, flagging any discrepancies to assess model accuracy. This step is for quality control only — its output is not used by any downstream scripts. It can be run any time after Step 3.

**Input:** `geocoding_input/consistent_parsed_addresses_random_sample.parquet`  
**Output:** `manual_review/random_sample_validation/accuracy_review_results.parquet`

---

### Step 5 — `queens_address_filtering` (.py / .sh)
Identifies loan addresses located in Queens, NYC (filtered by zip code prefix), which use a distinctive hyphenated address format (e.g., `147-22 Jamaica Avenue`) that LLMs frequently misclassify. Converts the most common parsing error ("range" → "queens_exact") to produce an initial guess for manual review.

**Output:** `geocoding_input/queens_addresses_for_review.parquet`

---

### Step 6 — `manual_review_queens_addresses` (Jupyter notebook)
Interactive notebook for manually reviewing and correcting parsed address components for Queens, NYC properties. Presents each address alongside its current parsed output, allowing the reviewer to accept or edit the result. Input is validated against the address component schema before submission.

**Input:** `geocoding_input/queens_addresses_for_review.parquet`  
**Output:** `manual_review/queens_addresses/review_results.parquet`

---

### Step 7 — `combine_parsed_address_data` (.py / .sh)
Merges parsed address data from three sources — LLM-consistent addresses, manually-reviewed inconsistent addresses, and manually-reviewed Queens addresses — into a single dataset. Queens addresses take precedence and are deduplicated from the other sources. The combined result is joined back onto the original loan-level data.

**Output:** `geocoding_input/filtered_loans_parsed_address_data.parquet`

---

### Step 8 — `expand_addresses` (.py / .sh)
Converts structured address components into formatted query strings for geocoding. Range-type addresses (e.g., `100–150 Main Street`) are expanded into individual building-level addresses. Approximate addresses (e.g., intersections) without a building number are dropped. Produces one row per candidate building-level address.

**Output:** `geocoding_input/addresses_to_geocode.parquet`

---

### Step 9 — `geocoding_here_api` (.py / .sh)
Geocodes each candidate address using the HERE Geocoding & Search API. Processes addresses in chunks and saves results incrementally to allow restarts. Returns geocoded coordinates, matched address components, and query/field-level match quality scores.

**Output:** `geocoding_output/geocoding_output_here_api.parquet`

---

### Step 10 — `attach_info_to_structures` (.py / .sh)
SLURM array job (one task per state) that enriches building footprints from the USA Structures dataset with geospatial attributes including county boundaries (2010/2022 vintages), census block groups (2000/2010/2020), ZIP code tabulation areas (ZCTAs), FEMA flood zones (NFHL), and parcel IDs. **This step has no dependencies on Steps 1–9 and can be run in parallel with the address parsing pipeline.**

**Output:** `structure_info/{STATE}/{STATE}_structure_info.parquet`

---

### Step 11 — `evaluate_building_proximity_here_api` (.py / .sh)
SLURM array job (one task per state) that evaluates the distance between each geocoded address point and the nearest building footprint. Addresses within 30 meters of a building are retained; those that exceed this threshold or that were only geocoded to a street or approximate location are flagged for potential re-geocoding using an alternative API.

**Output:**
- `geocoding_output/within_tolerance/here_api/{STATE}_addresses_within_tolerance_here_api.parquet`
- `geocoding_output/outside_tolerance/here_api/{STATE}_addresses_outside_tolerance_here_api.parquet`

---

### Step 12 — `combine_buildings_parcels` (.py / .sh)
SLURM array job (one task per state) that links each geocoded loan to its associated building footprint(s) and land parcel(s). Identifies both direct building matches (from geocoding) and indirect matches (other buildings sharing the same parcel). Saves loan-level match metadata, matched building footprints, and matched parcel geometries as separate output files.

**Output:**
- `property_geospatial_data/match_info/{STATE}_match_info.parquet`
- `property_geospatial_data/matched_buildings/{STATE}_matched_buildings.parquet`
- `property_geospatial_data/matched_parcels/{STATE}_matched_parcels.parquet`
