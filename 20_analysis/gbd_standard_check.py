"""Step 15: standard-population check for the GBD-to-registry ratio.

GBD publishes age-standardised rates on the GBD world population age standard, the registry rates in sdr_compare.csv
are standardised to the WHO world standard. GBD's own age-specific cirrhosis rates are re-standardised here to the WHO
world standard, with the same top-group merging as the registry row of the same country and year, and the ratio is
recomputed with both sides on one standard.

Inputs : 01_gbd2023/gbd2023_cirrhosis_aetiology_deaths_by_age_9countries_2010_2019_2023.csv
         10_derived/sdr_compare.csv (step 3)
Output : 10_derived/gbd_standard_check.csv

Run from the project root:  python3 20_analysis/gbd_standard_check.py
"""
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from whomdb_common import WHO2000

ROOT = pathlib.Path(__file__).resolve().parents[1]
GBD_IN = ROOT / "01_gbd2023" / "gbd2023_cirrhosis_aetiology_deaths_by_age_9countries_2010_2019_2023.csv"
SDR_IN = ROOT / "10_derived" / "sdr_compare.csv"
OUT = ROOT / "10_derived" / "gbd_standard_check.csv"
ISO = {"Germany": "DE", "France": "FR", "Italy": "IT", "Spain": "ES", "Netherlands": "NL", "Austria": "AT",
       "United Kingdom": "UK", "Poland": "PL", "Czechia": "CZ"}
ORDER = list(WHO2000)


def norm_age(a):
    a = a.replace(" to ", "-").replace(" plus", "+")
    if a in ("<1 year", "0-6 days", "7-27 days", "28-364 days", "12-23 months", "2-4", "1-4", "0"):
        return "0-4"
    return a


def restandardise(agg, top):
    """Age-standardised rate per 100 000 on the WHO world standard, groups from `top` upwards pooled."""
    t = ORDER.index(top)
    r = sum(agg.loc[a, "rate"] * WHO2000[a] for a in ORDER[:t])
    above = ORDER[t:]
    pooled = agg.loc[above, "count"].sum() / agg.loc[above, "pop"].sum() * 1e5
    r += pooled * sum(WHO2000[a] for a in above)
    return r / sum(WHO2000.values())


def main():
    g = pd.read_csv(GBD_IN)
    g = g[g.cause_name == "Cirrhosis and other chronic liver diseases"].copy()
    g["age"] = g.age_group.map(norm_age)
    g["pop"] = g.count_combined / g.rate_combined * 1e5
    sc = pd.read_csv(SDR_IN)
    rows = []
    for (loc, yr), d in g.groupby(["location_name", "year"]):
        agg = d.groupby("age").agg(count=("count_combined", "sum"), pop=("pop", "sum"))
        agg["rate"] = agg["count"] / agg["pop"] * 1e5
        assert set(ORDER) <= set(agg.index), (loc, yr, sorted(agg.index))
        s = sc[(sc.iso == ISO[loc]) & (sc.year == yr) & (sc.sex == "T")]
        if s.empty or pd.isna(s.ratio_gbd_over_registry.iloc[0]):
            continue
        s = s.iloc[0]
        gbd_who = restandardise(agg, s.top_age_group)
        rows.append(dict(iso=ISO[loc], year=yr, top_age_group=s.top_age_group,
                         gbd_asr_published=round(s.gbd_asr, 3), gbd_asr_who_std=round(gbd_who, 3),
                         registry_K70_K76_who_std=round(s.who_sdr_K70_K76_who2000, 3),
                         ratio_reported=round(s.ratio_gbd_over_registry, 3),
                         ratio_same_std=round(gbd_who / s.who_sdr_K70_K76_who2000, 3)))
    out = pd.DataFrame(rows).sort_values(["year", "iso"])
    out["ratio_diff"] = (out.ratio_same_std - out.ratio_reported).round(3)
    out.to_csv(OUT, index=False)
    print(f"wrote gbd_standard_check.csv ({len(out)} rows)")
    print(out.groupby("iso").ratio_diff.apply(lambda x: x.abs().max()).round(3).to_string())


if __name__ == "__main__":
    main()
