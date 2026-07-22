"""
05_fetch_discipline_and_saipe.py
==================================
Two new factors, per your list:
  1. CRDC discipline data (OSS rate, law enforcement referrals) -- no key needed
  2. Census SAIPE district-level poverty -- needs a free key (same one you'd
     use for the ACS vehicle-access pull)

CRDC ENDPOINT NAME: Urban Institute doesn't publish a single obvious slug for
this, and I couldn't verify it live this round (tool-side search/fetch
restriction, not a real dead end). This script tries the plausible candidates
in order and tells you which one actually returns data -- run it once to find
the right one, then hardcode that endpoint for future runs.

SAIPE: needs CENSUS_API_KEY env var (https://api.census.gov/data/key_signup.html)
"""

import os
import time
import requests
import pandas as pd
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
NC_FIPS = 37
BASE = "https://educationdata.urban.org/api/v1"

# Candidate CRDC discipline endpoint names, most-to-least likely per Urban
# Institute's documented naming conventions (topic-subtopic pattern).
CRDC_CANDIDATES = [
    "schools/crdc/discipline-instances",
    "schools/crdc/suspensions",
    "schools/crdc/out-of-school-suspensions",
    "schools/crdc/discipline",
    "schools/crdc/expulsions",
    "schools/crdc/referrals-or-arrests",
]

def fetch_all_pages(url: str, params: dict, max_pages: int = 30) -> pd.DataFrame:
    rows = []
    page = 1
    while url and page <= max_pages:
        resp = requests.get(url, params=params if page == 1 else None, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code} for {url}")
        data = resp.json()
        rows.extend(data.get("results", []))
        url = data.get("next")
        page += 1
        time.sleep(0.3)
    return pd.DataFrame(rows)


def find_working_crdc_endpoint(year: int = 2017):
    for candidate in CRDC_CANDIDATES:
        url = f"{BASE}/{candidate}/{year}/"
        try:
            resp = requests.get(url, params={"fips": NC_FIPS}, timeout=15)
            if resp.status_code == 200 and resp.json().get("results"):
                print(f"  WORKS: {candidate}")
                return candidate
            else:
                print(f"  no data: {candidate} (HTTP {resp.status_code})")
        except Exception as e:
            print(f"  failed: {candidate} ({e})")
    return None


def fetch_saipe_district_poverty(year: int = 2022):
    api_key = os.environ.get("CENSUS_API_KEY")
    if not api_key:
        print("  Set CENSUS_API_KEY env var to fetch SAIPE district poverty. Skipping.")
        return None
    url = f"https://api.census.gov/data/{year}/timeseries/poverty/saipe/schdist"
    params = {
        "get": "NAME,SAEPOVRT_ALL,SAEPOVALL_PT",
        "for": "school district (unified):*",
        "in": f"state:{NC_FIPS}",
        "time": year,
        "key": api_key,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    df = pd.DataFrame(data[1:], columns=data[0])
    return df


if __name__ == "__main__":
    print("Probing CRDC discipline endpoint candidates...")
    working = find_working_crdc_endpoint()
    if working:
        df = fetch_all_pages(f"{BASE}/{working}/2017/", params={"fips": NC_FIPS})
        df.to_csv(OUT_DIR / "nc_crdc_discipline.csv", index=False)
        print(f"Saved {len(df)} rows -> nc_crdc_discipline.csv (endpoint: {working})")
    else:
        print("None of the candidates worked -- check "
              "https://educationdata.urban.org/documentation/schools.html#discipline "
              "in a browser for the exact current slug and hardcode it above.")

    print("\nFetching SAIPE district poverty (needs CENSUS_API_KEY)...")
    saipe = fetch_saipe_district_poverty()
    if saipe is not None:
        saipe.to_csv(OUT_DIR / "nc_saipe_district_poverty.csv", index=False)
        print(f"Saved {len(saipe)} NC districts -> nc_saipe_district_poverty.csv")
