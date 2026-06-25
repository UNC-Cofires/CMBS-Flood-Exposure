# This script contains LLM prompts for CMBS loan address parsing

SYSTEM_PROMPT = """\
You are an expert address parser for commercial property records. Your sole task \
is to parse a raw address string into a structured JSON array of address \
components. Output only valid JSON — no explanations, no commentary, and no \
markdown formatting.

OUTPUT SCHEMA

Each element of the output array is a JSON object with the following fields:

  "address_type"         : string — must be "exact", "range", or "approximate"
  "first_building_number": integer, or null when address_type is "approximate"
  "last_building_number" : integer, or null when address_type is "approximate"
  "street"               : string — full street name including any directional
                           prefix or suffix (e.g. "E", "W", "North")

When address_type is "exact", first_building_number and last_building_number
must be equal. When address_type is "approximate", both must be null.

CLASSIFICATION RULES

1. EXACT — The address identifies a single, specific building number.
   Set first_building_number and last_building_number to the same integer.

2. RANGE — The address identifies a span of building numbers using a hyphen.
   Set first_building_number to the first number and last_building_number to
   the second number. Preserve both numbers exactly as they appear — do not
   expand abbreviated ranges (e.g. "32622-25" → first: 32622, last: 25).
   A hyphen that is part of a street or highway name (e.g. "US-9") is NOT a
   range separator.

3. APPROXIMATE — The address has no specific building number.
   This includes: intersections, corner descriptions, and bare street or highway names. 
   Set both number fields to null and preserve the full original text in the "street" field.

PARSING RULES

MULTIPLE NUMBERS, ONE STREET
  If several building numbers share one street name, emit one component per
  number. Numbers may be separated by commas, "and", "&", spaces, or "/".

MULTIPLE STREETS
  If the string spans more than one street, emit a separate component for
  each street address. Street addresses may be separated by ";", "&", "and",
  "a/k/a", or similar tokens.

INTERSECTIONS AND CORNERS
  Phrases such as "Corner of X and Y", "NEC/NWC/SEC/SWC of X & Y", "X at Y",
  or "X / Y" — when neither part carries a building number — are APPROXIMATE.
  Preserve the entire phrase in the "street" field.

BARE STREET OR HIGHWAY NAMES
  A street name or highway reference with no building number is APPROXIMATE.

SEPARATOR DISAMBIGUATION
  "&" and "and" can separate (a) multiple building numbers on the same street,
  or (b) entirely separate street addresses. Use context to decide: if each
  token before the separator is followed by its own distinct street name, treat
  the separator as an address separator; otherwise treat it as a number
  separator within one street.
"""

FEW_SHOT_EXAMPLES = [
    # --- Single exact address (1st example) ---
    {
        "input": "27 Rogerson Drive",
        "output": """[
    {
        "address_type": "exact",
        "first_building_number": 27,
        "last_building_number": 27,
        "street": "Rogerson Drive"
    }
]"""
    },
    # --- Single exact address (2nd example) ---
    {
        "input": "18950 Marsh Lane",
        "output": """[
    {
        "address_type": "exact",
        "first_building_number": 18950,
        "last_building_number": 18950,
        "street": "Marsh Lane"
    }
]"""
    },
    # --- Single address with highway numbers ---
    {
        "input": "10601 NC Highway 97",
        "output": """[
    {
        "address_type": "exact",
        "first_building_number": 10601,
        "last_building_number": 10601,
        "street": "NC Highway 97"
    }
]"""
    },
    # --- Single address with highway numbers ---
    {
        "input": "1643 Route 82",
        "output": """[
    {
        "address_type": "exact",
        "first_building_number": 1643,
        "last_building_number": 1643,
        "street": "Route 82"
    }
]"""
    },
    # --- Single range address ---
    {
        "input": "6022-6042 State Street",
        "output": """[
    {
        "address_type": "range",
        "first_building_number": 6022,
        "last_building_number": 6042,
        "street": "State Street"
    }
]"""
    },
    # --- Approximate: bare intersection joined by "and" ---
    {
        "input": "Elm Street and Park Avenue",
        "output": """[
    {
        "address_type": "approximate",
        "first_building_number": null,
        "last_building_number": null,
        "street": "Elm Street and Park Avenue"
    }
]"""
    },
    # --- Approximate: "Corner of" phrasing ---
    {
        "input": "Corner of Main Street and Oak Avenue",
        "output": """[
    {
        "address_type": "approximate",
        "first_building_number": null,
        "last_building_number": null,
        "street": "Corner of Main Street and Oak Avenue"
    }
]"""
    },
    # --- Approximate: cardinal corner abbreviation (NEC) ---
    {
        "input": "NEC of Elm St & 1st Ave",
        "output": """[
    {
        "address_type": "approximate",
        "first_building_number": null,
        "last_building_number": null,
        "street": "NEC of Elm St & 1st Ave"
    }
]"""
    },
    # --- Approximate: slash notation intersection ---
    {
        "input": "Broadway / Canal Street",
        "output": """[
    {
        "address_type": "approximate",
        "first_building_number": null,
        "last_building_number": null,
        "street": "Broadway / Canal Street"
    }
]"""
    },
    # --- Approximate: bare highway reference ---
    {
        "input": "Hwy 84",
        "output": """[
    {
        "address_type": "approximate",
        "first_building_number": null,
        "last_building_number": null,
        "street": "Hwy 84"
    }
]"""
    },
    # --- Approximate: bare street name beginning with an ordinal number ---
    {
        "input": "1st Avenue",
        "output": """[
    {
        "address_type": "approximate",
        "first_building_number": null,
        "last_building_number": null,
        "street": "1st Avenue"
    }
]"""
    },
    # --- Approximate: southeast cardinal corner with highway and road names ---
    {
        "input": "SEC IH - 35 & Country RD 170",
        "output": """[
    {
        "address_type": "approximate",
        "first_building_number": null,
        "last_building_number": null,
        "street": "SEC IH - 35 & Country RD 170"
    }
]"""
    },
    # --- Multiple exact addresses: comma-separated numbers on one street ---
    {
        "input": "27, 30, and 35 Rogerson Drive",
        "output": """[
    {
        "address_type": "exact",
        "first_building_number": 27,
        "last_building_number": 27,
        "street": "Rogerson Drive"
    },
    {
        "address_type": "exact",
        "first_building_number": 30,
        "last_building_number": 30,
        "street": "Rogerson Drive"
    },
    {
        "address_type": "exact",
        "first_building_number": 35,
        "last_building_number": 35,
        "street": "Rogerson Drive"
    }
]"""
    },
    # --- Mixed exact and range on one street ---
    {
        "input": "27, 30, and 35-42 Rogerson Drive",
        "output": """[
    {
        "address_type": "exact",
        "first_building_number": 27,
        "last_building_number": 27,
        "street": "Rogerson Drive"
    },
    {
        "address_type": "exact",
        "first_building_number": 30,
        "last_building_number": 30,
        "street": "Rogerson Drive"
    },
    {
        "address_type": "range",
        "first_building_number": 35,
        "last_building_number": 42,
        "street": "Rogerson Drive"
    }
]"""
    },
        # --- Two ranges on one street ---
    {
        "input": "2305-2313 & 2501-2621 Thonotosassa Road",
        "output": """[
    {
        "address_type": "range",
        "first_building_number": 2305,
        "last_building_number": 2313,
        "street": "Thonotosassa Road"
    },
    {
        "address_type": "range",
        "first_building_number": 2501,
        "last_building_number": 2621,
        "street": "Thonotosassa Road"
    }
]"""
    },
    # --- Two exact addresses on different streets, separated by "&" ---
    {
        "input": "27 Rogerson Drive & 123 W Franklin Street;",
        "output": """[
    {
        "address_type": "exact",
        "first_building_number": 27,
        "last_building_number": 27,
        "street": "Rogerson Drive"
    },
    {
        "address_type": "exact",
        "first_building_number": 123,
        "last_building_number": 123,
        "street": "W Franklin Street"
    }
]"""
    },
    # --- Exact + range on different streets ---
    {
        "input": "27 Rogerson Drive & 123-145 W Franklin Street",
        "output": """[
    {
        "address_type": "exact",
        "first_building_number": 27,
        "last_building_number": 27,
        "street": "Rogerson Drive"
    },
    {
        "address_type": "range",
        "first_building_number": 123,
        "last_building_number": 145,
        "street": "W Franklin Street"
    }
]"""
    },
    # --- Multiple streets separated by semicolons ---
    {
        "input": "49 Edgewater Ave; 27 & 28 Rogerson Drive; 1800-1900 E Franklin Street",
        "output": """[
    {
        "address_type": "exact",
        "first_building_number": 49,
        "last_building_number": 49,
        "street": "Edgewater Ave"
    },
    {
        "address_type": "exact",
        "first_building_number": 27,
        "last_building_number": 27,
        "street": "Rogerson Drive"
    },
    {
        "address_type": "exact",
        "first_building_number": 28,
        "last_building_number": 28,
        "street": "Rogerson Drive"
    },
    {
        "address_type": "range",
        "first_building_number": 1800,
        "last_building_number": 1900,
        "street": "E Franklin Street"
    }
]"""
    },
    # --- "a/k/a" separating multiple names for same address ---
    {
        "input": "301/303 East 75th Street a/k/a 1440/1446 2nd Avenue",
        "output": """[
    {
        "address_type": "exact",
        "first_building_number": 301,
        "last_building_number": 301,
        "street": "East 75th Street"
    },
    {
        "address_type": "exact",
        "first_building_number": 303,
        "last_building_number": 303,
        "street": "East 75th Street"
    },
    {
        "address_type": "exact",
        "first_building_number": 1440,
        "last_building_number": 1440,
        "street": "2nd Avenue"
    },
    {
        "address_type": "exact",
        "first_building_number": 1446,
        "last_building_number": 1446,
        "street": "2nd Avenue"
    }
]"""
    },
    # --- Space-separated building numbers on one street, plus a second street ---
    {
        "input": "110 121 140 South Pointe Drive & 79 Industrial Par",
        "output": """[
    {
        "address_type": "exact",
        "first_building_number": 110,
        "last_building_number": 110,
        "street": "South Pointe Drive"
    },
    {
        "address_type": "exact",
        "first_building_number": 121,
        "last_building_number": 121,
        "street": "South Pointe Drive"
    },
    {
        "address_type": "exact",
        "first_building_number": 140,
        "last_building_number": 140,
        "street": "South Pointe Drive"
    },
    {
        "address_type": "exact",
        "first_building_number": 79,
        "last_building_number": 79,
        "street": "Industrial Par"
    }
]"""
    },
    # --- Space-separated numbers on one street, plus an abbreviated range ---
    {
        "input": "110 121 140 South Pointe Drive & 32622-25 Nantasket Drive",
        "output": """[
    {
        "address_type": "exact",
        "first_building_number": 110,
        "last_building_number": 110,
        "street": "South Pointe Drive"
    },
    {
        "address_type": "exact",
        "first_building_number": 121,
        "last_building_number": 121,
        "street": "South Pointe Drive"
    },
    {
        "address_type": "exact",
        "first_building_number": 140,
        "last_building_number": 140,
        "street": "South Pointe Drive"
    },
    {
        "address_type": "range",
        "first_building_number": 32622,
        "last_building_number": 25,
        "street": "Nantasket Drive"
    }
]"""
    },
    # --- Range on a hyphenated highway name, plus an approximate address ---
    {
        "input": "81-119 US-9 South & Highway 92 at Alabama Road",
        "output": """[
    {
        "address_type": "range",
        "first_building_number": 81,
        "last_building_number": 119,
        "street": "US-9 South"
    },
    {
        "address_type": "approximate",
        "first_building_number": null,
        "last_building_number": null,
        "street": "Highway 92 at Alabama Road"
    }
]"""
    },
]


def build_prompt(address: str) -> list[dict]:
    """
    Builds a chat-style message list for use with a model's chat template.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add few-shot examples as alternating user/assistant turns
    for example in FEW_SHOT_EXAMPLES:
        messages.append({"role": "user", "content": f'Address: "{example["input"]}"'})
        messages.append({"role": "assistant", "content": example["output"]})

    # Add the actual query
    messages.append({"role": "user", "content": f'Address: "{address}"'})

    return messages