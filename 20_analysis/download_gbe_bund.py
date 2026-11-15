"""Step 5: retrieve the GBE-Bund table "Sterbefaelle, Sterbeziffer (altersstandardisiert), haeufigste Todesursachen
(ab 1998)" (indicator 517, Todesursachenstatistik) with the 100 most frequent three-character causes, ESP2013.

One sheet per year (1998-2024) x region (Germany, 16 Laender, former federal territory with East Berlin, new Laender
without East Berlin) x sex for all ages, plus the age groups under 65 and 65 and over for Germany and the two
East/West aggregates.

Outputs
  04_destatis/gbe_bund/raw/517_<year>_<region>_<sex>_<age>.csv   sheets as delivered (windows-1252 decoded, saved as UTF-8)
  04_destatis/gbe_bund/gbe517_top100_esp2013_long.csv             year, region_code, region, sex, age, rank, icd3, label, sdr_esp2013, deaths

Run from the project root:  python3 20_analysis/download_gbe_bund.py [--build]
Existing valid sheets are skipped, so an interrupted run can be resumed; --build only rebuilds the long table.
Standard library only; one request about every 0.7 s.
"""
import csv
import html
import http.cookiejar
import pathlib
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "04_destatis" / "gbe_bund"
RAW = OUT / "raw"
RAW.mkdir(parents=True, exist_ok=True)
BASE = "https://www.gbe-bund.de/gbe/"
try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CTX = ssl.create_default_context()
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), urllib.request.HTTPSHandler(context=CTX))
opener.addheaders = [("User-Agent", "Mozilla/5.0 (python-urllib; liver-mortality-germany)")]

YEARS = {y: 3720 + (y - 1998) for y in range(1998, 2025)}
REGIONS = {"1000001": "Deutschland", "12": "Baden-Württemberg", "13": "Bayern", "15": "Berlin", "16": "Brandenburg",
           "8": "Bremen", "6": "Hamburg", "10": "Hessen", "17": "Mecklenburg-Vorpommern", "7": "Niedersachsen",
           "9": "Nordrhein-Westfalen", "11": "Rheinland-Pfalz", "14": "Saarland", "18": "Sachsen", "19": "Sachsen-Anhalt",
           "5": "Schleswig-Holstein", "20": "Thüringen", "4357": "Früheres Bundesgebiet und Berlin-Ost",
           "4358": "Neue Länder ohne Berlin-Ost"}
AGGREGATES = ["1000001", "4357", "4358"]
SEXES = {"1000004": "T", "42": "M", "43": "F"}
AGES = {"10040": "alle", "10041": "u65", "10042": "65plus"}
TOP100, ESP2013, SACH = "9994", "50961", "10102"
THEMA = "p_thema_id=219&p_thema_id2=3600&p_thema_id3=3800&p_thema_id4=3900"


def _safe(url):
    return urllib.parse.quote(url, safe=":/?&=%+#")


def get(url, binary=False, _hops=0):
    """GET with retries; pages that redirect through JavaScript are followed."""
    for attempt in range(4):
        try:
            with opener.open(_safe(url), timeout=120) as r:
                data = r.read()
            if binary:
                return data
            text = data.decode("utf-8", "replace")
            m = re.search(r'location\.href\s*=\s*"([^"]+)"', text)
            if m and _hops < 3 and ("wird ausgeführt" in text or "wird aufgebaut" in text or len(text) < 20000):
                u = html.unescape(m.group(1))
                u = u if "://" in u else (BASE + u.lstrip("/") if not u.startswith("/") else "https://www.gbe-bund.de" + u)
                time.sleep(1.0)
                return get(u, binary, _hops + 1)
            return text
        except Exception as e:
            print(f"   retry {attempt + 1} after error: {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("giving up on " + url)


def open_session():
    """Open a guest session and the indicator page; return (session id, hidden form fields)."""
    t = get(BASE + "isgbe.startseite?p_uid=gast&p_aid=0&p_sprache=D")
    aids = [a for a in re.findall(r"p_aid=(\d+)", t) if a != "0"]
    if not aids:
        raise RuntimeError("no session id (p_aid) found on the start page")
    aid = aids[0]
    get(BASE + f"isgbe.themenuebersicht?p_uid=gast&p_aid={aid}&p_sprache=D&p_thema_id=3600")
    get(BASE + f"isgbe.fundstellen?p_uid=gast&p_aid={aid}&p_sprache=D&p_thema_id=3900&p_action=TRT&kategorie=TAB&aktualitaet=0&sortierung=REL")
    t = get(BASE + f"isgbe.information?p_uid=gast&p_aid={aid}&p_sprache=D&{THEMA}")
    m = re.search(r'<form[^>]*name="frmData"[^>]*>.*?</form>', t, re.S)
    if not m:
        raise RuntimeError(f"indicator page has no frmData form (session {aid})")
    hidden = dict(re.findall(r'name="(p_[a-z0-9_]+)"\s+value="([^"]*)"', m.group(0)))
    hidden.setdefault("p_uid", "gast")
    hidden.setdefault("p_aid", aid)
    hidden.setdefault("p_sprache", "D")
    return aid, hidden


def fetch_sheet(hidden, year_code, region, sex, age):
    params = dict(hidden)
    params.update({"D.100": SACH, "D.000": str(year_code), "D.001": region, "D.016": age, "D.003": sex,
                   "D.022": TOP100, "D.011": ESP2013})
    t = get(BASE + "!isgbe.indikatoren_set_page?" + urllib.parse.urlencode(params))
    m = re.search(r'href="([^"]*prc_download_csv\?[^"]*)"', t)
    if not m:
        raise RuntimeError("no CSV link in response")
    link = html.unescape(m.group(1))
    if link.startswith("/"):
        link = "https://www.gbe-bund.de" + link
    return get(link, binary=True).decode("windows-1252")


def sheet_ok(txt, year, region):
    return (f"Jahr:;{year}" in txt and f"Region:;{REGIONS[region]}" in txt and "TOP:;100" in txt
            and "Europastandardbev" in txt)


ROW = re.compile(r'^"\s*([A-Z]\d{2})\s+(.*?)";"([^"]*)";"([^"]*)";')


def conv(s):
    return None if s.strip().lower() in ("", "-", ".", "x", "...", "/") else float(s.replace(".", "").replace(",", "."))


def parse(csv_text):
    rows, rank = [], 0
    for line in csv_text.splitlines():
        m = ROW.match(line)
        if not m:
            continue
        rank += 1
        icd, label, sdr, deaths = m.groups()
        rows.append((rank, icd, label.strip(), conv(sdr), conv(deaths)))
    return rows


def build():
    long_path = OUT / "gbe517_top100_esp2013_long.csv"
    with open(long_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["year", "region_code", "region", "sex", "age", "rank", "icd3", "label", "sdr_esp2013", "deaths"])
        for p in sorted(RAW.glob("517_*.csv")):
            _, year, region, sex, age = p.stem.split("_", 4)
            txt = p.read_text(encoding="utf-8")
            if not sheet_ok(txt, int(year), region):
                continue
            for rank, icd, label, sdr, deaths in parse(txt):
                w.writerow([year, region, REGIONS[region], sex, age, rank, icd, label, sdr, deaths])
    print("wrote", long_path)


def scrape():
    aid, hidden = open_session()
    print("session", aid, "indicator", hidden.get("p_indnr"))
    jobs = [(y, c, r, s, "10040") for y, c in YEARS.items() for r in REGIONS for s in SEXES]
    jobs += [(y, c, r, s, a) for y, c in YEARS.items() for r in AGGREGATES for s in SEXES for a in ("10041", "10042")]
    done = failed = 0
    for year, code, region, sex, age in jobs:
        raw = RAW / f"517_{year}_{region}_{SEXES[sex]}_{AGES[age]}.csv"
        if raw.exists() and sheet_ok(raw.read_text(encoding="utf-8"), year, region):
            continue
        txt = None
        for attempt in range(3):
            try:
                txt = fetch_sheet(hidden, code, region, sex, age)
            except Exception as e:
                print(f"   error {year} {REGIONS[region]} {SEXES[sex]}: {e}")
                txt = None
            if txt and sheet_ok(txt, year, region):
                break
            # expired session or default sheet returned: open a new session and retry
            time.sleep(3 + 5 * attempt)
            aid, hidden = open_session()
        if not (txt and sheet_ok(txt, year, region)):
            print(f"FAILED {year} {REGIONS[region]} {SEXES[sex]} {AGES[age]}")
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
