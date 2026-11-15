"""Step 19: drinking pattern in eastern and western Germany from the GEDA surveys (step 18).

Inputs
  04_destatis/gbe_geda/gbe_geda_alcohol_long.csv   GEDA 2009/2010/2012 (West, Ost and sub-regions) and GEDA 2014/2015-EHIS (16 Laender)
  04_destatis/12411-0042_...csv                    mid-year population by Land (weights for the 2014/2015 East/West means)
Output
  10_derived/geda_alcohol_east_west.csv            survey, year, indicator, sex, age, East, West, Germany, East/West ratio, method

Indicators
  GEDA 2009, 2010, 2012 (telephone interviews): risky drinking = AUDIT-C score of at least 5 (men) or 4 (women);
    heavy episodic drinking = six or more drinks on one occasion, at least weekly / at least monthly (weekly + monthly).
  GEDA 2014/2015-EHIS (self-administered questionnaire): risky intake = more than 20 g (men) or 10 g (women) of pure
    alcohol per day among people who drink at least weekly, as a share of all respondents; heavy episodic drinking as above.
  The two survey generations differ in instrument, answer categories, reference period and mode.

Regions
  GEDA 2009-2012: the published aggregates West and Ost (Ost includes Berlin); the three waves are summarised as the
    mean of the three published estimates.
  GEDA 2014/2015: East = Brandenburg, Mecklenburg-Vorpommern, Sachsen, Sachsen-Anhalt, Thueringen and West = the ten
    western Laender as population-weighted means (mid-year population 2015), Berlin excluded; a variant with Berlin
    assigned to West and the unweighted mean are also written.

Run from the project root:  python3 20_analysis/geda_east_west.py
"""
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
DER = ROOT / "10_derived"
GEDA = ROOT / "04_destatis" / "gbe_geda" / "gbe_geda_alcohol_long.csv"
POP = ROOT / "04_destatis" / "12411-0042_durchschnittsbevoelkerung_bundeslaender_jahre_nationalitaet_geschlecht.csv"
EAST = ["Brandenburg", "Mecklenburg-Vorpommern", "Sachsen", "Sachsen-Anhalt", "Thüringen"]
WEST = ["Baden-Württemberg", "Bayern", "Bremen", "Hamburg", "Hessen", "Niedersachsen", "Nordrhein-Westfalen",
        "Rheinland-Pfalz", "Saarland", "Schleswig-Holstein"]
AGES = ["18-29", "30-44", "45-64", "65plus", "alle"]
OLD, NEW = "GEDA 2009/2010/2012", "GEDA 2014/2015-EHIS"
INDICATORS = {  # indicator: {survey: (thema, [categories summed], definition)}
    "risky_auditc": {OLD: (192, ["Risikokonsum"], "AUDIT-C score ≥ 5 men / ≥ 4 women (telephone)")},
    "risky_intake_ehis": {NEW: (26612, ["Risikokonsum"], "EHIS frequency–quantity index > 20 g men / > 10 g women per day among weekly drinkers, share of all respondents (self-administered)")},
    "binge_weekly": {OLD: (193, ["Mindestens jede Woche"], "six or more drinks on one occasion at least weekly"),
                     NEW: (26613, ["Mindestens jede Woche"], "six or more drinks on one occasion at least weekly, past 12 months")},
    "binge_monthly_plus": {OLD: (193, ["Mindestens jede Woche", "Jeden Monat"], "six or more drinks on one occasion at least monthly (weekly + monthly)"),
                           NEW: (26613, ["Mindestens monatlich (Jeden Monat + mind. Jede Woche)"], "six or more drinks on one occasion at least monthly, past 12 months")},
    "abstainer": {OLD: (192, ["Nie-Trinker"], "never drinks alcohol"), NEW: (26612, ["Nie-Trinker"], "no alcohol in the past 12 months")},
}
LABEL = {"risky_auditc": "risky drinking, AUDIT-C", "risky_intake_ehis": "risky alcohol intake, EHIS",
         "binge_weekly": "heavy episodic drinking at least weekly", "binge_monthly_plus": "heavy episodic drinking at least monthly",
         "abstainer": "never drinks"}


def wmean(v, w):
    return float((v * w).sum() / w.sum())


def main():
    d = pd.read_csv(GEDA, dtype={"year": str})
    d["category"] = d.category.str.strip()
    pop = pd.read_csv(POP, sep=";", dtype=str)
    pop = pop[(pop["2_variable_attribute_label"] == "Insgesamt") & (pop["3_variable_attribute_label"] == "Insgesamt")
              & (pop.time == "2015")]
    w2015 = pd.to_numeric(pop.set_index("1_variable_attribute_label").value)

    rows = []
    for ind, by_survey in INDICATORS.items():
        for survey, (thema, cats, definition) in by_survey.items():
            sub = d[(d.thema == thema) & d.category.isin(cats)]
            if len(cats) > 1:
                sub = sub.groupby(["year", "sex", "age", "region"], as_index=False).value_pct.sum()
            base = {"survey": survey, "indicator": ind, "indicator_label": LABEL[ind], "definition": definition}
            if survey == OLD:
                waves = []
                for (year, sex, age), g in sub.groupby(["year", "sex", "age"]):
                    v = g.set_index("region").value_pct
                    r = dict(base, year=year, sex=sex, age=age, east=v["Ost"], west=v["West"], germany=v["Deutschland"],
                             method="published West/Ost aggregates (Ost incl. Berlin)")
                    rows.append(r)
                    waves.append(r)
                wv = pd.DataFrame(waves)
                for (sex, age), g in wv.groupby(["sex", "age"]):
                    if len(g) == 3:
                        rows.append(dict(base, year="2009-2012", sex=sex, age=age, east=round(g.east.mean(), 2),
                                         west=round(g.west.mean(), 2), germany=round(g.germany.mean(), 2),
                                         method="mean of the 2009, 2010 and 2012 estimates (Ost incl. Berlin)"))
            else:
                for (sex, age), g in sub.groupby(["sex", "age"]):
                    v = g.set_index("region").value_pct
                    e, w_, west_b = v.loc[EAST], v.loc[WEST], v.loc[WEST + ["Berlin"]]
                    rows.append(dict(base, year="2014/2015", sex=sex, age=age, east=round(wmean(e, w2015.loc[EAST]), 2),
                                     west=round(wmean(w_, w2015.loc[WEST]), 2), germany=v["Deutschland"],
                                     method="population-weighted mean of the Länder (2015 population, all ages), Berlin excluded"))
                    rows.append(dict(base, year="2014/2015", sex=sex, age=age, east=round(wmean(e, w2015.loc[EAST]), 2),
                                     west=round(wmean(west_b, w2015.loc[WEST + ["Berlin"]]), 2), germany=v["Deutschland"],
                                     method="population-weighted mean of the Länder, Berlin assigned to West (as in the mortality definition)"))
                    rows.append(dict(base, year="2014/2015", sex=sex, age=age, east=round(float(e.mean()), 2),
                                     west=round(float(w_.mean()), 2), germany=v["Deutschland"],
                                     method="unweighted mean of the Länder, Berlin excluded"))
    out = pd.DataFrame(rows)
    out["east_over_west"] = (out.east / out.west).round(3)
    out["age"] = pd.Categorical(out.age, AGES, ordered=True)
    out = out.sort_values(["indicator", "survey", "year", "sex", "age", "method"]).reset_index(drop=True)
    out.to_csv(DER / "geda_alcohol_east_west.csv", index=False)
    print(f"wrote geda_alcohol_east_west.csv ({len(out)} rows)")


if __name__ == "__main__":
    main()
