"""Step 9: liver disease mortality (K70-K77) in East and West Germany by sex and age band, 1998-2024.

Input : 04_destatis/gbe_full/deaths/gbe6_by_age_long.csv  (download_gbe_full.py --table deaths)
Output: 10_derived/east_west_age_bands.csv          icd, region, sex, band, year, deaths, rate
        10_derived/east_west_age_bands_summary.csv  rates in 2000, 2010, 2019, 2022 and 2024 with percent change

Band rate = ESP2013-weighted mean of the crude five-year rates within the band (90 and over carries the ESP weight
of 90-94 and 95+), the same quantity as sdr_in_band in step 6. Cells suppressed by the Federal Statistical Office
(fewer than three deaths) are treated as zero.

Run from the project root:  python3 20_analysis/east_west_age_bands.py
"""
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from whomdb_common import ESP2013

ROOT = pathlib.Path(__file__).resolve().parents[1]
IN = ROOT / "04_destatis" / "gbe_full" / "deaths" / "gbe6_by_age_long.csv"
DER = ROOT / "10_derived"

AGE = {"45 bis unter 50 Jahre": "45-49", "50 bis unter 55 Jahre": "50-54", "55 bis unter 60 Jahre": "55-59",
       "60 bis unter 65 Jahre": "60-64", "65 bis unter 70 Jahre": "65-69", "70 bis unter 75 Jahre": "70-74",
       "75 bis unter 80 Jahre": "75-79", "80 bis unter 85 Jahre": "80-84", "85 bis unter 90 Jahre": "85-89",
       "90 Jahre und älter": "90+"}
W = dict(ESP2013)
W["90+"] = ESP2013["90-94"] + ESP2013["95+"]
BANDS = {"45-64": ["45-49", "50-54", "55-59", "60-64"], "65-74": ["65-69", "70-74"],
         "75plus": ["75-79", "80-84", "85-89", "90+"]}
REG = {"Deutschland": "DE", "Früheres Bundesgebiet und Berlin-Ost": "West", "Neue Länder ohne Berlin-Ost": "East"}
ICD = ["K70-K77", "C15-C26", "B15-B19", "F10-F19", "K00-K93"]


def band_rates(x, count_col):
    """ESP-weighted band rate and summed counts from a table with columns icd, region, sex, year, age5, crude, <count_col>."""
    out = []
    for (icd, reg, sex, year), g in x.groupby(["icd", "region", "sex", "year"]):
        g = g.set_index("age5")
        for band, ages in BANDS.items():
            if not all(a in g.index for a in ages):
                continue
            ws = sum(W[a] for a in ages)
            out.append({"icd": icd, "region": reg, "sex": sex, "band": band, "year": year,
                        count_col: g.loc[ages, count_col].sum(),
                        "rate": sum(g.loc[a, "crude"] * W[a] for a in ages) / ws})
    return pd.DataFrame(out)


def main():
    d = pd.read_csv(IN)
    d = d[d.icd.isin(ICD) & d.age.isin(AGE) & d.region.isin(REG)].copy()
    d["age5"] = d.age.map(AGE)
    d["region"] = d.region.map(REG)
    d["value"] = d.value.fillna(0)
    d["measure"] = d.measure.str.replace(r"\s+", " ", regex=True)
    idx = ["icd", "region", "sex", "year", "age5"]
    deaths = d[d.measure == "Sterbefälle"].pivot_table(index=idx, values="value", aggfunc="first")
    rate = d[d.measure == "Sterbefälle je 100.000 Einwohner"].pivot_table(index=idx, values="value", aggfunc="first")
    x = deaths.rename(columns={"value": "deaths"}).join(rate.rename(columns={"value": "crude"}), how="outer").fillna(0).reset_index()
    r = band_rates(x, "deaths").sort_values(["icd", "region", "sex", "band", "year"])
    r.to_csv(DER / "east_west_age_bands.csv", index=False, float_format="%.3f")
    print(f"wrote east_west_age_bands.csv ({len(r)} rows)")

    ref = [2000, 2010, 2019, 2022, 2024]
    w = r[r.year.isin(ref)].pivot_table(index=["icd", "region", "sex", "band"], columns="year", values="rate").reset_index()
    w["pct_2010_2019"] = 100 * (w[2019] / w[2010] - 1)
    w["pct_2010_2024"] = 100 * (w[2024] / w[2010] - 1)
    w.columns = [str(c) for c in w.columns]
    w.to_csv(DER / "east_west_age_bands_summary.csv", index=False, float_format="%.2f")
    print("wrote east_west_age_bands_summary.csv")


if __name__ == "__main__":
    main()
