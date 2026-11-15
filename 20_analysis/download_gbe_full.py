"""Retrieve GBE-Bund tables with an ICD-10 row hierarchy and five-year age groups, one sheet per year x region x sex.

  --table deaths     "Sterbefaelle, Sterbeziffern (ab 1998). Gliederungsmerkmale: Jahre, Region, Alter, Geschlecht,
                     Nationalitaet, ICD-10, Art der Standardisierung" (indicator 6, Todesursachenstatistik), 1998-2024.
                     ICD-10 at block level (K70-K77, F10-F19, B15-B19, C15-C26 ...).
  --table hospital3  "Diagnosedaten der Krankenhaeuser nach Wohnsitz (ICD-10-3-Steller, ab 2000)" (indicator 594),
                     three-character codes with stays, bed days and in-hospital deaths, 2000-2023.
  --table hospital4  "Diagnosedaten der Krankenhaeuser nach Wohnsitz (ICD10-4-Steller, ab 2000)" (indicator 703),
                     four-character codes of chapter XI (K70.0 ... K77.8), 2000-2023.

Regions: Germany and the East/West aggregates; --laender adds the 16 Laender. Sheets use nationality = all,
length of stay = all cases and the ESP2013.

Outputs
  04_destatis/gbe_full/<table>/raw/<indicator>_<year>_<region>_<sex>.csv   sheets as delivered (windows-1252 decoded, saved as UTF-8)
  04_destatis/gbe_full/<table>/gbe<indicator>_by_age_long.csv              year, region_code, region, sex, icd, label, age, measure, value

Run from the project root:  python3 20_analysis/download_gbe_full.py --table deaths|hospital3|hospital4 [--laender] [--build]
Existing valid sheets are skipped; --build only rebuilds the long table. Session mechanics are shared with download_gbe_bund.py.
"""
import csv
import html
import pathlib
import re
import sys
import time
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from download_gbe_bund import get, open_session, BASE, YEARS, REGIONS, SEXES, ROOT

ESP2013 = "50961"
TABLES = {
    "deaths": dict(indnr="6", topic2="3600", topic4="3900",
                   thema="p_thema_id=14187&p_thema_id2=3600&p_thema_id3=3800&p_thema_id4=3900",
                   years=range(1998, 2025),
                   drill=["K00-K93", "A00-B99", "F00-F99", "C00-D48", "C00-C97", "C00-C75", "C15-C26"],
                   orient={"D.000": "3", "D.001": "3", "D.002": "1", "D.003": "3", "D.004": "3", "D.946": "2",
                           "D.011": "3", "D.100": "1"},
                   sheet={"D.004": "1000006", "D.011": ESP2013},
                   check="K70-K77"),
    "hospital3": dict(indnr="594", search="Diagnosedaten der Krankenhäuser nach Wohnsitz",
                      thema="p_thema_id=9589&p_thema_id2=8500&p_thema_id3=14300&p_thema_id4=14300",
                      years=range(2000, 2024),
                      hier={"D.946_HIER": "25", "D.002_HIER": "17"},
                      drill=["A00-T98", "K00-K93", "K70-K77", "C00-D48", "C00-C97", "C00-C75", "C15-C26", "A00-B99",
                             "B15-B19", "F00-F99", "F10-F19"],
                      orient={"D.000": "3", "D.001": "3", "D.002": "1", "D.003": "3", "D.972": "3", "D.946": "2",
                              "D.011": "3", "D.100": "1"},
                      sheet={"D.972": "1000619", "D.011": ESP2013},
                      check="K70 "),
    "hospital4": dict(indnr="703", search="Diagnosedaten der Krankenhäuser nach Wohnsitz",
                      thema="p_thema_id=11778&p_thema_id2=8500&p_thema_id3=14300&p_thema_id4=14300",
                      years=range(2000, 2024),
                      hier={"D.946_HIER": "211", "D.002_HIER": "17"},
                      drill=["K00-K93", "K70-K77", "K70 ", "K71 ", "K72 ", "K73 ", "K74 ", "K75 ", "K76 ", "K77 "],
                      orient={"D.000": "3", "D.001": "3", "D.002": "1", "D.003": "3", "D.972": "3", "D.946": "2",
                              "D.011": "3", "D.100": "1"},
                      sheet={"D.972": "1000619", "D.011": ESP2013},
                      check="K70.3"),
}
TABLE = sys.argv[sys.argv.index("--table") + 1] if "--table" in sys.argv else "deaths"
CFG = TABLES[TABLE]
OUT = ROOT / "04_destatis" / "gbe_full" / TABLE
RAW = OUT / "raw"
RAW.mkdir(parents=True, exist_ok=True)


def frm_data(page):
    m = re.search(r'<form[^>]*name="frmData"[^>]*>.*?</form>', page, re.S)
    return dict(re.findall(r'name="(p_[a-z0-9_]+)"\s+value="([^"]*)"', m.group(0))) if m else {}


def info_page(aid):
    """Open the table's information page by the same navigation path as a browser; return its hidden form fields."""
    if CFG.get("search"):
        thema = re.search(r"p_thema_id=(\d+)", CFG["thema"]).group(1)
        for attempt in range(4):
            res = get(BASE + "isgbe.suche?" + urllib.parse.urlencode(
                {"p_uid": "gast", "p_aid": aid, "p_sprache": "D", "p_action": "W", "p_suchstring": CFG["search"],
                 "p_methode": "1"}))
            if f"p_thema_id={thema}&" in res or f"p_thema_id={thema}\"" in html.unescape(res):
                break
            time.sleep(3 + 3 * attempt)
    else:
        get(BASE + f"isgbe.themenuebersicht?p_uid=gast&p_aid={aid}&p_sprache=D&p_thema_id={CFG['topic2']}")
        get(BASE + f"isgbe.fundstellen?p_uid=gast&p_aid={aid}&p_sprache=D&p_thema_id={CFG['topic4']}&p_action=TRT&kategorie=TAB&aktualitaet=0&sortierung=REL")
    t = get(BASE + f"isgbe.information?p_uid=gast&p_aid={aid}&p_sprache=D&{CFG['thema']}")
    hidden = frm_data(t)
    if not hidden:
        raise RuntimeError("information page without frmData form")
    if hidden.get("p_indnr") != CFG["indnr"]:
        raise RuntimeError(f"unexpected indicator {hidden.get('p_indnr')} (expected {CFG['indnr']})")
    return hidden, t


def row_links(page):
    out = []
    for th in re.findall(r"<th[^>]*>(.*?)</th>", page, re.S):
        m = re.search(r'href="([^"]*indikatoren_set_hierlevel[^"]*p_direction=drill[^"]*)"', th)
        if m:
            out.append((re.sub(r"<[^>]+>", "", html.unescape(th)).strip(), html.unescape(m.group(1))))
    return out


def drill_rows(page):
    for prefix in CFG["drill"]:
        hit = [u for lab, u in row_links(page) if lab.startswith(prefix)]
        if not hit:
            continue
        page = get(hit[0])
        time.sleep(0.5)
    return page


def setup(_retries=3):
    """New session, table page, orientation (age groups in columns), ICD drill, newest view version."""
    aid = open_session()[0]
    try:
        hidden, page = info_page(aid)
    except RuntimeError as e:
        if _retries <= 0:
            raise
        print(f"   {e}; new session")
        time.sleep(5)
        return setup(_retries - 1)
    if CFG.get("search"):
        # a table opened from a search result list is filtered to the matching rows; restore the full hierarchy
        m = re.search(r'href="([^"]*indikatoren_reset_ind[^"]*)"', page)
        if not m:
            raise RuntimeError("no reset link on the table page")
        page = get(html.unescape(m.group(1)) if "://" in m.group(1) else BASE + html.unescape(m.group(1)).lstrip("/"))
        hidden.update(frm_data(page))
    if CFG.get("hier"):
        params = dict(hidden)
        params.update(CFG["hier"])
        page = get(BASE + "!isgbe.indikatoren_set_hierarchy?" + urllib.parse.urlencode(params))
        hidden.update(frm_data(page))
    params = dict(hidden)
    params.update(CFG["orient"])
    page = get(BASE + "!isgbe.indikatoren_set_orientation?" + urllib.parse.urlencode(params))
    hidden.update(frm_data(page))
    page = drill_rows(page)
    # every orientation or drill step creates a new view version; a stale p_version reverts the table
    vers = [int(v) for v in re.findall(r"p_version=(\d+)", page)]
    if vers:
        hidden["p_version"] = str(max(vers))
    ans = re.findall(r"p_ansnr=(\d+)", page)
    if ans:
        hidden["p_ansnr"] = max(set(ans), key=ans.count)
    print(f"session {aid}: table {TABLE} (indicator {CFG['indnr']}) ready, view version {hidden['p_version']}")
    return hidden


def fetch_sheet(hidden, year_code, region, sex):
    params = dict(hidden)
    params.update({"D.000": str(year_code), "D.001": region, "D.003": sex})
    params.update(CFG["sheet"])
    t = get(BASE + "!isgbe.indikatoren_set_page?" + urllib.parse.urlencode(params))
    m = re.search(r'href="([^"]*prc_download_csv\?[^"]*)"', t)
    if not m:
        raise RuntimeError("no CSV link in response")
    link = html.unescape(m.group(1))
    if link.startswith("/"):
        link = "https://www.gbe-bund.de" + link
    return get(link, binary=True).decode("windows-1252")


def sheet_ok(txt, year, region, sex):
    sexlab = {"T": ("Insgesamt", "Alle Geschlechter"), "M": ("Männlich",), "F": ("Weiblich",)}[sex]
    return (f"Jahr:;{year}" in txt and f":;{REGIONS[region]}" in txt and CFG["check"] in txt
            and any(f"Geschlecht:;{s}" in txt for s in sexlab))


ICD_ROW = re.compile(r'^"?\s*([A-Z]\d{2}(?:\.\d)?(?:-[A-Z]\d{2})?)\s+([^";]*)"?;(.*)$')


def parse(txt):
    """Rows = ICD code and label; columns = age group x measure from the two header lines."""
    lines = txt.splitlines()
    hdr = [i for i, l in enumerate(lines) if "Alle Altersgruppen" in l]
    if not hdr:
        return []
    h1 = lines[hdr[0]].split(";")
    h2 = lines[hdr[0] + 1].split(";") if hdr[0] + 1 < len(lines) else []
    ages, cur = [], ""
    for c in h1:
        c = c.strip().strip('"')
        if c:
            cur = c
        ages.append(cur)
    meas = [re.sub(r"\s+", " ", c.strip().strip('"')) for c in h2]
    out = []
    for l in lines[hdr[0] + 2:]:
        m = ICD_ROW.match(l)
        if not m:
            continue
        icd, label, rest = m.groups()
        for j, v in enumerate(rest.split(";")):
            col = j + 1
            if col >= len(ages) or not ages[col]:
                continue
            v = v.strip().strip('"')
            val = None if v.lower() in ("", "-", ".", "x", "...", "/") else float(v.replace(".", "").replace(",", "."))
            out.append((icd, label.strip(), ages[col], meas[col] if col < len(meas) else "", val))
    return out


def build():
    long_path = OUT / f"gbe{CFG['indnr']}_by_age_long.csv"
    n = 0
    with open(long_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["year", "region_code", "region", "sex", "icd", "label", "age", "measure", "value"])
        for p in sorted(RAW.glob(f"{CFG['indnr']}_*.csv")):
            _, year, region, sex = p.stem.split("_")
            rows = parse(p.read_text(encoding="utf-8"))
            if not rows:
                print("no rows parsed in", p.name)
                continue
            for icd, label, age, meas, val in rows:
                w.writerow([year, region, REGIONS[region], sex, icd, label, age, meas, val])
                n += 1
    print(f"wrote {long_path} ({n} rows)")


def scrape():
    regions = list(REGIONS) if "--laender" in sys.argv else ["1000001", "4357", "4358"]
    jobs = [(y, YEARS[y], r, s) for y in CFG["years"] for r in regions for s in SEXES]
    hidden = setup()
    done = failed = 0
    for year, code, region, sex in jobs:
        raw = RAW / f"{CFG['indnr']}_{year}_{region}_{SEXES[sex]}.csv"
        if raw.exists() and sheet_ok(raw.read_text(encoding="utf-8"), year, region, SEXES[sex]):
            continue
        txt = None
        for attempt in range(3):
            try:
                txt = fetch_sheet(hidden, code, region, sex)
            except Exception as e:
                print(f"   error {year} {REGIONS[region]} {SEXES[sex]}: {e}")
                txt = None
            if txt and sheet_ok(txt, year, region, SEXES[sex]):
                break
            time.sleep(3 + 5 * attempt)
            hidden = setup()
        if not (txt and sheet_ok(txt, year, region, SEXES[sex])):
            print(f"FAILED {year} {REGIONS[region]} {SEXES[sex]}")
            failed += 1
            if failed >= 10:
                sys.exit("10 consecutive failures, stopping")
            continue
        failed = 0
        raw.write_text(txt, encoding="utf-8")
        done += 1
        if done % 25 == 0:
            print(f"{done} sheets fetched", flush=True)
        time.sleep(0.7)
    build()


if __name__ == "__main__":
    if "--build" in sys.argv:
        build()
    else:
        scrape()
