"""Step 3: age-standardise the WHO Mortality Database counts of step 2.

Method
  WHO age columns are mapped to 21 groups (0, 1-4, 5-9, ..., 95+) according to the age format of each row; the
  effective top group of a country, year and sex is that of its all-cause row. Deaths of unknown age are
  redistributed in proportion to the deaths of known age; age cells suppressed for confidentiality (Germany
  from 2021) are rescaled to the all-ages total (whomdb_common.to_groups). Denominators are Eurostat mid-year
  populations (mean of 1 January of year t and t+1, demo_pjan) where available and the WHO population file
  otherwise. Rates are directly standardised to the ESP2013 (21 groups) and to the WHO world standard (0-4
  pooled); standard weights above the top group are merged into it. Both sexes = male + female rows.
  Only national rows (Admin1 and SubDiv blank) are used.

Outputs
  00_meta/standard_populations/esp2013.csv, who_world_2000.csv
  10_derived/who_mdb_sdr.csv          country x year x sex x code group: deaths, population, crude rate, SDR (ESP2013),
                                      SDR (WHO world), top age group, population source
  10_derived/who_mdb_sdr_skipped.csv  rows with unsupported age formats or without denominators
  10_derived/sdr_compare.csv          own ESP2013 SDR for K70+K73+K74 against the Eurostat published rate;
                                      own WHO-standard SDR for K70-K76 against the GBD 2023 age-standardised rate
  10_derived/coding_indicators.csv    K74 and K74.6 share of K70+K74 deaths, K76.0 share of K70-K76, K70-K76 share of all deaths

Run from the project root:  python3 20_analysis/standardise_who_mdb.py
"""
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from whomdb_common import GROUPS, ESP2013, WHO2000, to_groups, collapse, sdr, eurostat_pop, write_standard_populations

ROOT = pathlib.Path(__file__).resolve().parents[1]
DER = ROOT / "10_derived"
GBD = ROOT / "01_gbd2023"
NAME2ISO = {"Germany": "DE", "France": "FR", "Italy": "IT", "Spain": "ES", "United Kingdom": "UK", "Netherlands": "NL",
            "Belgium": "BE", "Austria": "AT", "Switzerland": "CH", "Denmark": "DK", "Sweden": "SE", "Norway": "NO",
            "Finland": "FI", "Portugal": "PT", "Ireland": "IE", "Greece": "EL", "Luxembourg": "LU", "Poland": "PL",
            "Czechia": "CZ", "Slovakia": "SK", "Hungary": "HU", "Slovenia": "SI", "Croatia": "HR", "Romania": "RO",
            "Bulgaria": "BG", "Lithuania": "LT", "Latvia": "LV", "Estonia": "EE"}


def code_group(c):
    """Code groups to which a 3- or 4-character ICD-10 code contributes."""
    out = []
    if c.startswith("K70"): out += ["K70", "K70_K73_K74", "K70_K76"]
    if c.startswith("K71"): out += ["K71", "K70_K76"]
    if c.startswith("K72"): out += ["K72", "K72_K75", "K70_K76"]
    if c.startswith("K73"): out += ["K73", "K70_K73_K74", "K72_K75", "K70_K76"]
    if c.startswith("K74"): out += ["K74", "K70_K73_K74", "K72_K75", "K70_K76"]
    if c == "K746": out += ["K746"]
    if c.startswith("K75"): out += ["K75", "K72_K75", "K70_K76"]
    if c.startswith("K76"): out += ["K76", "K70_K76"]
    if c == "K760": out += ["K760"]
    if c.startswith("B18"): out += ["B18"]
    if c.startswith(("B15", "B16", "B17", "B18", "B19")): out += ["B15_B19"]
    if c.startswith("C22"): out += ["C22"]
    if c.startswith("F10"): out += ["F10"]
    if c == "AAA": out += ["AAA"]
    return out


def pad(d):
    return d | {k: np.nan for k in GROUPS if k not in d}


def main():
    write_standard_populations()
    raw = pd.read_csv(DER / "who_mdb_liver_raw.csv", dtype={"Cause": str, "Frmat": str, "List": str, "Sex": str,
                                                            "Admin1": str, "SubDiv": str}, low_memory=False)
    raw = raw[raw["Admin1"].fillna("").eq("") & raw["SubDiv"].fillna("").eq("") & raw["Sex"].isin(["1", "2"])].copy()
    pop = pd.read_csv(DER / "who_mdb_pop_raw.csv", dtype={"Frmat": str, "Sex": str, "Admin1": str, "SubDiv": str},
                      low_memory=False)
    pop = pop[pop["Admin1"].fillna("").eq("") & pop["SubDiv"].fillna("").eq("") & pop["Sex"].astype(str).isin(["1", "2"])].copy()
    pop["Sex"] = pop["Sex"].astype(str)

    skipped = []
    pop_h = {}
    for _, r in pop.iterrows():
        g, top = to_groups(r, "Pop")
        if g is None:
            skipped.append(("pop", r["Country"], r["Year"], r["Frmat"]))
            continue
        pop_h[(str(r["Country"]), int(r["Year"]), r["Sex"])] = (g, top)
    pop_source = {k: "who_pop" for k in pop_h}
    iso_by_country = raw.drop_duplicates("Country").set_index("Country")["iso"].to_dict()
    eu_pop = eurostat_pop()
    for ctry, iso in iso_by_country.items():
        for (geo, yr, sx), v in eu_pop.items():
            if geo == iso:
                pop_h[(str(ctry), yr, sx)] = v
                pop_source[(str(ctry), yr, sx)] = "eurostat_midyear"

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
            skipped.append(("deaths", r["Country"], r["Year"], r["Frmat"]))
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
                merged = {k: a[k] + b[k] for k in a}
                merged.update({k: np.nan for k in GROUPS[GROUPS.index(t) + 1:]})
                acc[key] = (merged, t)
            else:
                acc[key] = (g, top)

    out = []
    for (iso, ctry, year, sex, grp), (g, top) in acc.items():
        ph = pop_h.get((ctry, year, sex))
        if ph is None:
            skipped.append(("no_pop", ctry, year, sex))
            continue
        pg, ptop = ph
        t = min(top, ptop, key=GROUPS.index)
        d, p = collapse(g, t), collapse(pg, t)
        deaths = sum(v for v in d.values() if not np.isnan(v))
        poptot = sum(v for v in p.values() if not np.isnan(v))
        out.append(dict(iso=iso, who_country=ctry, year=year, sex={"1": "M", "2": "F"}[sex], code_group=grp,
                        deaths=round(deaths, 2), population=poptot, crude_rate=deaths / poptot * 1e5 if poptot else np.nan,
                        sdr_esp2013=sdr(d, p, t, ESP2013), sdr_who2000=sdr(d, p, t, WHO2000, pool_0_4=True),
                        top_age_group=t, pop_source=pop_source.get((ctry, year, sex), "")))
    res = pd.DataFrame(out)

    # both sexes
    accT = {}
    for (iso, ctry, year, sex, grp), (g, top) in acc.items():
        key = (iso, ctry, year, grp)
        ph = pop_h.get((ctry, year, sex))
        if ph is None:
            continue
        pg, ptop = ph
        t = min(top, ptop, key=GROUPS.index)
        d, p = collapse(g, t), collapse(pg, t)
        if key in accT:
            d0, p0, t0 = accT[key]
            t2 = min(t, t0, key=GROUPS.index)
            d0, p0 = collapse(pad(d0), t2), collapse(pad(p0), t2)
            d, p = collapse(pad(d), t2), collapse(pad(p), t2)
            accT[key] = ({k: np.nansum([d0[k], d[k]]) for k in d0}, {k: np.nansum([p0[k], p[k]]) for k in p0}, t2)
        else:
            accT[key] = (d, p, t)
    both = []
    for (iso, ctry, year, grp), (d, p, t) in accT.items():
        deaths, poptot = sum(d.values()), sum(p.values())
        both.append(dict(iso=iso, who_country=ctry, year=year, sex="T", code_group=grp, deaths=round(deaths, 2),
                         population=poptot, crude_rate=deaths / poptot * 1e5 if poptot else np.nan,
                         sdr_esp2013=sdr(d, p, t, ESP2013), sdr_who2000=sdr(d, p, t, WHO2000, pool_0_4=True),
                         top_age_group=t, pop_source=pop_source.get((ctry, year, "1"), "")))
    res = pd.concat([res, pd.DataFrame(both)], ignore_index=True).sort_values(["iso", "code_group", "sex", "year"])
    res.to_csv(DER / "who_mdb_sdr.csv", index=False, float_format="%.4f")
    pd.DataFrame(skipped, columns=["what", "country", "year", "detail"]).drop_duplicates().to_csv(
        DER / "who_mdb_sdr_skipped.csv", index=False)
    print("who_mdb_sdr rows:", len(res), "| skipped rows:", len(set(skipped)))

    # validation against Eurostat (K70+K73+K74, ESP2013) and comparison with GBD 2023 (K70-K76, WHO world standard)
    cmp = res[res.code_group.eq("K70_K73_K74")][["iso", "year", "sex", "deaths", "sdr_esp2013", "sdr_who2000",
                                                 "top_age_group"]].rename(columns={"deaths": "who_deaths"})
    eu = pd.concat([pd.read_csv(ROOT / "02_eurostat" / f"hlth_cd_asdr2_K70_K73_K74_{s}.csv").assign(sex=s)
                    for s in ["T", "M", "F"]])
    eu = eu.rename(columns={"geo": "iso", "time": "year", "value": "eurostat_sdr_esp2013"})[
        ["iso", "year", "sex", "eurostat_sdr_esp2013"]]
    cmp = cmp.merge(eu, on=["iso", "year", "sex"], how="left")
    cmp["diff_pct_vs_eurostat"] = (cmp.sdr_esp2013 / cmp.eurostat_sdr_esp2013 - 1) * 100
    gbd = pd.concat([pd.read_csv(GBD / "gbd2023_cirrhosis_deaths_western_europe_2010_2023.csv"),
                     pd.read_csv(GBD / "gbd2023_cirrhosis_deaths_central_eastern_europe_comparators_2010_2023.csv")])
    gbd["iso"] = gbd.location_name.map(NAME2ISO)
    gbd = gbd.dropna(subset=["iso"])
    gl = pd.concat([gbd[["iso", "year", f"rate_age_std_{k}"]].rename(columns={f"rate_age_std_{k}": "gbd_asr"}).assign(sex=s)
                    for k, s in [("combined", "T"), ("male", "M"), ("female", "F")]])
    k76 = res[res.code_group.eq("K70_K76")][["iso", "year", "sex", "sdr_who2000"]].rename(
        columns={"sdr_who2000": "who_sdr_K70_K76_who2000"})
    cmp = cmp.merge(k76, on=["iso", "year", "sex"], how="left").merge(gl, on=["iso", "year", "sex"], how="left")
    cmp["ratio_gbd_over_registry"] = cmp.gbd_asr / cmp.who_sdr_K70_K76_who2000
    cmp.sort_values(["iso", "sex", "year"]).to_csv(DER / "sdr_compare.csv", index=False, float_format="%.3f")

    piv = res.pivot_table(index=["iso", "year", "sex"], columns="code_group", values="deaths").reset_index()
    ind = piv[["iso", "year", "sex"]].copy()
    ind["share_K746_in_K70_K74"] = piv["K746"] / (piv["K70"] + piv["K74"])
    ind["share_K74_in_K70_K74"] = piv["K74"] / (piv["K70"] + piv["K74"])
    ind["share_K760_in_K70_K76"] = piv["K760"] / piv["K70_K76"]
    ind["share_K70_K76_in_all"] = piv["K70_K76"] / piv["AAA"]
    ind.to_csv(DER / "coding_indicators.csv", index=False, float_format="%.4f")

    chk = cmp[cmp.sex.eq("T") & cmp.year.between(2011, 2023)].groupby("iso").diff_pct_vs_eurostat.agg(
        n="count", median_abs=lambda x: x.abs().median(), max_abs=lambda x: x.abs().max())
    print("\nOwn ESP2013 SDR (K70+K73+K74) against Eurostat, both sexes, 2011-2023, % difference:")
    print(chk.round(2).to_string())


if __name__ == "__main__":
    main()
