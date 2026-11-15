"""Step 2: extract the liver-related causes from the WHO Mortality Database ICD-10 files.

Reads the bulk-download ZIPs in 03_who_mdb/ (morticd10_part1 ... part6, morticd10_add, mort_pop) and keeps the
European countries and the ICD-10 codes K70-K77, B15-B19, C22, F10 and the all-cause total (AAA) from 2000 onwards.

Outputs
  10_derived/who_mdb_liver_raw.csv   one row per country, year, list, cause and sex with the WHO age columns as delivered
  10_derived/who_mdb_pop_raw.csv     the matching population rows
  10_derived/who_mdb_coverage.csv    list and age format available per country and year

Run from the project root:  python3 20_analysis/extract_who_mdb.py
"""
import io
import pathlib
import re
import zipfile

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "03_who_mdb"
OUT = ROOT / "10_derived"
OUT.mkdir(exist_ok=True)

COUNTRIES = {
    "4010": "AT", "4020": "BE", "4030": "BG", "4038": "HR", "4045": "CZ", "4050": "DK", "4055": "EE", "4070": "FI",
    "4080": "FR", "4085": "DE", "4140": "EL", "4150": "HU", "4160": "IS", "4170": "IE", "4180": "IT", "4186": "LV",
    "4188": "LT", "4190": "LU", "4200": "MT", "4210": "NL", "4220": "NO", "4230": "PL", "4240": "PT", "4270": "RO",
    "4274": "SK", "4276": "SI", "4280": "ES", "4290": "SE", "4300": "CH", "4308": "UK", "3080": "CY",
}
KEEP = re.compile(r"^(K7[0-7]|B1[5-9]|C22|F10|AAA)")
YEAR_MIN = 2000
DEATH_COLS = [f"Deaths{i}" for i in range(1, 27)]
POP_COLS = [f"Pop{i}" for i in range(1, 27)]


def read_csv_from_zip(zpath, member):
    with zipfile.ZipFile(zpath) as z:
        with z.open(member) as f:
            for chunk in pd.read_csv(f, dtype=str, chunksize=200_000, keep_default_na=False):
                yield chunk


def filter_chunk(ch):
    ch = ch[ch["Country"].isin(COUNTRIES)]
    ch = ch[ch["Year"].astype(int) >= YEAR_MIN]
    return ch[ch["Cause"].str.match(KEEP)]


def main():
    frames = []
    for part in range(1, 7):
        n = 0
        for ch in read_csv_from_zip(SRC / f"morticd10_part{part}.zip", f"Morticd10_part{part}"):
            ch = filter_chunk(ch)
            n += len(ch)
            frames.append(ch)
        print(f"part {part}: kept {n} rows", flush=True)

    # countries delivered as Excel sheets in the supplementary file (Germany from 2021, Norway)
    with zipfile.ZipFile(SRC / "morticd10_add.zip") as z:
        for name in z.namelist():
            if not name.endswith(".xlsx"):
                continue
            xl = pd.ExcelFile(io.BytesIO(z.read(name)))
            for sheet in xl.sheet_names:
                if sheet.upper().startswith("README"):
                    continue
                df = xl.parse(sheet, dtype=str).fillna("")
                if "Country" not in df.columns:
                    continue
                df = filter_chunk(df)
                df["source_file"] = name
                print(f"{name}/{sheet}: kept {len(df)} rows", flush=True)
                frames.append(df)

    raw = pd.concat(frames, ignore_index=True)
    raw["source_file"] = raw.get("source_file", pd.Series([""] * len(raw))).fillna("")
    raw.loc[raw["source_file"] == "", "source_file"] = "Morticd10_part"
    raw["iso"] = raw["Country"].map(COUNTRIES)
    for c in DEATH_COLS:
        raw[c] = pd.to_numeric(raw[c], errors="coerce")
    raw = raw.sort_values(["iso", "Year", "Cause", "Sex"]).reset_index(drop=True)
    raw.to_csv(OUT / "who_mdb_liver_raw.csv", index=False)
    print("raw rows:", len(raw))

    pops = []
    for ch in read_csv_from_zip(SRC / "mort_pop.zip", "pop"):
        pops.append(ch[ch["Country"].isin(COUNTRIES) & (ch["Year"].astype(int) >= YEAR_MIN)])
    pop = pd.concat(pops, ignore_index=True)
    pop["iso"] = pop["Country"].map(COUNTRIES)
    for c in POP_COLS:
        pop[c] = pd.to_numeric(pop[c], errors="coerce")
    pop.to_csv(OUT / "who_mdb_pop_raw.csv", index=False)
    print("pop rows:", len(pop))

    cov = (raw[(raw["Admin1"] == "") & (raw["SubDiv"] == "")]
           .groupby(["iso", "Country", "Year"])
           .agg(List=("List", lambda s: ",".join(sorted(set(s)))),
                Frmat=("Frmat", lambda s: ",".join(sorted(set(s)))),
                n_rows=("Cause", "size"),
                source=("source_file", lambda s: ",".join(sorted(set(s)))))
           .reset_index())
    cov.to_csv(OUT / "who_mdb_coverage.csv", index=False)


if __name__ == "__main__":
    main()
