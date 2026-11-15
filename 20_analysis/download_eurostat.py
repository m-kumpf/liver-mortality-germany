"""Step 1: download the Eurostat causes-of-death and population tables into 02_eurostat/.

Run from the project root:  python3 20_analysis/download_eurostat.py
Standard library only. The JSON-stat responses are kept in 02_eurostat/raw_json/.
"""
import csv
import itertools
import json
import pathlib
import ssl
import time
import urllib.request

try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context()

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "02_eurostat"
RAW = OUT / "raw_json"
RAW.mkdir(parents=True, exist_ok=True)
BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"


def fetch(dataset, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{BASE}{dataset}?format=JSON&lang=EN&{q}"
    with urllib.request.urlopen(url, timeout=120, context=SSL_CTX) as r:
        return json.load(r), url


def tidy(js):
    """Flatten a JSON-stat response (row-major, last dimension varies fastest)."""
    ids = js["id"]
    size = js["size"]
    cats = [list(js["dimension"][d]["category"]["index"].keys()) for d in ids]
    strides = list(itertools.accumulate([1] + size[::-1][:-1], lambda a, b: a * b))[::-1]
    rows = []
    for k, v in js["value"].items():
        i = int(k)
        rec = {}
        for d, s, c in zip(ids, strides, cats):
            rec[d] = c[i // s]
            i = i % s
        rec["value"] = v
        rows.append(rec)
    return ids + ["value"], rows


def save(dataset, name, **params):
    js, url = fetch(dataset, **params)
    (RAW / f"{name}.json").write_text(json.dumps(js))
    cols, rows = tidy(js)
    with open(OUT / f"{name}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"{name}: {len(rows)} rows  <- {url}")
    time.sleep(1.5)


if __name__ == "__main__":
    # age-standardised death rates (ESP2013), country level, by sex
    for icd in ["K70_K73_K74", "K72-K75", "C22", "B15-B19_B942", "B180-B182", "F10"]:
        for sex in ["T", "M", "F"]:
            save("hlth_cd_asdr2", f"hlth_cd_asdr2_{icd.replace('-', '_')}_{sex}",
                 unit="RT", sex=sex, age="TOTAL", icd10=icd, geoLevel="country")
    # deaths by age group (residents) and age-specific crude rates, chronic liver disease
    for sex in ["T", "M", "F"]:
        save("hlth_cd_aro", f"hlth_cd_aro_K70_K73_K74_{sex}",
             unit="NR", sex=sex, icd10="K70_K73_K74", resid="TOT_IN", geoLevel="country")
    for sex in ["T", "M", "F"]:
        save("hlth_cd_acdr2", f"hlth_cd_acdr2_K70_K73_K74_{sex}",
             unit="RT", sex=sex, icd10="K70_K73_K74", geoLevel="country")
    # population on 1 January by single year of age (denominators for the own standardisation)
    for sex in ["T", "M", "F"]:
        save("demo_pjan", f"demo_pjan_{sex}", sex=sex, geoLevel="country", sinceTimePeriod="2010")
