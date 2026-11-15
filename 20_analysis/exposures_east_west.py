"""Step 17: exposure series for the East/West analysis.

Inputs
  05_exposures/alcohol_gdr_frg_sieber1998.csv          per-capita consumption, GDR 1955-1989 and FRG 1960-1989 (transcribed)
  05_exposures/who_hfa_alcohol_germany.csv             WHO Europe HFA-DB recorded consumption, Germany 1961-2019 (step 16)
  05_exposures/mikrozensus_adipositasquote_laender.csv Mikrozensus obesity share by Land, 1999-2025 (step 16)
  01_gbd2023/gbd2023_paf_high_alcohol_cirrhosis_deaths_by_age_germany_2010_2023.csv
  01_gbd2023/gbd2023_sev_high_alcohol_high_bmi_germany_1990_2023.csv
  04_destatis/12411-0042_...csv                        mid-year population by Land (weights for the East/West means)

Outputs (10_derived/)
  exposures_alcohol_gdr_frg_annual.csv        annual per-inhabitant pure alcohol, GDR and FRG, reported and interpolated
  exposures_cohort_cumulative_alcohol.csv     litres summed from age 15 (not before 1960) to 1989, birth cohorts 1940-44 to 1955-59
  exposures_alcohol_frg_vs_hfa.csv            Sieber FRG (per inhabitant) against HFA-DB (per capita 15+) in the reported years
  exposures_obesity_east_west.csv             East, West, Berlin and Germany obesity share, unweighted and population-weighted means
  exposures_obesity_laender_change.csv        obesity share by Land with changes 1999-2021 and 2021-2025
  exposures_paf_alcohol_cirrhosis_by_age.csv  GBD 2023 alcohol-attributable fraction of cirrhosis deaths by age and sex, 2010 and 2023
  exposures_sev_germany.csv                   GBD 2023 age-standardised summary exposure values, 1990-2023

Cumulative consumption: for each birth cohort the first year counted is the mid-cohort birth year plus 15, but not
before 1960; annual values are interpolated linearly between the reported years of each state and summed through 1989.
East = Brandenburg, Mecklenburg-Vorpommern, Sachsen, Sachsen-Anhalt, Thueringen; West = the ten western Laender;
Berlin separate. Population weights are the mid-year population of the same year (2000 for 1999).

Run from the project root:  python3 20_analysis/exposures_east_west.py
"""
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXP = ROOT / "05_exposures"
GBD = ROOT / "01_gbd2023"
DER = ROOT / "10_derived"
POP = ROOT / "04_destatis" / "12411-0042_durchschnittsbevoelkerung_bundeslaender_jahre_nationalitaet_geschlecht.csv"
EAST = ["Brandenburg", "Mecklenburg-Vorpommern", "Sachsen", "Sachsen-Anhalt", "Thüringen"]
WEST = ["Baden-Württemberg", "Bayern", "Bremen", "Hamburg", "Hessen", "Niedersachsen", "Nordrhein-Westfalen",
        "Rheinland-Pfalz", "Saarland", "Schleswig-Holstein"]
COHORTS = [(1940, 1944), (1945, 1949), (1950, 1954), (1955, 1959)]
FIRST_YEAR, LAST_YEAR, START_AGE = 1960, 1989, 15


def alcohol_tables():
    s = pd.read_csv(EXP / "alcohol_gdr_frg_sieber1998.csv")
    pure = s[s.measure == "pure_alcohol"].pivot(index="year", columns="state", values="value").sort_index()
    annual = []
    for state in ["GDR", "FRG"]:
        rep = pure[state].dropna()
        years = np.arange(rep.index.min(), LAST_YEAR + 1)
        vals = np.interp(years, rep.index.values, rep.values)
        for y, v in zip(years, vals):
            annual.append({"state": state, "year": int(y), "litres_per_inhabitant": round(float(v), 4),
                           "reported": bool(y in rep.index)})
    annual = pd.DataFrame(annual)
    annual.to_csv(DER / "exposures_alcohol_gdr_frg_annual.csv", index=False)

    rows = []
    for b0, b1 in COHORTS:
        mid = (b0 + b1) // 2
        start = max(mid + START_AGE, FIRST_YEAR)
        for state in ["GDR", "FRG"]:
            a = annual[(annual.state == state) & (annual.year >= start) & (annual.year <= LAST_YEAR)]
            rows.append({"cohort": f"{b0}–{b1}", "birth_year_mid": mid, "first_year_counted": start,
                         "last_year_counted": LAST_YEAR, "years_counted": len(a), "state": state,
                         "litres_sum": round(float(a.litres_per_inhabitant.sum()), 1)})
    coh = pd.DataFrame(rows)
    wide = coh.pivot(index="cohort", columns="state", values="litres_sum")
    coh["frg_over_gdr"] = coh.cohort.map((wide.FRG / wide.GDR).round(3))
    coh.to_csv(DER / "exposures_cohort_cumulative_alcohol.csv", index=False)

    hfa = pd.read_csv(EXP / "who_hfa_alcohol_germany.csv")
    tot = hfa[hfa.measure == "pure_alcohol_total"].set_index("year").value
    cmp_rows = [{"year": int(y), "sieber_frg_per_inhabitant": v, "hfa_germany_per_capita_15plus": tot[y],
                 "ratio_sieber_over_hfa": round(v / tot[y], 3)}
                for y, v in pure["FRG"].dropna().items() if y in tot.index]
    pd.DataFrame(cmp_rows).to_csv(DER / "exposures_alcohol_frg_vs_hfa.csv", index=False)


def obesity_tables():
    o = pd.read_csv(EXP / "mikrozensus_adipositasquote_laender.csv")
    wide = o.pivot(index="region", columns="year", values="value")
    years = sorted(o.year.unique())
    pop = pd.read_csv(POP, sep=";", dtype=str)
    pop = pop[(pop["2_variable_attribute_label"] == "Insgesamt") & (pop["3_variable_attribute_label"] == "Insgesamt")]
    pop = pop.assign(year=pop.time.astype(int), value=pd.to_numeric(pop.value, errors="coerce"))
    popw = pop.pivot_table(index="1_variable_attribute_label", columns="year", values="value")

    rows = []
    for region, members in [("East", EAST), ("West", WEST), ("Berlin", ["Berlin"])]:
        for y in years:
            vals = wide.loc[members, y]
            py = y if y in popw.columns else int(popw.columns.min())
            w = popw.loc[members, py]
            rows.append({"region": region, "year": y, "n_laender": len(members),
                         "mean_unweighted": round(float(vals.mean()), 2),
                         "mean_popweighted": round(float((vals * w).sum() / w.sum()), 2), "population_year_used": py})
    for y in years:
        rows.append({"region": "Germany (published)", "year": y, "n_laender": 16, "mean_unweighted": wide.loc["Deutschland", y],
                     "mean_popweighted": wide.loc["Deutschland", y], "population_year_used": ""})
    pd.DataFrame(rows).to_csv(DER / "exposures_obesity_east_west.csv", index=False)

    ch = wide.copy()
    ch["group"] = ["East" if r in EAST else "West" if r in WEST else "Berlin" if r == "Berlin" else "Germany" for r in ch.index]
    ch["change_1999_2021_pp"] = (ch[2021] - ch[1999]).round(1)
    ch["change_2021_2025_pp"] = (ch[2025] - ch[2021]).round(1)
    ch = ch.reset_index().sort_values(["group", "change_1999_2021_pp"], ascending=[True, False])
    ch.to_csv(DER / "exposures_obesity_laender_change.csv", index=False)


def gbd_tables():
    p = pd.read_csv(GBD / "gbd2023_paf_high_alcohol_cirrhosis_deaths_by_age_germany_2010_2023.csv")
    rows = []
    for _, r in p.iterrows():
        for sex, key in [("M", "male"), ("F", "female"), ("T", "combined")]:
            rows.append({"year": r.year, "sex": sex, "age_group": r.age_group, "age_group_id": r.age_group_id,
                         "paf_pct": round(r[f"percent_{key}"], 2), "paf_lower": round(r[f"percent_lower_{key}"], 2),
                         "paf_upper": round(r[f"percent_upper_{key}"], 2),
                         "attributable_deaths": round(r[f"count_{key}"], 1)})
    pd.DataFrame(rows).to_csv(DER / "exposures_paf_alcohol_cirrhosis_by_age.csv", index=False)

    s = pd.read_csv(GBD / "gbd2023_sev_high_alcohol_high_bmi_germany_1990_2023.csv")
    rows = []
    for _, r in s.iterrows():
        for sex, key in [("M", "male"), ("F", "female"), ("T", "combined")]:
            rows.append({"year": r.year, "risk": r.risk_name, "sex": sex, "sev": round(r[f"sev_{key}"], 4),
                         "lower": round(r[f"lower_{key}"], 4), "upper": round(r[f"upper_{key}"], 4)})
    pd.DataFrame(rows).to_csv(DER / "exposures_sev_germany.csv", index=False)


if __name__ == "__main__":
    alcohol_tables()
    obesity_tables()
    gbd_tables()
    print("wrote the exposures_*.csv tables in 10_derived/")
