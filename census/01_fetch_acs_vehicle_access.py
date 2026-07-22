"""
01_fetch_acs_vehicle_access.py
================================
Pulls NC county-level American Community Survey (ACS 5-Year) data on
household vehicle access, poverty, and income from the Census Bureau API.

WHY THIS METRIC: "no vehicle available" is the household-level mirror of
the school-level transit_desert_score / stops_within_radius metrics we
already tested. It answers a different question: not "is there a bus
stop near the school" but "can this family get around without one."

GET A FREE API KEY: https://api.census.gov/data/key_signup.html
(works without a key at low volume too, but a key avoids rate-limiting)

REQUIRES: api.census.gov reachable. In this sandbox that means adding
api.census.gov to the network egress allowlist (Settings > network),
since it isn't in the sandbox's default allowed domains. If you're running
this outside the sandbox (e.g. in your agent workflow's own environment),
it should just work.
"""

import os
import requests
import pandas as pd
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
NC_STATE_FIPS = "37"

API_KEY = os.environ.get("CENSUS_API_KEY", "")  # optional but recommended

# ACS variables:
#   B08201_001E = total households (vehicle availability universe)
#   B08201_002E = households with 0 vehicles available
#   B17001_001E = population for whom poverty status is determined
#   B17001_002E = population below poverty line
#   B19013_001E = median household income
VARS = "NAME,B08201_001E,B08201_002E,B17001_001E,B17001_002E,B19013_001E"

def fetch_acs(year: int = 2022) -> pd.DataFrame:
    url = f"https://api.census.gov/data/{year}/acs/acs5"
    params = {
        "get": VARS,
        "for": "county:*",
        "in": f"state:{NC_STATE_FIPS}",
    }
    if API_KEY:
        params["key"] = API_KEY

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    rows = resp.json()
    df = pd.DataFrame(rows[1:], columns=rows[0])

    numeric_cols = ["B08201_001E", "B08201_002E", "B17001_001E", "B17001_002E", "B19013_001E"]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["county_name"] = df["NAME"].str.replace(" County, North Carolina", "", regex=False).str.strip()
    df["fips"] = df["state"] + df["county"]  # 5-digit FIPS, matches GeoJSON GEO_ID tail

    df["pct_no_vehicle"] = (df["B08201_002E"] / df["B08201_001E"] * 100).round(2)
    df["pct_poverty"] = (df["B17001_002E"] / df["B17001_001E"] * 100).round(2)
    df["median_household_income"] = df["B19013_001E"]

    out = df[["county_name", "fips", "pct_no_vehicle", "pct_poverty", "median_household_income"]].copy()
    out["county_norm"] = out["county_name"].str.strip().str.lower()
    return out


if __name__ == "__main__":
    acs = fetch_acs()
    acs.to_csv(OUT_DIR / "acs_nc_vehicle_access.csv", index=False)
    print(f"Saved {len(acs)} NC counties -> acs_nc_vehicle_access.csv")
    print(acs.sort_values("pct_no_vehicle", ascending=False).head(10).to_string(index=False))
