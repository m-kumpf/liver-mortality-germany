"""Step 16: exposure series for the East/West analysis.

  obesity  Statistische Aemter des Bundes und der Laender, SDG indicator "Adipositasquote" (Mikrozensus): share of the
           population aged 18 and over with a body-mass index above 30 kg/m2, by Land, survey years 1999-2025.
           The HTML table of the indicator page is parsed; the SDG Tabellenband (XLSX) is saved as an archival copy.
  alcohol  WHO Regional Office for Europe, Health for All database (HFA-DB) API v5: recorded pure alcohol per capita
           aged 15 and over, Germany, total and by beverage (HFA_426 total, HFA_427 spirits, HFA_428 wine, HFA_429 beer).
  sieber   05_exposures/alcohol_gdr_frg_sieber1998.csv, transcribed from Sieber E, Heon V, Willich SN. Soz Praventivmed
           1998; 43: 90-99 (tables 1 and 2): the file is validated, not downloaded.

Outputs
  05_exposures/raw/                                   page, workbook and JSON responses as retrieved
  05_exposures/mikrozensus_adipositasquote_laender.csv (+ _notes.txt with the footnotes of the table)
  05_exposures/who_hfa_alcohol_germany.csv

Run from the project root:  python3 20_analysis/download_exposures.py [--offline] [--only obesity|alcohol|sieber]
--offline re-parses the saved raw files. Standard library only.
"""
import csv
import datetime as dt
import json
import pathlib
import re
import ssl
import sys
import urllib.request
from html.parser import HTMLParser

try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context()

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "05_exposures"
RAW = OUT / "raw"
RAW.mkdir(parents=True, exist_ok=True)
TODAY = dt.date.today().isoformat()
UA = {"User-Agent": "Mozilla/5.0 (python-urllib; liver-mortality-germany)"}

OBESITY_URL = ("https://www.statistikportal.de/de/nachhaltigkeit/ergebnisse/"
               "ziel-3-gesundheit-und-wohlergehen/adipositasquote")
SDG_XLSX_URL = "https://www.statistikportal.de/sites/default/files/2026-10/AK%20NE%20Nachhaltigkeitsindikatoren.xlsx"
HFA_BASE = "https://dw.euro.who.int/api/v5/measures/"
HFA_MEASURES = {"HFA_426": "pure_alcohol_total", "HFA_427": "spirits", "HFA_428": "wine", "HFA_429": "beer"}
LAENDER = ["Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen", "Hamburg", "Hessen",
           "Mecklenburg-Vorpommern", "Niedersachsen", "Nordrhein-Westfalen", "Rheinland-Pfalz", "Saarland",
           "Sachsen", "Sachsen-Anhalt", "Schleswig-Holstein", "Thüringen", "Deutschland"]


def get(url, binary=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120, context=SSL_CTX) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", errors="replace")


class _Tables(HTMLParser):
    """Collect every <table> as a list of rows of cell texts."""

    def __init__(self):
        super().__init__()
        self.tables, self._t, self._row, self._cell, self._in = [], None, None, None, False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._t = []
        elif tag == "tr" and self._t is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell, self._in = [], True

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._in:
            self._row.append(" ".join("".join(self._cell).split()))
            self._in = False
        elif tag == "tr" and self._row is not None:
            self._t.append(self._row)
            self._row = None
        elif tag == "table" and self._t is not None:
            self.tables.append(self._t)
            self._t = None

    def handle_data(self, data):
        if self._in:
            self._cell.append(data)


def parse_obesity(html):
    p = _Tables()
    p.feed(html)
    table = next((t for t in p.tables if any(r and r[0] == "Mecklenburg-Vorpommern" for r in t)), None)
    if table is None:
        raise SystemExit("obesity: no table with the Länder found in the page")
    years = None
    rows = []
    for r in table:
        if years is None and r and re.fullmatch(r"(19|20)\d\d.*", r[0]):
            years = [int(re.match(r"(\d{4})", c).group(1)) for c in r]
            flags = [re.sub(r"^\d{4}\s*", "", c) for c in r]
            continue
        if years and r and r[0] in LAENDER:
            vals = r[1:]
            if len(vals) != len(years):
                raise SystemExit(f"obesity: {r[0]} has {len(vals)} values for {len(years)} years")
            for y, fl, v in zip(years, flags, vals):
                v = v.replace(",", ".").strip()
                rows.append({"region": r[0], "year": y, "value": float(v) if v not in ("", "-", ".", "/") else "",
                             "unit": "percent of population aged 18+", "footnote": fl.strip()})
    if years is None or len(rows) != 17 * len(years):
        raise SystemExit(f"obesity: parsed {len(rows)} rows, expected {17 * (len(years) if years else 0)}")
    notes = {}
    tail = re.sub(r"<[^>]+>", "\n", html[html.rfind("</table>"):])
    for m in re.finditer(r"(?m)^\s*(\d)\)\s+([A-ZÄÖÜ].{15,800}?)\s*$", tail):
        notes.setdefault(m.group(1) + ")", " ".join(m.group(2).split()))
    return years, rows, notes


def obesity(offline):
    files = sorted(RAW.glob("statistikportal_adipositasquote_*.html"))
    if not offline:
        html = get(OBESITY_URL)
        f = RAW / f"statistikportal_adipositasquote_{TODAY}.html"
        f.write_text(html, encoding="utf-8")
        print(f"obesity: page saved -> {f.name}")
        try:
            x = get(SDG_XLSX_URL, binary=True)
            (RAW / "AK_NE_Nachhaltigkeitsindikatoren.xlsx").write_bytes(x)
        except Exception as e:
            print(f"obesity: SDG Tabellenband not downloaded ({e})")
        files = [f]
    elif not files:
        raise SystemExit("obesity: no raw page in 05_exposures/raw/")
    src = files[-1]
    years, rows, notes = parse_obesity(src.read_text(encoding="utf-8"))
    out = OUT / "mikrozensus_adipositasquote_laender.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["region", "year", "value", "unit", "footnote", "source", "raw_file"])
        w.writeheader()
        for r in rows:
            r["source"] = "Statistische Ämter des Bundes und der Länder, SDG-Indikator Adipositasquote (Mikrozensus), " + OBESITY_URL
            r["raw_file"] = src.name
            w.writerow(r)
    (OUT / "mikrozensus_adipositasquote_laender_notes.txt").write_text(
        "\n".join(f"{k} {v}" for k, v in notes.items()) + "\n", encoding="utf-8")
    print(f"obesity: {len(rows)} rows, years {years} -> {out.name}")


def alcohol(offline):
    rows = []
    for code, meas in HFA_MEASURES.items():
        f = RAW / f"whoeurope_hfa_{code}_DEU.json"
        if not offline:
            url = f"{HFA_BASE}{code}?filter=COUNTRY:DEU&output=data,metadata,notes&lang=EN"
            js = json.loads(get(url))
            f.write_text(json.dumps(js, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"alcohol: {code} saved <- {url}")
        elif not f.exists():
            raise SystemExit(f"alcohol: {f.name} missing")
        js = json.loads(f.read_text(encoding="utf-8"))
        name = js.get("short_name") or js.get("full_name") or code
        for fact in js["data"]:
            d = fact["dimensions"]
            if d.get("COUNTRY") != "DEU":
                continue
            rows.append({"measure_code": code, "measure": meas, "measure_name": name, "country": "DEU",
                         "sex": d.get("SEX", "ALL"), "year": int(d["YEAR"]),
                         "value": fact["value"]["numeric"], "unit": "litres of pure alcohol per capita aged 15+"})
    rows.sort(key=lambda r: (r["measure_code"], r["year"]))
    out = OUT / "who_hfa_alcohol_germany.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    yrs = [r["year"] for r in rows if r["measure_code"] == "HFA_426"]
    print(f"alcohol: {len(rows)} rows, HFA_426 {min(yrs)}–{max(yrs)} -> {out.name}")


def sieber():
    with open(OUT / "alcohol_gdr_frg_sieber1998.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    need = {"state", "year", "measure", "value", "unit", "source_table", "note"}
    if set(rows[0]) != need:
        raise SystemExit(f"sieber: unexpected columns {sorted(rows[0])}")
    pure = {(r["state"], int(r["year"])): float(r["value"]) for r in rows if r["measure"] == "pure_alcohol"}
    gdr = sorted(y for s, y in pure if s == "GDR")
    frg = sorted(y for s, y in pure if s == "FRG")
    assert gdr == [1955, 1960, 1965, 1970, 1975, 1980, 1985, 1986, 1987, 1988, 1989], gdr
    assert frg == [1960, 1970, 1980, 1987, 1988, 1989], frg
    for y in gdr:
        for m in ("beer", "wine_sekt", "spirits"):
            assert any(r["state"] == "GDR" and int(r["year"]) == y and r["measure"] == m for r in rows), (y, m)
    print(f"sieber: file valid; GDR pure alcohol {pure[('GDR', 1955)]} (1955) to {pure[('GDR', 1989)]} (1989) L, "
          f"FRG {pure[('FRG', 1960)]} (1960) to {pure[('FRG', 1989)]} (1989) L per inhabitant")


if __name__ == "__main__":
    args = sys.argv[1:]
    offline = "--offline" in args
    only = [args[i + 1] for i, a in enumerate(args) if a == "--only"] or ["obesity", "alcohol", "sieber"]
    if "obesity" in only:
        obesity(offline)
    if "alcohol" in only:
        alcohol(offline)
    if "sieber" in only:
        sieber()
