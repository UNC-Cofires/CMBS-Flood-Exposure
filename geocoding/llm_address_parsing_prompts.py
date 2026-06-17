# This scripts contains LLM prompts for CMBS loan address parsing

SYSTEM_PROMPT = """\
You are an address parsing assistant. Analyze address strings and determine \
whether they refer to multiple distinct building locations.

An address string refers to multiple locations if it contains:
- Hyphenated address ranges (e.g., "150-154 Main St" means buildings 150, 151, 152, 153, 154)
- Multiple street addresses separated by commas, "&", ";", "and", or other conjunctions,
  where each part contains a building number

An address string refers to a SINGLE location if it is:
- A single unambiguous address (e.g., "742 Evergreen Terrace")
- A street intersection, which may be indicated by any of the following formats:
    - Cardinal corner abbreviations: NEC, NWC, SEC, or SWC followed by two street names
      (e.g., "NEC of Coldwater Rd & Noble Drive")
    - "Corner of" phrasing (e.g., "Corner of Main Street and Oak Avenue")
    - Two street names with no building numbers joined by "and"
      (e.g., "Elm Street and Park Avenue")
    - Two street names separated by "/" (e.g., "Broadway / Canal Street")
    - Two street names separated by "@" (e.g., "Elm St @ Park Ave")

Rules:
1. For hyphenated ranges where the second number is strictly greater than the
   first (e.g., "10-14", "150-154"), expand by listing every integer from the
   first number to the second number inclusive.
2. For hyphenated ranges where the second number is strictly less than the first
   number (e.g., "32622-25"), the range is ambiguous and cannot be reliably
   expanded. Set range_ambiguous to true and return an empty addresses list.
3. Preserve the full street name, direction, and type for each expanded address.
4. If expanding all ranges in the string would result in more than 100 total
   addresses, do NOT expand them. Instead, set range_too_large to true and
   return an empty addresses list.
5. Respond ONLY with a valid JSON object — no explanation, no extra text.

JSON schema:
{
  "multiple_locations": <boolean>,
  "range_too_large": <boolean>,
  "range_ambiguous": <boolean>,
  "addresses": [<list of individual address strings>]
}
If multiple_locations is false, range_too_large, range_ambiguous, and addresses
should be set to false, false, and [] respectively.
If range_too_large or range_ambiguous is true, addresses should be an empty list.
"""

FEW_SHOT_EXAMPLES = [
    # --- Multi-location: hyphenated ranges across multiple streets ---
    {
        "input": "150-154 South Whitney Street, 149-151 Sisson Avenue, 28-30 Kibbe Street and 63-65 Evergreen Avenue",
        "output": """{
  "multiple_locations": true,
  "range_too_large": false,
  "range_ambiguous": false,
  "addresses": [
    "150 South Whitney Street",
    "151 South Whitney Street",
    "152 South Whitney Street",
    "153 South Whitney Street",
    "154 South Whitney Street",
    "149 Sisson Avenue",
    "150 Sisson Avenue",
    "151 Sisson Avenue",
    "28 Kibbe Street",
    "29 Kibbe Street",
    "30 Kibbe Street",
    "63 Evergreen Avenue",
    "64 Evergreen Avenue",
    "65 Evergreen Avenue"
  ]
}"""
    },
    # --- Single location: plain address ---
    {
        "input": "742 Evergreen Terrace",
        "output": """{
  "multiple_locations": false,
  "range_too_large": false,
  "range_ambiguous": false,
  "addresses": []
}"""
    },
    # --- Multi-location: two addresses joined by "and" ---
    {
        "input": "10 and 12 Oak Street",
        "output": """{
  "multiple_locations": true,
  "range_too_large": false,
  "range_ambiguous": false,
  "addresses": [
    "10 Oak Street",
    "12 Oak Street"
  ]
}"""
    },
    # --- Single location: named corner with cardinal abbreviation (NEC) ---
    # "NEC" (Northeast Corner) indicates an intersection, not multiple buildings.
    # The "&" here joins two street names, not two separate addresses.
    {
        "input": "NEC of Coldwater Rd & Noble Drive",
        "output": """{
  "multiple_locations": false,
  "range_too_large": false,
  "range_ambiguous": false,
  "addresses": []
}"""
    },
    # --- Single location: other cardinal corner abbreviation (SWC) ---
    {
        "input": "SWC of Elm St & 1st Ave",
        "output": """{
  "multiple_locations": false,
  "range_too_large": false,
  "range_ambiguous": false,
  "addresses": []
}"""
    },
    # --- Single location: corner described with "Corner of" phrasing ---
    {
        "input": "Corner of Main Street and Oak Avenue",
        "output": """{
  "multiple_locations": false,
  "range_too_large": false,
  "range_ambiguous": false,
  "addresses": []
}"""
    },
    # --- Single location: bare intersection with "and" ---
    # Two street names with no building numbers — this is an intersection.
    {
        "input": "Elm Street and Park Avenue",
        "output": """{
  "multiple_locations": false,
  "range_too_large": false,
  "range_ambiguous": false,
  "addresses": []
}"""
    },
    # --- Single location: slash notation ---
    {
        "input": "Broadway / Canal Street",
        "output": """{
  "multiple_locations": false,
  "range_too_large": false,
  "range_ambiguous": false,
  "addresses": []
}"""
    },
    # --- Single location: at (@) notation ---
    {
        "input": "Elm St @ Park Ave",
        "output": """{
  "multiple_locations": false,
  "range_too_large": false,
  "range_ambiguous": false,
  "addresses": []
}"""
    },
    # --- Multi-location: ambiguous range (second number less than first) ---
    # 25 < 32622, so the range cannot be reliably expanded.
    # range_ambiguous is set to true and addresses is left empty.
    {
        "input": "32622-25 Nantasket Drive",
        "output": """{
  "multiple_locations": true,
  "range_too_large": false,
  "range_ambiguous": true,
  "addresses": []
}"""
    },
    # --- Multi-location: "&" separating two addressed properties with ambiguous range ---
    # Both sides have building numbers, so "&" is an address separator.
    # However, "32622-25" is ambiguous (25 < 32622), so the range cannot be expanded.
    {
        "input": "6600 Beachview Drive & 32622-25 Nantasket Drive",
        "output": """{
  "multiple_locations": true,
  "range_too_large": false,
  "range_ambiguous": true,
  "addresses": []
}"""
    },
    # --- Multi-location: range that exceeds the 100-address limit ---
    # 1 to 250 would produce 250 addresses, exceeding the limit of 100.
    # range_too_large is set to true and addresses is left empty.
    {
        "input": "1-250 Main Street",
        "output": """{
  "multiple_locations": true,
  "range_too_large": true,
  "range_ambiguous": false,
  "addresses": []
}"""
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