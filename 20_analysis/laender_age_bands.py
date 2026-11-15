"""Step 12: the 16 Laender by age band: K70-K77 deaths, cirrhosis stays and coding shares.

Inputs: 04_destatis/gbe_full/deaths/gbe6_by_age_long.csv       (download_gbe_full.py --table deaths --laender)
        04_destatis/gbe_full/hospital4/gbe703_by_age_long.csv  (download_gbe_full.py --table hospital4 --laender)
        04_destatis/gbe_bund/gbe517_top100_esp2013_long.csv    (step 5)
Outputs: 10_derived/laender_deaths_subset.csv, laender_hospital4_subset.csv   rows used here; reused if present
         10_derived/laender_age_bands.csv           land, sex, band, year, K70-K77 death rate and deaths, K70.3/K74.6/K76.0 stay rates
         10_derived/laender_age_bands_summary.csv   three-year means (2009-11, 2018-20, 2022-24), percent change,
                                                    K74.6 share of cirrhosis stays, K74 share of K70+K74 deaths (all ages)

Band rates as in step 9.

Run from the project root:  python3 20_analysis/laender_age_bands.py
"""
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from east_west_age_bands import AGE, W, BANDS

ROOT = pathlib.Path(__file__).resolve().parents[1]
D_IN = ROOT / "04_destatis" / "gbe_full" / "deaths" / "gbe6_by_age_long.csv"
H_IN = ROOT / "04_destatis" / "gbe_full" / "hospital4" / "gbe703_by_age_long.csv"
T_IN = ROOT / "04_destatis" / "gbe_bund" / "gbe517_top100_esp2013_long.csv"
DER = ROOT / "10_derived"
EAST = {"Brandenburg", "Mecklenburg-Vorpommern", "Sachsen", "Sachsen-Anhalt", "Thüringen"}
SHORT = {"Baden-Württemberg": "BW", "Bayern": "BY", "Berlin": "BE", "Brandenburg": "BB", "Bremen": "HB", "Hamburg": "HH",
         "Hessen": "HE", "Mecklenburg-Vorpommern": "MV", "Niedersachsen": "NI", "Nordrhein-Westfalen": "NW",
         "Rheinland-Pfalz": "RP", "Saarland": "SL", "Sachsen": "SN", "Sachsen-Anhalt": "ST", "Schleswig-Holstein": "SH",
         "Thüringen": "TH", "Deutschland": "DE", "Früheres Bundesgebiet und Berlin-Ost": "West",
         "Neue Länder ohne Berlin-Ost": "East"}


def subset(path, out, icds, measures):
    if out.exists():
        return pd.read_csv(out)
    parts = []
    for i, ch in enumerate(pd.read_csv(path, chunksize=2_000_000,
                                       usecols=["year", "region", "sex", "icd", "age", "measure", "value"])):
        ch["measure"] = ch.measure.str.replace(r"\s+", " ", regex=True)
        parts.append(ch[ch.icd.isin(icds) & ch.age.isin(AGE) & ch.measure.isin(measures)])
        print(f"   {path.name}: chunk {i + 1}", flush=True)
    d = pd.concat(parts, ignore_index=True)
    d.to_csv(out, index=False)
    print(f"wrote {out.name} ({len(d)} rows)")
    return d


def bands(d, value_measure, count_measure, name):
    d = d.copy()
    d["age5"] = d.age.map(AGE)
    d["value"] = d.value.fillna(0)
    d["land"] = d.region.map(SHORT)
    x = d.pivot_table(index=["icd", "land", "sex", "year", "age5"], columns="measure", values="value",
                      aggfunc="first").fillna(0).reset_index()
    out = []
    for (icd, land, sex, year), g in x.groupby(["icd", "land", "sex", "year"]):
        g = g.set_index("age5")
        for band, ages in BANDS.items():
            if not all(a in g.index for a in ages):
                continue
            ws = sum(W[a] for a in ages)
            out.append(dict(icd=icd, land=land, sex=sex, band=band, year=year,
                            **{f"{name}_rate": sum(g.loc[a, value_measure] * W[a] for a in ages) / ws,
                               f"{name}_n": g.loc[ages, count_measure].sum()}))
    return pd.DataFrame(out)


def main():
    dd = subset(D_IN, DER / "laender_deaths_subset.csv", ["K70-K77"], ["Sterbefälle", "Sterbefälle je 100.000 Einwohner"])
    hh = subset(H_IN, DER / "laender_hospital4_subset.csv", ["K70", "K70.3", "K74", "K74.6", "K76.0", "K70-K77"],
                ["Fälle", "Fälle je 100.000 Einwohner"])
    db = bands(dd, "Sterbefälle je 100.000 Einwohner", "Sterbefälle", "deaths")
    hb = bands(hh, "Fälle je 100.000 Einwohner", "Fälle", "stays")
    hw = hb.pivot_table(index=["land", "sex", "band", "year"], columns="icd", values=["stays_rate", "stays_n"]).reset_index()
    hw.columns = ["_".join(c).strip("_") if c[1] else c[0] for c in hw.columns]
    hw["k746_share_stays"] = hw["stays_n_K74.6"] / (hw["stays_n_K70.3"] + hw["stays_n_K74.6"])
    r = db[db.icd == "K70-K77"].drop(columns="icd").merge(hw, on=["land", "sex", "band", "year"], how="outer")
    r = r.sort_values(["land", "sex", "band", "year"])
    r.to_csv(DER / "laender_age_bands.csv", index=False, float_format="%.4f")
    print(f"wrote laender_age_bands.csv ({len(r)} rows)")

    def mean3(col, years):
        return r[r.year.isin(years)].groupby(["land", "sex", "band"])[col].mean()

    s = pd.DataFrame({"deaths_2010": mean3("deaths_rate", [2009, 2010, 2011]),
                      "deaths_2019": mean3("deaths_rate", [2018, 2019, 2020]),
                      "deaths_2023": mean3("deaths_rate", [2022, 2023, 2024]),
                      "k746_share_2010": mean3("k746_share_stays", [2009, 2010, 2011]),
                      "k746_share_2019": mean3("k746_share_stays", [2018, 2019, 2020]),
                      "stays_K703_2019": mean3("stays_rate_K70.3", [2018, 2019, 2020]),
                      "stays_K746_2019": mean3("stays_rate_K74.6", [2018, 2019, 2020]),
                      "stays_K760_2019": mean3("stays_rate_K76.0", [2018, 2019, 2020])}).reset_index()
    s["deaths_pct_2010_2019"] = 100 * (s.deaths_2019 / s.deaths_2010 - 1)
    s["deaths_pct_2010_2023"] = 100 * (s.deaths_2023 / s.deaths_2010 - 1)
    t = pd.read_csv(T_IN)
    t = t[(t.age == "alle") & t.icd3.isin(["K70", "K74"])]
    tp = t.pivot_table(index=["region", "sex", "year"], columns="icd3", values="deaths", aggfunc="first").reset_index()
    tp["land"] = tp.region.map(SHORT)
    tp["k74_share_deaths"] = tp.K74 / (tp.K70 + tp.K74)
    k = tp[tp.year.between(2018, 2020)].groupby(["land", "sex"]).k74_share_deaths.mean().rename("k74_share_deaths_2019").reset_index()
    s = s.merge(k, on=["land", "sex"], how="left")
    s["east"] = s.land.isin({SHORT[x] for x in EAST})
    s.to_csv(DER / "laender_age_bands_summary.csv", index=False, float_format="%.3f")
    print("wrote laender_age_bands_summary.csv")


if __name__ == "__main__":
    main()
