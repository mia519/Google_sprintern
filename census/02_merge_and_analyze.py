"""
02_merge_and_analyze.py
========================
Merges county-level ACS "no vehicle access" / poverty / income data onto
the existing school-level transit_education_matched.csv (which has
edu_rate = chronic absenteeism rate) and runs the SAME robustness
framework we already validated for the transit metrics:

  1. Bivariate correlation (pct_no_vehicle vs edu_rate)
  2. Poverty-controlled OLS, clustered SE by county
  3. County fixed-effects OLS (within-county comparison)
  4. Variance partitioning vs Title I alone

This lets you directly compare "household vehicle access" against
"school transit-stop proximity" on equal statistical footing before
either goes into the app as a headline factor.
"""

import pandas as pd
import numpy as np
from scipy import stats
import statsmodels.api as sm
import statsmodels.formula.api as smf
from pathlib import Path
from rapidfuzz import process, fuzz
import re

BASE = Path(__file__).resolve().parent
PROJECT_ROOT = BASE.parent

acs = pd.read_csv(BASE / "acs_nc_vehicle_access.csv")
poverty_path = BASE / "transit_edu_with_poverty.csv"
if poverty_path.exists():
    edu = pd.read_csv(poverty_path)
else:
    edu = pd.read_csv(PROJECT_ROOT / "transit_education_matched.csv")
    spg = pd.read_csv(PROJECT_ROOT / "2025spg.csv", low_memory=False)
    spg = spg[(spg["subgroup"] == "ALL") & (spg["agency_level"] == "SCH")].copy()

    def normalize_name(value):
        value = re.sub(r"[^a-z0-9 ]", " ", str(value).lower())
        replacements = {
            r"\belem\b": "elementary", r"\bele\b": "elementary",
            r"\bmid\b": "middle", r"\bms\b": "middle", r"\bhs\b": "high",
            r"\bschl\b": "school", r"\bsch\b": "school",
            r"\bearly coll\b": "early college", r"\bec\b": "early college",
            r"\bacad\b": "academy",
        }
        for pattern, replacement in replacements.items():
            value = re.sub(pattern, replacement, value)
        value = re.sub(r"\bschool\b", "", value)
        return re.sub(r"\s+", " ", value).strip()

    spg["name_norm_join"] = spg["name"].map(normalize_name)
    spg["county_norm_join"] = spg["county"].astype(str).str.strip().str.lower()
    title_i_values = []
    match_scores = []
    for row in edu.itertuples(index=False):
        county = str(row.edu_county).strip().lower()
        name = normalize_name(row.edu_school_name)
        candidates = spg[spg["county_norm_join"] == county]
        result = process.extractOne(name, candidates["name_norm_join"].tolist(), scorer=fuzz.token_sort_ratio)
        if result and result[1] >= 85:
            title_i_values.append(candidates.iloc[result[2]]["title_i"])
            match_scores.append(result[1])
        else:
            title_i_values.append(np.nan)
            match_scores.append(result[1] if result else np.nan)

    edu["title_i"] = title_i_values
    edu["title_i_match_score"] = match_scores
    matched_mask = pd.Series(match_scores, index=edu.index).ge(85)
    edu["is_title_i"] = np.where(matched_mask, edu["title_i"].eq("Y").astype(int), np.nan)
    edu.to_csv(poverty_path, index=False)
    print(f"Built {poverty_path.name}: SPG matched for {matched_mask.sum()} / {len(edu)} schools")

edu["county_norm3"] = edu["edu_county"].astype(str).str.strip().str.lower()
merged = edu.merge(acs, left_on="county_norm3", right_on="county_norm", how="inner", suffixes=("", "_acs"))
print(f"Merged n = {len(merged)} / {len(edu)} school rows matched to a county ACS record "
      f"({len(merged)/len(edu)*100:.1f}%)")

merged.to_csv(BASE / "transit_edu_poverty_vehicle.csv", index=False)

print("\n=== 1. BIVARIATE: pct_no_vehicle vs edu_rate ===")
d = merged[["pct_no_vehicle", "edu_rate"]].dropna()
r, p = stats.pearsonr(d["pct_no_vehicle"], d["edu_rate"])
rho, ps = stats.spearmanr(d["pct_no_vehicle"], d["edu_rate"])
print(f"n={len(d)}  pearson r={r:+.4f} p={p:.4g}   spearman rho={rho:+.4f} p={ps:.4g}")

print("\n=== 2. POVERTY-CONTROLLED (Title I), clustered SE by county ===")
d2 = merged[["pct_no_vehicle", "is_title_i", "edu_rate", "county"]].dropna()
m2 = smf.ols("edu_rate ~ pct_no_vehicle + is_title_i", data=d2).fit(
    cov_type="cluster", cov_kwds={"groups": d2["county"]}
)
print(m2.summary().tables[1])

print("\n=== 3. COUNTY FIXED EFFECTS (within-county) ===")
county_counts = d2["county"].value_counts()
valid = county_counts[county_counts >= 5].index
d3 = d2[d2["county"].isin(valid)]
m3 = smf.ols("edu_rate ~ pct_no_vehicle + is_title_i + C(county)", data=d3).fit()
b = m3.params.get("pct_no_vehicle", np.nan)
p3 = m3.pvalues.get("pct_no_vehicle", np.nan)
print(f"n={len(d3)}, counties={d3['county'].nunique()}, coef={b:+.6f} p={p3:.4g}")

print("\n=== 4. VARIANCE PARTITIONING vs Title I alone ===")
Xa = sm.add_constant(d2[["is_title_i"]])
ma = sm.OLS(d2["edu_rate"], Xa).fit()
Xb = sm.add_constant(d2[["is_title_i", "pct_no_vehicle"]])
mb = sm.OLS(d2["edu_rate"], Xb).fit()
print(f"R2(poverty only)={ma.rsquared:.4f}  R2(+vehicle access)={mb.rsquared:.4f}  "
      f"unique={mb.rsquared-ma.rsquared:+.4f}")

print("\n=== 5. HEAD-TO-HEAD vs stops_within_radius (already validated) ===")
d5 = merged[["pct_no_vehicle", "stops_within_radius", "is_title_i", "edu_rate", "county"]].dropna()
m5 = smf.ols("edu_rate ~ pct_no_vehicle + stops_within_radius + is_title_i", data=d5).fit(
    cov_type="cluster", cov_kwds={"groups": d5["county"]}
)
print(m5.summary().tables[1])
