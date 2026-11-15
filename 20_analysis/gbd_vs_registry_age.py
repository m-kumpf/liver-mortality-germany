"""Step 8: GBD 2023 age-specific estimates combined to the registry bands and compared with the registry rates.

GBD five-year rates are combined to 45-64, 65-74 and 75 and over with the ESP2013 weights renormalised within the
band, the same quantity as sdr_in_band in step 6; GBD counts are summed.

Inputs
  01_gbd2023/gbd2023_cirrhosis_deaths_by_5yr_age_9countries_2000_2023.csv          cause 521, deaths, by five-year age group
  01_gbd2023/gbd2023_cirrhosis_aetiology_deaths_by_age_9countries_2010_2019_2023.csv  causes 521, 522, 523, 524, 971, 525 by age
  10_derived/age_specific_rates.csv (step 6)
Outputs
  10_derived/gbd_age_bands.csv                      GBD band rates and counts by sex and year
  10_derived/gbd_vs_registry_age_bands.csv          GBD against registry K70-K76 and K70+K74 by band, sex and year
  10_derived/gbd_vs_registry_age_bands_summary.csv  mean ratio 2015-2022 and percent change 2010-2022 by sex and band
  10_derived/gbd_aetiology_age_bands.csv            GBD rates and shares of the five modelled causes by band, 2010, 2019, 2023
  10_derived/gbd_aetiology_age_bands_summary.csv    percent change 2010-2023 and share in 2023 by cause and band, both sexes

Run from the project root:  python3 20_analysis/gbd_vs_registry_age.py
"""
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from whomdb_common import ESP2013

ROOT = pathlib.Path(__file__).resolve().parents[1]
GBD = ROOT / "01_gbd2023"
DER = ROOT / "10_derived"
ISO = {"Germany": "DE", "France": "FR", "Italy": "IT", "Spain": "ES", "United Kingdom": "UK",
       "Poland": "PL", "Czechia": "CZ", "Austria": "AT", "Netherlands": "NL"}
BANDS = {"45-64": ["45-49", "50-54", "55-59", "60-64"],
         "65-74": ["65-69", "70-74"],
         "75plus": ["75-79", "80-84", "85-89", "90-94", "95+"]}
SEX = {"male": "M", "female": "F", "combined": "T"}
CAUSE_SHORT = {"Cirrhosis and other chronic liver diseases": "total",
               "Cirrhosis due to alcohol": "alcohol",
               "Chronic hepatitis B including cirrhosis": "hbv",
               "Chronic hepatitis C including cirrhosis": "hcv",
               "Nonalcoholic fatty liver disease including cirrhosis": "masld",
               "Cirrhosis due to other causes": "other"}


def norm_age(a):
    return a.replace(" to ", "-").replace(" plus", "+").strip()


def to_bands(df):
    out = []
    for (iso, year, cause), g in df.groupby(["iso", "year", "cause"]):
        g = g.set_index("age5")
        for band, groups in BANDS.items():
            if any(a not in g.index for a in groups):
                continue
            w = {a: ESP2013[a] for a in groups}
            wsum = sum(w.values())
            row = {"iso": iso, "year": year, "cause": cause, "band": band}
            for s, sx in SEX.items():
                row[f"rate_{sx}"] = sum(g.loc[a, f"rate_{s}"] * w[a] for a in groups) / wsum
                row[f"deaths_{sx}"] = sum(g.loc[a, f"count_{s}"] for a in groups)
                row[f"rate_lower_{sx}"] = sum(g.loc[a, f"rate_lower_{s}"] * w[a] for a in groups) / wsum
                row[f"rate_upper_{sx}"] = sum(g.loc[a, f"rate_upper_{s}"] * w[a] for a in groups) / wsum
            out.append(row)
    return pd.DataFrame(out)


def main():
    t = pd.read_csv(GBD / "gbd2023_cirrhosis_deaths_by_5yr_age_9countries_2000_2023.csv")
    t["iso"] = t.location_name.map(ISO)
    t["age5"] = t.age_group.map(norm_age)
    t["cause"] = "total"
    gb = to_bands(t).sort_values(["iso", "band", "year"])
    gb.to_csv(DER / "gbd_age_bands.csv", index=False, float_format="%.3f")
    print(f"wrote gbd_age_bands.csv ({len(gb)} rows)")

    r = pd.read_csv(DER / "age_specific_rates.csv")
    r = r[r.iso.isin(ISO.values()) & r.band.isin(BANDS) & r.code_group.isin(["K70_K76", "K70_K74"])]
    r = r.pivot_table(index=["iso", "year", "band", "sex"], columns="code_group", values="sdr_in_band").reset_index()
    gl = gb.melt(id_vars=["iso", "year", "band"], value_vars=["rate_M", "rate_F", "rate_T"], var_name="sex", value_name="gbd")
    gl["sex"] = gl.sex.str[-1]
    cmp_ = gl.merge(r, on=["iso", "year", "band", "sex"], how="left")
    cmp_["ratio_gbd_K70_K76"] = cmp_.gbd / cmp_.K70_K76
    cmp_["ratio_gbd_K70_K74"] = cmp_.gbd / cmp_.K70_K74
    cmp_ = cmp_.sort_values(["iso", "sex", "band", "year"])
    cmp_.to_csv(DER / "gbd_vs_registry_age_bands.csv", index=False, float_format="%.3f")
    print("wrote gbd_vs_registry_age_bands.csv")

    ratio = cmp_[cmp_.year.between(2015, 2022)].groupby(["iso", "sex", "band"]).ratio_gbd_K70_K76.mean().rename(
        "ratio_gbd_K70_K76_mean_2015_2022")
    piv = cmp_[cmp_.year.isin([2010, 2022])].pivot_table(index=["iso", "sex", "band"], columns="year",
                                                         values=["gbd", "K70_K76"])
    summ = pd.DataFrame({"pct_2010_2022_gbd": 100 * (piv[("gbd", 2022)] / piv[("gbd", 2010)] - 1),
                         "pct_2010_2022_registry_K70_K76": 100 * (piv[("K70_K76", 2022)] / piv[("K70_K76", 2010)] - 1)})
    summ = summ.join(ratio).reset_index()
    summ.to_csv(DER / "gbd_vs_registry_age_bands_summary.csv", index=False, float_format="%.3f")
    print("wrote gbd_vs_registry_age_bands_summary.csv")

    a = pd.read_csv(GBD / "gbd2023_cirrhosis_aetiology_deaths_by_age_9countries_2010_2019_2023.csv")
    a["iso"] = a.location_name.map(ISO)
    a["age5"] = a.age_group.map(norm_age)
    a["cause"] = a.cause_name.map(CAUSE_SHORT)
    a = a[a.age5.isin([x for b in BANDS.values() for x in b])]
    ab = to_bands(a)
    tot = ab[ab.cause == "total"].set_index(["iso", "year", "band"])
    for sx in ["M", "F", "T"]:
        ab[f"share_{sx}"] = ab.apply(lambda x: x[f"deaths_{sx}"] / tot.loc[(x.iso, x.year, x.band), f"deaths_{sx}"], axis=1)
    ab = ab.sort_values(["iso", "band", "year", "cause"])
    ab.to_csv(DER / "gbd_aetiology_age_bands.csv", index=False, float_format="%.4f")
    print("wrote gbd_aetiology_age_bands.csv")

    p = ab.pivot_table(index=["iso", "band", "cause"], columns="year", values=["rate_T", "share_T"])
    asum = pd.DataFrame({"rate_T_2010": p[("rate_T", 2010)], "rate_T_2023": p[("rate_T", 2023)],
                         "pct_2010_2023": 100 * (p[("rate_T", 2023)] / p[("rate_T", 2010)] - 1),
                         "share_T_2023": p[("share_T", 2023)]}).reset_index()
    asum.to_csv(DER / "gbd_aetiology_age_bands_summary.csv", index=False, float_format="%.4f")
    print("wrote gbd_aetiology_age_bands_summary.csv")


if __name__ == "__main__":
    main()
