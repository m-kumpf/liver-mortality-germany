"""Step 14: manuscript tables from the derived tables, values as printed.

Outputs (10_derived/tables/)
  table1.csv   Germany: K70, K74 and K70+K74 by sex and age band, 2010, 2019, 2022                  (step 7)
  tableS3.csv  own ESP2013 rate for K70+K73+K74 against the Eurostat published rate, by country     (step 3)
  tableS5.csv  Eurostat rate 2011, 2019, 2023 and GBD 2023 rate 2010, 2019, 2023 by country          (02_eurostat, 01_gbd2023, step 3)
  tableS6.csv  East and West Germany: K70-K77 by sex and age band, 2010, 2019, 2024                  (step 9)
  tableS7.csv  Laender: K70-K77 at 65-74, three-year means                                           (step 12)
  tableS8.csv  hospital stays by main diagnosis and in-hospital deaths per 100 stays, East and West  (steps 10, 11)
  tableS9.csv  self-reported drinking in eastern and western Germany, GEDA surveys                   (step 19)
  tables.md    the same tables as Markdown

Run from the project root:  python3 20_analysis/make_tables.py
"""
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
DER = ROOT / "10_derived"
OUT = DER / "tables"
OUT.mkdir(exist_ok=True)
BAND = {"45-64": "45–64", "65-74": "65–74", "75plus": "≥75"}
SEX = {"M": "Men", "F": "Women", "T": "Both sexes"}
CODE = {"K70": "Alcoholic liver disease (K70)", "K74": "Fibrosis and cirrhosis (K74)", "K70_K74": "K70 and K74 combined"}
NAMES = {"AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "HR": "Croatia", "CY": "Cyprus", "CZ": "Czechia",
         "DK": "Denmark", "EE": "Estonia", "FI": "Finland", "FR": "France", "DE": "Germany", "EL": "Greece",
         "HU": "Hungary", "IS": "Iceland", "IE": "Ireland", "IT": "Italy", "LV": "Latvia", "LT": "Lithuania",
         "LU": "Luxembourg", "MT": "Malta", "NL": "Netherlands", "NO": "Norway", "PL": "Poland", "PT": "Portugal",
         "RO": "Romania", "SK": "Slovakia", "SI": "Slovenia", "ES": "Spain", "SE": "Sweden", "CH": "Switzerland",
         "UK": "United Kingdom", "WE": "Western Europe"}
LAND = {"BW": "Baden-Württemberg", "BY": "Bavaria", "BE": "Berlin", "BB": "Brandenburg", "HB": "Bremen", "HH": "Hamburg",
        "HE": "Hesse", "MV": "Mecklenburg-Western Pomerania", "NI": "Lower Saxony", "NW": "North Rhine-Westphalia",
        "RP": "Rhineland-Palatinate", "SL": "Saarland", "SN": "Saxony", "ST": "Saxony-Anhalt", "SH": "Schleswig-Holstein",
        "TH": "Thuringia"}
EAST = {"BB", "MV", "SN", "ST", "TH"}
md = ["# Manuscript tables (20_analysis/make_tables.py)\n"]


def pct(a, b):
    return 100 * (b / a - 1)


def f1(x):
    return "" if pd.isna(x) else f"{x:.1f}"


def fp(x):
    if pd.isna(x):
        return ""
    v = round(x)
    return "0%" if v == 0 else f"{v:+.0f}%"


def fn(x):
    return "" if pd.isna(x) else f"{int(round(x)):,}".replace(",", " ")


def emit(name, title, df, note):
    df.to_csv(OUT / f"{name}.csv", index=False)
    md.append(f"## {title}\n")
    md.append(df.to_markdown(index=False))
    md.append(f"\n{note}\n")
    print("wrote", OUT / f"{name}.csv")


def table1():
    ab = pd.read_csv(DER / "age_band_detail.csv")
    ab = ab[(ab.iso == "DE") & ab.code_group.isin(CODE) & ab.sex.isin(["M", "F"]) & ab.year.isin([2010, 2019, 2022])]
    rows = []
    for code in CODE:
        for sex in ["M", "F"]:
            for band in BAND:
                s = ab[(ab.code_group == code) & (ab.sex == sex) & (ab.band == band)].set_index("year")
                rows.append({"Cause": CODE[code], "Sex": SEX[sex], "Age (years)": BAND[band],
                             "2010 rate": f1(s.loc[2010, "rate"]), "2010 deaths": fn(s.loc[2010, "deaths"]),
                             "2019 rate": f1(s.loc[2019, "rate"]), "2019 deaths": fn(s.loc[2019, "deaths"]),
                             "2022 rate": f1(s.loc[2022, "rate"]), "2022 deaths": fn(s.loc[2022, "deaths"]),
                             "Change 2010–2022": fp(pct(s.loc[2010, "rate"], s.loc[2022, "rate"]))})
    emit("table1", "Table 1. Mortality from alcoholic liver disease and from fibrosis and cirrhosis in Germany by sex "
         "and age band, 2010, 2019 and 2022", pd.DataFrame(rows),
         "Rates are deaths per 100 000 standardised to the European Standard Population 2013 within the age band; deaths "
         "are underlying-cause counts (WHO Mortality Database, Eurostat mid-year population).")


def table_s3():
    sc = pd.read_csv(DER / "sdr_compare.csv")
    sc = sc[(sc.sex == "T") & sc.year.between(2011, 2023) & sc.diff_pct_vs_eurostat.notna()]
    rows = []
    for iso, g in sc.groupby("iso"):
        d = g.diff_pct_vs_eurostat
        rows.append({"Country": NAMES[iso], "Years compared": f"{g.year.min()}–{g.year.max()}", "n": len(g),
                     "Median |difference| (%)": f"{d.abs().median():.2f}", "Maximum |difference| (%)": f"{d.abs().max():.2f}",
                     "Mean signed difference (%)": f"{d.mean():+.2f}"})
    t = pd.DataFrame(rows).sort_values("Country")
    emit("tableS3", "Table S3. Own ESP2013 age-standardised death rates for K70, K73 and K74 combined against the rates "
         "published by Eurostat, both sexes, by country", t,
         "Difference = (own rate − Eurostat rate) / Eurostat rate × 100, from WHO Mortality Database counts and Eurostat "
         "mid-year populations.")


def table_s5():
    eu = pd.read_csv(ROOT / "02_eurostat" / "hlth_cd_asdr2_K70_K73_K74_T.csv").pivot(index="geo", columns="time", values="value")
    g = pd.concat([pd.read_csv(ROOT / "01_gbd2023" / "gbd2023_cirrhosis_deaths_western_europe_2010_2023.csv"),
                   pd.read_csv(ROOT / "01_gbd2023" / "gbd2023_cirrhosis_deaths_central_eastern_europe_comparators_2010_2023.csv")])
    g = g[g.age_group == "all_ages"].pivot(index="location_name", columns="year", values="rate_age_std_combined")
    pc = pd.read_csv(ROOT / "01_gbd2023" / "gbd2023_cirrhosis_percent_change_2010_2023.csv").set_index("location_name")
    sc = pd.read_csv(DER / "sdr_compare.csv")
    ratio = sc[(sc.sex == "T") & sc.year.between(2015, 2022)].groupby("iso").ratio_gbd_over_registry.mean()
    rows = []
    for iso in ["DE", "AT", "BE", "CZ", "DK", "FI", "FR", "IT", "NL", "PL", "PT", "ES", "SE", "CH", "UK", "WE"]:
        nm = NAMES[iso]
        r = {"Country": nm}
        if iso in eu.index:
            e = eu.loc[iso]
            last = int(e.dropna().index.max())
            r.update({"Eurostat 2011": f1(e.get(2011)), "Eurostat 2019": f1(e.get(2019)) if last >= 2019 else "..",
                      "Eurostat 2023": f1(e.get(2023)) if last >= 2023 else f"{f1(e[last])} ({last})",
                      "Eurostat change": fp(pct(e[2011], e[last])) + ("" if last == 2023 else f" (2011–{last})")})
        else:
            r.update({"Eurostat 2011": "..", "Eurostat 2019": "..", "Eurostat 2023": "..", "Eurostat change": ".."})
        gg, p = g.loc[nm], pc.loc[nm]
        r.update({"GBD 2010": f1(gg[2010]), "GBD 2019": f1(gg[2019]), "GBD 2023": f1(gg[2023]),
                  "GBD change (95% UI)": f"{p.percent_change_rate_age_std_combined:+.1f}% "
                                         f"({p.lower_rate_age_std_combined:+.1f} to {p.upper_rate_age_std_combined:+.1f})",
                  "GBD / registry": f"{ratio[iso]:.2f}" if iso in ratio.index else ".."})
        rows.append(r)
    emit("tableS5", "Table S5. Age-standardised mortality from chronic liver disease by country: Eurostat registry series "
         "and GBD 2023 estimates", pd.DataFrame(rows),
         "Eurostat: deaths per 100 000 from K70, K73 and K74 (underlying cause, both sexes, ESP2013; UK series ends 2018). "
         "GBD: cirrhosis and other chronic liver diseases, age-standardised to the GBD world standard, with the published "
         "change 2010–2023 and 95% uncertainty interval. GBD / registry: mean of the annual ratios 2015–2022 of the GBD "
         "rate to the registered K70–K76 rate standardised to the WHO world standard. '..' not available.")


def table_s6():
    ew = pd.read_csv(DER / "east_west_age_bands.csv")
    ew = ew[(ew.icd == "K70-K77") & ew.year.isin([2010, 2019, 2024])]
    rows = []
    for sex in ["M", "F"]:
        for band in BAND:
            e = ew[(ew.sex == sex) & (ew.band == band) & (ew.region == "East")].set_index("year").rate
            w = ew[(ew.sex == sex) & (ew.band == band) & (ew.region == "West")].set_index("year").rate
            rows.append({"Sex": SEX[sex], "Age (years)": BAND[band],
                         "East 2010": f1(e[2010]), "East 2019": f1(e[2019]), "East 2024": f1(e[2024]),
                         "East change": fp(pct(e[2010], e[2024])),
                         "West 2010": f1(w[2010]), "West 2019": f1(w[2019]), "West 2024": f1(w[2024]),
                         "West change": fp(pct(w[2010], w[2024])),
                         "East/West 2010": f"{e[2010] / w[2010]:.2f}", "East/West 2024": f"{e[2024] / w[2024]:.2f}"})
    emit("tableS6", "Table S6. Mortality from diseases of the liver (K70–K77) in East and West Germany by sex and age band, "
         "2010, 2019 and 2024", pd.DataFrame(rows),
         "Deaths per 100 000 standardised to the ESP2013 within the age band (Todesursachenstatistik via GBE-Bund). "
         "East: new Länder without East Berlin; West: former federal territory with East Berlin. Change 2010–2024.")


def table_s7():
    ls = pd.read_csv(DER / "laender_age_bands_summary.csv")
    la = pd.read_csv(DER / "laender_age_bands.csv")
    n = la[(la.band == "65-74") & la.year.between(2022, 2024)].groupby(["land", "sex"]).deaths_n.mean()
    rows = []
    for land in sorted(LAND, key=lambda k: LAND[k]):
        r = {"Land": LAND[land] + (" (East)" if land in EAST else "")}
        for sex in ["M", "F"]:
            s = ls[(ls.land == land) & (ls.sex == sex) & (ls.band == "65-74")].iloc[0]
            small = n[(land, sex)] < 30
            r.update({f"{SEX[sex]} 2009–11": f1(s.deaths_2010), f"{SEX[sex]} 2018–20": f1(s.deaths_2019),
                      f"{SEX[sex]} 2022–24": f1(s.deaths_2023),
                      f"{SEX[sex]} change": fp(s.deaths_pct_2010_2023) + ("*" if small else ""),
                      f"{SEX[sex]} deaths/year": f"{n[(land, sex)]:.0f}"})
        k = ls[(ls.land == land) & (ls.sex == "T") & (ls.band == "65-74")].iloc[0]
        r["K74 share, all ages"] = f"{k.k74_share_deaths_2019:.2f}"
        rows.append(r)
    emit("tableS7", "Table S7. Mortality from diseases of the liver (K70–K77) at 65–74 years by Land, three-year means "
         "2009–11, 2018–20 and 2022–24", pd.DataFrame(rows),
         "Deaths per 100 000 standardised to the ESP2013 within the band; change between the 2009–11 and 2022–24 means; "
         "deaths/year = mean annual deaths 2022–24; * fewer than 30 deaths per year, change not interpreted. K74 share = "
         "K74 deaths divided by K70 plus K74 deaths, all ages and both sexes, mean of 2018–20 (GBE-Bund TOP-100 table).")


def table_s8():
    h4 = pd.read_csv(DER / "hospital_age_bands.csv")
    h3 = pd.read_csv(DER / "hospital3_bands.csv")
    h3 = h3[h3.region.isin(["DE", "East", "West"])]
    rows = []
    for icd, lab, src, col in [("K70.3", "Alcoholic cirrhosis (K70.3)", h4, "rate"), ("K74.6", "Unspecified cirrhosis (K74.6)", h4, "rate"),
                               ("K76.0", "Fatty liver (K76.0)", h4, "rate"), ("F10", "Alcohol use disorders (F10)", h3, "rate"),
                               ("C22", "Liver cancer (C22)", h3, "rate"), ("B18", "Chronic viral hepatitis (B18)", h3, "rate"),
                               ("K70-K77", "In-hospital deaths per 100 stays, K70–K77", h3, "cfr_pct")]:
        for band in BAND:
            r = {"Main diagnosis": lab, "Age (years)": BAND[band]}
            for reg in ["East", "West"]:
                s = src[(src.icd == icd) & (src.region == reg) & (src.sex == "T") & (src.band == band)].set_index("year")[col]
                r.update({f"{reg} 2010": f1(s[2010]), f"{reg} 2019": f1(s[2019]), f"{reg} 2023": f1(s[2023]),
                          f"{reg} change 2010–2019": fp(pct(s[2010], s[2019]))})
            rows.append(r)
    emit("tableS8", "Table S8. Hospital stays by main diagnosis and residence, East and West Germany, both sexes, 2010, "
         "2019 and 2023", pd.DataFrame(rows),
         "Stays per 100 000 standardised to the ESP2013 within the age band (Krankenhausdiagnosestatistik via GBE-Bund); "
         "stays are counted per admission. The last block gives in-hospital deaths per 100 stays for diseases of the liver (K70–K77).")


def table_s9():
    g = pd.read_csv(DER / "geda_alcohol_east_west.csv")
    blocks = [("Risky drinking, AUDIT-C, GEDA 2009–2012 (mean of three waves)", "risky_auditc", "2009-2012", "mean of the"),
              ("Risky intake, EHIS threshold, GEDA 2014/2015-EHIS", "risky_intake_ehis", "2014/2015", "population-weighted mean of the Länder (2015"),
              ("Heavy episodic drinking at least weekly, GEDA 2009–2012 (mean of three waves)", "binge_weekly", "2009-2012", "mean of the"),
              ("Heavy episodic drinking at least weekly, GEDA 2014/2015-EHIS", "binge_weekly", "2014/2015", "population-weighted mean of the Länder (2015")]
    rows = []
    for label, ind, year, method in blocks:
        for sex in ["M", "F"]:
            for age, alab in [("alle", "All"), ("45-64", "45–64"), ("65plus", "65 and over")]:
                s = g[(g.indicator == ind) & (g.year == year) & (g.sex == sex) & (g.age == age) & g.method.str.startswith(method)].iloc[0]
                rows.append({"Indicator and survey": label, "Sex": SEX[sex], "Age (years)": alab,
                             "Eastern Germany (%)": f1(s.east), "Western Germany (%)": f1(s.west),
                             "Difference, percentage points": f"{s.east - s.west:+.1f}"})
    emit("tableS9", "Table S9. Self-reported drinking in eastern and western Germany by sex and age band, GEDA surveys",
         pd.DataFrame(rows),
         "Eastern Germany includes Berlin in GEDA 2009–2012 (published aggregate) and excludes it in GEDA 2014/2015-EHIS "
         "(population-weighted mean of the five eastern Länder). Levels are not comparable between the two survey generations.")


if __name__ == "__main__":
    table1()
    table_s3()
    table_s5()
    table_s6()
    table_s7()
    table_s8()
    table_s9()
    (OUT / "tables.md").write_text("\n".join(md), encoding="utf-8")
    print("wrote", OUT / "tables.md")
