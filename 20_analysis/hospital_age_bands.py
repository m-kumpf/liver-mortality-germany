"""Step 10: hospital stays by four-character main diagnosis (liver codes), East and West Germany, by sex and age band.

Input : 04_destatis/gbe_full/hospital4/gbe703_by_age_long.csv  (download_gbe_full.py --table hospital4)
Output: 10_derived/hospital_age_bands.csv          icd, region, sex, band, year, cases, rate
        10_derived/hospital_age_bands_summary.csv  rates in 2000, 2010, 2019 and 2023 with percent change

Band rates as in step 9 (ESP2013-weighted mean of the crude five-year rates). Stays are counted per admission.

Run from the project root:  python3 20_analysis/hospital_age_bands.py
"""
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from east_west_age_bands import AGE, REG, band_rates

ROOT = pathlib.Path(__file__).resolve().parents[1]
IN = ROOT / "04_destatis" / "gbe_full" / "hospital4" / "gbe703_by_age_long.csv"
DER = ROOT / "10_derived"
ICD = ["K70-K77", "K70", "K70.0", "K70.1", "K70.3", "K70.4", "K72", "K74", "K74.6", "K75", "K76", "K76.0", "K76.6", "K76.7"]


def main():
    d = pd.read_csv(IN)
    d = d[d.icd.isin(ICD) & d.age.isin(AGE) & d.region.isin(REG)].copy()
    d["age5"] = d.age.map(AGE)
    d["region"] = d.region.map(REG)
    d["value"] = d.value.fillna(0)
    idx = ["icd", "region", "sex", "year", "age5"]
    cases = d[d.measure == "Fälle"].pivot_table(index=idx, values="value", aggfunc="first")
    rate = d[d.measure == "Fälle je 100.000 Einwohner"].pivot_table(index=idx, values="value", aggfunc="first")
    x = cases.rename(columns={"value": "cases"}).join(rate.rename(columns={"value": "crude"}), how="outer").fillna(0).reset_index()
    r = band_rates(x, "cases").sort_values(["icd", "region", "sex", "band", "year"])
    r.to_csv(DER / "hospital_age_bands.csv", index=False, float_format="%.3f")
    print(f"wrote hospital_age_bands.csv ({len(r)} rows)")

    ref = [2000, 2010, 2019, 2023]
    w = r[r.year.isin(ref)].pivot_table(index=["icd", "region", "sex", "band"], columns="year", values="rate").reset_index()
    w["pct_2010_2019"] = 100 * (w[2019] / w[2010] - 1)
    w["pct_2010_2023"] = 100 * (w[2023] / w[2010] - 1)
    w.columns = [str(c) for c in w.columns]
    w.to_csv(DER / "hospital_age_bands_summary.csv", index=False, float_format="%.2f")
    print("wrote hospital_age_bands_summary.csv")


if __name__ == "__main__":
    main()
