"""
04_fetch_urban_institute.py
=============================
Pulls NC school-level data from the Urban Institute Education Data Portal
(free, no API key required): CCD free/reduced lunch + teacher FTE, and
CRDC teacher experience/turnover + AP participation.

Docs: https://educationdata.urban.org/documentation/
No key needed. Rate limit is generous but be a good citizen -- this script
sleeps briefly between paginated calls.

NOTE: use requests with a `params` dict (not a hand-built query string) --
that's what makes the state filter actually apply server-side.
"""

import requests
import pandas as pd
import time
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
NC_FIPS = 37
BASE = "https://educationdata.urban.org/api/v1"

def fetch_all_pages(url: str, params: dict, max_pages: int = 50) -> pd.DataFrame:
    """Follow the `next` cursor until exhausted or max_pages hit."""
    rows = []
    page = 1
    while url and page <= max_pages:
        resp = requests.get(url, params=params if page == 1 else None, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        rows.extend(data.get("results", []))
        url = data.get("next")
        page += 1
        time.sleep(0.3)
    return pd.DataFrame(rows)


def fetch_ccd_directory(year: int = 2022) -> pd.DataFrame:
    """FRL counts, teacher FTE, Title I status, enrollment -- NC only."""
    url = f"{BASE}/schools/ccd/directory/{year}/"
    df = fetch_all_pages(url, params={"fips": NC_FIPS})
    df["frl_rate"] = df["free_or_reduced_price_lunch"] / df["enrollment"]
    df["student_teacher_ratio"] = df["enrollment"] / df["teachers_fte"]
    return df


def fetch_crdc_teacher_experience(year: int = 2017) -> pd.DataFrame:
    """First-year-teacher share, teacher experience -- CRDC is biennial, sparser years."""
    url = f"{BASE}/schools/crdc/teachers-staffing/{year}/"
    df = fetch_all_pages(url, params={"fips": NC_FIPS})
    return df


def fetch_crdc_ap(year: int = 2017) -> pd.DataFrame:
    """AP enrollment / exam pass counts -- high schools only, sparse for younger grades."""
    url = f"{BASE}/schools/crdc/ap-exams/{year}/"
    df = fetch_all_pages(url, params={"fips": NC_FIPS})
    return df


if __name__ == "__main__":
    print("Fetching CCD directory (FRL, teacher FTE, Title I)...")
    ccd = fetch_ccd_directory()
    ccd.to_csv(OUT_DIR / "nc_ccd_directory.csv", index=False)
    print(f"  {len(ccd)} NC schools saved -> nc_ccd_directory.csv")

    print("Fetching CRDC teacher staffing (experience/turnover)...")
    try:
        crdc_staff = fetch_crdc_teacher_experience()
        crdc_staff.to_csv(OUT_DIR / "nc_crdc_teacher_staffing.csv", index=False)
        print(f"  {len(crdc_staff)} rows saved -> nc_crdc_teacher_staffing.csv")
    except Exception as e:
        print(f"  Endpoint/year may need adjusting -- check the docs. Error: {e}")

    print("Fetching CRDC AP exam data...")
    try:
        crdc_ap = fetch_crdc_ap()
        crdc_ap.to_csv(OUT_DIR / "nc_crdc_ap.csv", index=False)
        print(f"  {len(crdc_ap)} rows saved -> nc_crdc_ap.csv")
    except Exception as e:
        print(f"  Endpoint/year may need adjusting -- check the docs. Error: {e}")

    print("\nNext step: match ncessch / school_name+county to your existing")
    print("matched.csv / transit_edu_poverty_vehicle.csv the same way you've")
    print("been joining ACS data, then correlate frl_rate, student_teacher_ratio,")
    print("and teacher experience against ach_score and edu_rate.")
