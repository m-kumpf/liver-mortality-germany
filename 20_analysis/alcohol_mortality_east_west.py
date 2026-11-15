"""Step 20: alcohol-specific mortality (F10 and K70) in eastern and western Germany by sex and age band, 1998-2024.

The three-character codes are published by region in the GBE-Bund TOP-100 table (step 5) as age-standardised rates
(ESP2013) for all ages and within the bands under 65 and 65 and over. F10 for women aged 65 and over is not among the
100 most frequent causes in most years; for these cells the deaths are recovered as all ages minus under 65 and the
within-band rate is estimated by distributing them over the five-year age groups in proportion to the F10-F19 block
of the full table (download_gbe_full.py --table deaths). The same estimate is computed for every cell in which the
rate is published, to check the allocation.

Inputs : 04_destatis/gbe_bund/gbe517_top100_esp2013_long.csv
         04_destatis/gbe_full/deaths/gbe6_by_age_long.csv
Outputs: 10_derived/alcohol_mortality_east_west.csv        region, sex, age, year, icd (F10, K70, F10+K70), deaths, rate, rate_source
         10_derived/alcohol_mortality_allocation_check.csv  published against estimated 65+ rates where both exist

Run from the project root:  python3 20_analysis/alcohol_mortality_east_west.py
"""
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from whomdb_common import ESP2013

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOP = ROOT / "04_destatis" / "gbe_bund" / "gbe517_top100_esp2013_long.csv"
FULL = ROOT / "04_destatis" / "gbe_full" / "deaths" / "gbe6_by_age_long.csv"
DER = ROOT / "10_derived"

REG = {"Deutschland": "DE", "Früheres Bundesgebiet und Berlin-Ost": "West", "Neue Länder ohne Berlin-Ost": "East"}
AGE5 = {"Unter 1 Jahr": "0", "1 Jahr bis unter 5 Jahre": "1-4", "5 bis unter 10 Jahre": "5-9", "10 bis unter 15 Jahre": "10-14",
        "15 bis unter 20 Jahre": "15-19", "20 bis unter 25 Jahre": "20-24", "25 bis unter 30 Jahre": "25-29",
        "30 bis unter 35 Jahre": "30-34", "35 bis unter 40 Jahre": "35-39", "40 bis unter 45 Jahre": "40-44",
        "45 bis unter 50 Jahre": "45-49", "50 bis unter 55 Jahre": "50-54", "55 bis unter 60 Jahre": "55-59",
        "60 bis unter 65 Jahre": "60-64", "65 bis unter 70 Jahre": "65-69", "70 bis unter 75 Jahre": "70-74",
        "75 bis unter 80 Jahre": "75-79", "80 bis unter 85 Jahre": "80-84", "85 bis unter 90 Jahre": "85-89",
        "90 Jahre und älter": "90+"}
W = dict(ESP2013)
W["90+"] = ESP2013["90-94"] + ESP2013["95+"]
BAND = {"u65": [a for a in AGE5.values() if a not in ("65-69", "70-74", "75-79", "80-84", "85-89", "90+")],
        "65plus": ["65-69", "70-74", "75-79", "80-84", "85-89", "90+"]}
BLOCK = {"F10": "F10-F19", "K70": "K70-K77"}
POP_BLOCKS = ["C00-D48", "I00-I99", "C00-C97"]  # population by age group = deaths / crude rate, median over three large blocks


def load_full():
    d = pd.read_csv(FULL, usecols=["year", "region", "sex", "icd", "age", "measure", "value"])
    d = d[d.region.isin(REG) & d.age.isin(AGE5) & d.icd.isin(list(BLOCK.values()) + POP_BLOCKS)].copy()
    d["region"] = d.region.map(REG)
    d["age5"] = d.age.map(AGE5)
    d["measure"] = d.measure.str.replace(r"\s+", " ", regex=True)
    idx = ["year", "region", "sex", "age5"]
    deaths = d[d.measure == "Sterbefälle"].pivot_table(index=idx, columns="icd", values="value", aggfunc="first")
    crude = d[d.measure == "Sterbefälle je 100.000 Einwohner"].pivot_table(index=idx, columns="icd", values="value", aggfunc="first")
    pop = pd.concat([deaths[b] / crude[b] * 1e5 for b in POP_BLOCKS], axis=1).median(axis=1)
    return deaths.fillna(0), pop


def estimate_band(deaths_band, block, pop, band):
    """ESP-standardised rate within the band for deaths distributed over the five-year groups like the block."""
    ages = BAND[band]
    b = block.reindex(ages).fillna(0)
    if b.sum() == 0:
        return np.nan
    share = b / b.sum()
    rate_a = deaths_band * share / pop.reindex(ages) * 1e5
    ws = sum(W[a] for a in ages)
    return float(sum(rate_a[a] * W[a] for a in ages) / ws)


def main():
    t = pd.read_csv(TOP)
    t = t[t.region.isin(REG) & t.icd3.isin(BLOCK)].assign(region=lambda x: x.region.map(REG))
    t = t[["year", "region", "sex", "age", "icd3", "deaths", "sdr_esp2013"]].rename(columns={"icd3": "icd", "sdr_esp2013": "rate"})
    idx = pd.MultiIndex.from_product([sorted(t.year.unique()), list(REG.values()), ["M", "F", "T"], ["alle", "u65", "65plus"],
                                      list(BLOCK)], names=["year", "region", "sex", "age", "icd"])
    t = t.set_index(["year", "region", "sex", "age", "icd"]).reindex(idx).reset_index()
    t["rate_source"] = np.where(t.rate.notna(), "GBE TOP-100 (ESP2013)", "")
    blk, pop = load_full()

    check = []
    for i, r in t[t.age == "65plus"].iterrows():
        same = (t.year == r.year) & (t.region == r.region) & (t.sex == r.sex) & (t.icd == r.icd)
        alle = t[same & (t.age == "alle")].deaths
        u65 = t[same & (t.age == "u65")].deaths
        if alle.empty or u65.empty or pd.isna(alle.iloc[0]) or pd.isna(u65.iloc[0]):
            continue
        d65 = float(alle.iloc[0] - u65.iloc[0])
        est = estimate_band(d65, blk.loc[(r.year, r.region, r.sex)][BLOCK[r.icd]], pop.loc[(r.year, r.region, r.sex)], "65plus")
        if pd.notna(r.rate):
            check.append(dict(year=r.year, region=r.region, sex=r.sex, icd=r.icd, rate_published=r.rate, rate_estimated=est,
                              deaths_published=r.deaths, deaths_recovered=d65))
        else:
            t.loc[i, ["deaths", "rate", "rate_source"]] = [d65, est, "estimated: (all ages − under 65) deaths allocated like the ICD block"]
    chk = pd.DataFrame(check)
    chk["rel_diff"] = chk.rate_estimated / chk.rate_published - 1
    chk.to_csv(DER / "alcohol_mortality_allocation_check.csv", index=False, float_format="%.4f")
    print(f"allocation check: n = {len(chk)}, median relative difference {100 * chk.rel_diff.median():+.1f}%, "
          f"90% of estimates within {100 * chk.rel_diff.abs().quantile(0.9):.1f}%, "
          f"deaths identical in {100 * (chk.deaths_published == chk.deaths_recovered).mean():.0f}% of cells")

    # F10 + K70: rates standardised with the same weights are additive
    s = t.groupby(["year", "region", "sex", "age"]).agg(deaths=("deaths", "sum"), rate=("rate", "sum"), n=("rate", "count"),
                                                         src=("rate_source", lambda x: "; ".join(sorted(set(x) - {""})))).reset_index()
    s = s[s.n == 2].drop(columns="n").assign(icd="F10+K70").rename(columns={"src": "rate_source"})
    out = pd.concat([t, s], ignore_index=True).sort_values(["icd", "region", "sex", "age", "year"])
    out["rate"] = out.rate.round(2)
    out.to_csv(DER / "alcohol_mortality_east_west.csv", index=False)
    print(f"wrote alcohol_mortality_east_west.csv ({len(out)} rows)")


if __name__ == "__main__":
    main()
