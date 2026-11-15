"""Step 7: bands 45-64, 65-74 and 75 and over by sex for K70, K74, K74.6 and K70+K74, nine countries.

Input : 10_derived/age_specific_rates.csv (step 6)
Output: 10_derived/age_band_detail.csv          iso, sex, band, code_group, year, deaths, population, crude_rate, rate
        10_derived/age_band_detail_summary.csv  rates in 2010, 2019 and 2022 with percent change

Run from the project root:  python3 20_analysis/age_band_detail.py
"""
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
DER = ROOT / "10_derived"
COUNTRIES = ["DE", "FR", "IT", "ES", "UK", "PL", "CZ", "AT", "NL"]
BANDS = ["45-64", "65-74", "75plus"]
GROUPS = ["K70", "K74", "K746", "K70_K74"]
REF_YEARS = [2010, 2019, 2022]
MIN_DEATHS = 20


def main():
    d = pd.read_csv(DER / "age_specific_rates.csv")
    d = d[d.iso.isin(COUNTRIES) & d.band.isin(BANDS) & d.code_group.isin(GROUPS) & d.sex.isin(["M", "F", "T"])].copy()
    d = d.rename(columns={"sdr_in_band": "rate"})
    d["unstable"] = d.deaths < MIN_DEATHS
    d = d.sort_values(["code_group", "iso", "sex", "band", "year"])
    d[["iso", "sex", "band", "code_group", "year", "deaths", "population", "crude_rate", "rate", "unstable",
       "top_age_group"]].to_csv(DER / "age_band_detail.csv", index=False, float_format="%.3f")
    print(f"wrote age_band_detail.csv ({len(d)} rows)")

    w = d[d.year.isin(REF_YEARS)].pivot_table(index=["code_group", "iso", "sex", "band"], columns="year",
                                              values="rate").reset_index()
    for y in REF_YEARS:
        if y not in w.columns:
            w[y] = float("nan")
    w["pct_2010_2019"] = 100 * (w[2019] / w[2010] - 1)
    w["pct_2010_2022"] = 100 * (w[2022] / w[2010] - 1)
    w.columns = [str(c) for c in w.columns]
    w.to_csv(DER / "age_band_detail_summary.csv", index=False, float_format="%.2f")
    print("wrote age_band_detail_summary.csv")


if __name__ == "__main__":
    main()
