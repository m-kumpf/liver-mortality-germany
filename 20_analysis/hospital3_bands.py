"""Step 11: three-character hospital table: stays, in-hospital deaths per 100 stays and length of stay by age band
for the liver codes and the comparators C22, F10 and B18.

Input : 04_destatis/gbe_full/hospital3/gbe594_by_age_long.csv  (download_gbe_full.py --table hospital3)
Output: 10_derived/hospital3_subset.csv        rows used here (liver and comparator codes, five-year ages); reused if present
        10_derived/hospital3_bands.csv         icd, region, sex, band, year, cases, rate, inhosp_deaths, cfr_pct, bed_days, mean_los
        10_derived/hospital3_bands_summary.csv rates, case fatality and length of stay in 2000, 2010, 2019 and 2023

Band rate as in step 9. Case fatality (cfr_pct) = 100 x in-hospital deaths / stays summed over the five-year groups of
the band; mean_los = bed days / stays.

Run from the project root:  python3 20_analysis/hospital3_bands.py
"""
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from east_west_age_bands import AGE, W, BANDS

ROOT = pathlib.Path(__file__).resolve().parents[1]
IN = ROOT / "04_destatis" / "gbe_full" / "hospital3" / "gbe594_by_age_long.csv"
DER = ROOT / "10_derived"
SUB = DER / "hospital3_subset.csv"
ICD = ["K70-K77", "K70", "K71", "K72", "K73", "K74", "K75", "K76", "C22", "F10", "B18", "B15-B19", "K00-K93"]
MEAS = {"Fälle": "cases", "Fälle je 100.000 Einwohner": "crude", "Sterbefälle": "deaths",
        "Berechnungs- und Belegungstage": "bed_days"}
REG = {"Deutschland": "DE", "Früheres Bundesgebiet und Berlin-Ost": "West", "Neue Länder ohne Berlin-Ost": "East"}


def subset():
    if SUB.exists():
        return pd.read_csv(SUB)
    parts = []
    for i, ch in enumerate(pd.read_csv(IN, chunksize=2_000_000,
                                       usecols=["year", "region_code", "region", "sex", "icd", "age", "measure", "value"])):
        ch["measure"] = ch.measure.str.replace(r"\s+", " ", regex=True)
        parts.append(ch[ch.icd.isin(ICD) & ch.age.isin(AGE) & ch.measure.isin(MEAS)])
        print(f"   chunk {i + 1} read", flush=True)
    d = pd.concat(parts, ignore_index=True)
    d.to_csv(SUB, index=False)
    print(f"wrote hospital3_subset.csv ({len(d)} rows)")
    return d


def main():
    d = subset()
    d["age5"] = d.age.map(AGE)
    d["measure"] = d.measure.map(MEAS)
    d["value"] = d.value.fillna(0)
    d["region"] = d.region.map(REG).fillna(d.region)
    x = d.pivot_table(index=["icd", "region", "sex", "year", "age5"], columns="measure", values="value",
                      aggfunc="first").fillna(0).reset_index()
    out = []
    for (icd, reg, sex, year), g in x.groupby(["icd", "region", "sex", "year"]):
        g = g.set_index("age5")
        for band, ages in BANDS.items():
            if not all(a in g.index for a in ages):
                continue
            ws = sum(W[a] for a in ages)
            c, dth, bd = g.loc[ages, "cases"].sum(), g.loc[ages, "deaths"].sum(), g.loc[ages, "bed_days"].sum()
            out.append(dict(icd=icd, region=reg, sex=sex, band=band, year=year, cases=c,
                            rate=sum(g.loc[a, "crude"] * W[a] for a in ages) / ws,
                            inhosp_deaths=dth, cfr_pct=100 * dth / c if c else float("nan"),
                            bed_days=bd, mean_los=bd / c if c else float("nan")))
    r = pd.DataFrame(out).sort_values(["icd", "region", "sex", "band", "year"])
    r.to_csv(DER / "hospital3_bands.csv", index=False, float_format="%.3f")
    print(f"wrote hospital3_bands.csv ({len(r)} rows)")

    ref = [2000, 2010, 2019, 2023]
    w = r[r.year.isin(ref)].pivot_table(index=["icd", "region", "sex", "band"], columns="year",
                                        values=["rate", "cfr_pct", "mean_los"]).reset_index()
    w.columns = ["_".join(str(c) for c in col if c != "") for col in w.columns]
    w["rate_pct_2010_2019"] = 100 * (w["rate_2019"] / w["rate_2010"] - 1)
    w["rate_pct_2010_2023"] = 100 * (w["rate_2023"] / w["rate_2010"] - 1)
    w.to_csv(DER / "hospital3_bands_summary.csv", index=False, float_format="%.2f")
    print("wrote hospital3_bands_summary.csv")


if __name__ == "__main__":
    main()
