"""Step 6: age-band mortality rates from the WHO Mortality Database extract, 16 European countries, 2000 onwards.

Bands: under 65, 65 and over, 25-44, 45-64, 65-74 and 75 and over. The band rate (sdr_in_band) is the ESP2013-weighted
mean of the five-year rates within the band; harmonisation and denominators as in step 3.

Output: 10_derived/age_specific_rates.csv   iso, year, sex, code_group, band, deaths, population, crude_rate, sdr_in_band

Run from the project root:  python3 20_analysis/age_specific_comparison.py
"""
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from whomdb_common import GROUPS, ESP2013, to_groups, collapse, eurostat_pop

ROOT = pathlib.Path(__file__).resolve().parents[1]
DER = ROOT / "10_derived"
COUNTRIES = ["DE", "FR", "IT", "ES", "UK", "PL", "CZ", "AT", "NL", "SE", "DK", "PT", "HU", "CH", "BE", "FI"]
BANDS = {"u65": ("0", "60-64"), "65plus": ("65-69", "95+"), "25-44": ("25-29", "40-44"), "45-64": ("45-49", "60-64"),
         "65-74": ("65-69", "70-74"), "75plus": ("75-79", "95+")}


def code_group(c):
    out = []
    if c.startswith("K70"): out += ["K70", "K70_K74", "K70_K76"]
    if c.startswith("K74"): out += ["K74", "K70_K74", "K70_K76"]
    if c == "K746": out += ["K746"]
    if c.startswith(("K71", "K72", "K73", "K75", "K76")): out += ["K70_K76"]
    if c.startswith("C22"): out += ["C22"]
    if c.startswith("B18"): out += ["B18"]
    if c == "AAA": out += ["AAA"]
    return out


def pad(d):
    return {k: d.get(k, np.nan) for k in GROUPS}


def main():
    raw = pd.read_csv(DER / "who_mdb_liver_raw.csv", dtype={"Cause": str, "Frmat": str, "Sex": str, "Admin1": str,
                                                            "SubDiv": str}, low_memory=False)
    raw = raw[raw["Admin1"].fillna("").eq("") & raw["SubDiv"].fillna("").eq("") & raw["Sex"].isin(["1", "2"])
              & raw["iso"].isin(COUNTRIES) & (raw["Year"] >= 2000)].copy()
    pop = pd.read_csv(DER / "who_mdb_pop_raw.csv", dtype={"Frmat": str, "Sex": str, "Admin1": str, "SubDiv": str},
                      low_memory=False)
    pop = pop[pop["Admin1"].fillna("").eq("") & pop["SubDiv"].fillna("").eq("") & pop["Sex"].astype(str).isin(["1", "2"])].copy()
    pop["Sex"] = pop["Sex"].astype(str)

    pop_h = {}
    for _, r in pop.iterrows():
        g, top = to_groups(r, "Pop")
        if g is not None:
            pop_h[(str(r["Country"]), int(r["Year"]), r["Sex"])] = (g, top)
    iso_by_country = raw.drop_duplicates("Country").set_index("Country")["iso"].to_dict()
    for (geo, yr, sx), v in eurostat_pop().items():
        for ctry, iso in iso_by_country.items():
            if iso == geo:
                pop_h[(str(ctry), yr, sx)] = v

    eff_top = {}
    for _, r in raw[raw["Cause"].eq("AAA")].iterrows():
        g, top = to_groups(r, "Deaths")
        if g is not None:
            eff_top[(str(r["Country"]), int(r["Year"]), r["Sex"])] = top

    acc = {}
    for _, r in raw.iterrows():
        groups = code_group(r["Cause"])
        if not groups:
            continue
        g, top = to_groups(r, "Deaths", top_override=eff_top.get((str(r["Country"]), int(r["Year"]), r["Sex"])))
        if g is None:
            continue
        unk = r.get("Deaths26", np.nan)
        known = np.nansum(list(g.values()))
        if unk and not np.isnan(unk) and unk > 0 and known > 0:
            g = {k: (v + v / known * unk if not np.isnan(v) else v) for k, v in g.items()}
        for grp in groups:
            key = (r["iso"], str(r["Country"]), int(r["Year"]), r["Sex"], grp)
            if key in acc:
                old, otop = acc[key]
                t = min(top, otop, key=GROUPS.index)
                a, b = collapse(old, t), collapse(g, t)
                acc[key] = ({k: a[k] + b[k] for k in a} | {k: np.nan for k in GROUPS[GROUPS.index(t) + 1:]}, t)
            else:
                acc[key] = (g, top)

    cells = {}
    for (iso, ctry, year, sex, grp), (g, top) in acc.items():
        ph = pop_h.get((ctry, year, sex))
        if ph is None:
            continue
        pg, ptop = ph
        t = min(top, ptop, key=GROUPS.index)
        cells[(iso, year, grp, {"1": "M", "2": "F"}[sex])] = (collapse(pad(g), t), collapse(pad(pg), t), t)
    for (iso, year, grp, sx) in list(cells):
        if sx != "M" or (iso, year, grp, "F") not in cells:
            continue
        dm, pm, tm = cells[(iso, year, grp, "M")]
        df_, pf, tf = cells[(iso, year, grp, "F")]
        t = min(tm, tf, key=GROUPS.index)
        dm, pm, df_, pf = collapse(pad(dm), t), collapse(pad(pm), t), collapse(pad(df_), t), collapse(pad(pf), t)
        cells[(iso, year, grp, "T")] = ({k: dm[k] + df_[k] for k in dm}, {k: pm[k] + pf[k] for k in pm}, t)

    rows = []
    for (iso, year, grp, sx), (d, p, t) in cells.items():
        for band, (lo, hi) in BANDS.items():
            if GROUPS.index(t) < GROUPS.index(lo):
                continue
            hi_eff = hi if GROUPS.index(hi) <= GROUPS.index(t) else t
            ks = GROUPS[GROUPS.index(lo):GROUPS.index(hi_eff) + 1]
            deaths = float(np.nansum([d[k] for k in ks]))
            popn = float(np.nansum([p[k] for k in ks]))
            if popn <= 0:
                continue
            w = {k: ESP2013[k] for k in ks}
            if hi_eff == t:
                w[t] = sum(ESP2013[k] for k in GROUPS[GROUPS.index(t):GROUPS.index(hi) + 1])
            wsum = sum(w.values())
            sdr_b = sum((d[k] / p[k] if p[k] > 0 else 0) * w[k] for k in ks) / wsum * 1e5
            rows.append(dict(iso=iso, year=year, sex=sx, code_group=grp, band=band, deaths=round(deaths, 1),
                             population=round(popn), crude_rate=deaths / popn * 1e5, sdr_in_band=sdr_b, top_age_group=t))
    res = pd.DataFrame(rows).sort_values(["code_group", "band", "iso", "sex", "year"])
    res.to_csv(DER / "age_specific_rates.csv", index=False, float_format="%.3f")
    print("age_specific_rates rows:", len(res))


if __name__ == "__main__":
    main()
