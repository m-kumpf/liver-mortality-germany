"""Step 18: drinking pattern by region from the GEDA surveys (Robert Koch Institute) through GBE-Bund.

Tables
  192    Alkoholkonsum (2009-2012): risky drinking (AUDIT-C), moderate drinking, never drinkers;
         regions Germany, West, Nordwest, Nordrhein-Westfalen, Mitte, Bayern, Baden-Wuerttemberg, Ost, Ost (Nord), Ost (Sued)
  193    Rauschtrinken (2009-2012): six or more drinks on one occasion at least weekly / monthly / less often / never
  26612  Alkoholkonsum (2014/2015, GEDA 2014/2015-EHIS): never drinkers, no weekly consumption, no risky intake, risky intake;
         Germany and the 16 Laender
  26613  Rauschtrinken (2014/2015): never / less than monthly / monthly / at least weekly / at least monthly

One sheet per survey year (2009, 2010, 2012; 2014/2015) x age group (all, 18-29, 30-44, 45-64, 65 and over) x sex,
education = all groups.

Outputs
  04_destatis/gbe_geda/raw/<table>_<year>_<age>_<sex>.csv   sheets as delivered (windows-1252 decoded, saved as UTF-8)
  04_destatis/gbe_geda/gbe_geda_alcohol_long.csv            thema, indicator, survey, year, age, sex, region, category, value_pct

Run from the project root:  python3 20_analysis/download_gbe_geda.py [--build]
Existing valid sheets are skipped; --build only rebuilds the long table. Standard library only.
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
OUT = ROOT / "04_destatis" / "gbe_geda"
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

TABLES = {  # thema id: (search text, indicator, survey, {D.000 code: year label}, D.355 category code)
    "192": ("Alkoholkonsum Bundesländer", "alcohol_consumption", "GEDA 2009/2010/2012",
            {"110172": "2009", "110633": "2010", "111342": "2012"}, "110301"),
    "193": ("Rauschtrinken", "binge_drinking", "GEDA 2009/2010/2012",
            {"110172": "2009", "110633": "2010", "111342": "2012"}, "110301"),
    "26612": ("Alkoholkonsum Bundesländer", "alcohol_consumption", "GEDA 2014/2015-EHIS", {"": "2014/2015"}, "110302"),
    "26613": ("Rauschtrinken", "binge_drinking", "GEDA 2014/2015-EHIS", {"": "2014/2015"}, "110302"),
}
AGES = {"1000002": "alle", "110167": "18-29", "110168": "30-44", "2573": "45-64", "1337": "65plus"}
SEXES = {"1000004": "T", "42": "M", "43": "F"}
EDU_ALL = "110156"


def _safe(url):
    return urllib.parse.quote(url, safe=":/?&=%+#")


def get(url, binary=False, _hops=0):
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
    t = get(BASE + "isgbe.startseite?p_uid=gast&p_aid=0&p_sprache=D")
    aids = [a for a in re.findall(r"p_aid=(\d+)", t) if a != "0"]
    if not aids:
        raise RuntimeError("no session id (p_aid) found on the start page")
    return aids[0]


def open_table(aid, search, thema):
    """Search result list -> information page of the table -> hidden form fields."""
    q = urllib.parse.urlencode({"p_uid": "gast", "p_aid": aid, "p_sprache": "D", "p_action": "W",
                                "p_suchstring": search, "p_methode": "1"})
    t = get(BASE + "isgbe.suche?" + q)
    links = [html.unescape(u) for u in re.findall(r'data-url="([^"]*isgbe\.information[^"]*)"', t)]
    url = next((u for u in links if f"p_thema_id={thema}" in u), None)
    if not url:
        raise RuntimeError(f"table {thema} not in the result list for '{search}'")
    url = url if "://" in url else BASE + url.lstrip("/")
    page = get(url)
    m = re.search(r'<form[^>]*name="frmData"[^>]*>.*?</form>', page, re.S)
    if not m:
        raise RuntimeError(f"information page of table {thema} without frmData form")
    hidden = dict(re.findall(r'name="(p_[a-z0-9_]+)"\s+value="([^"]*)"', m.group(0)))
    hidden.setdefault("p_uid", "gast")
    hidden.setdefault("p_aid", aid)
    hidden.setdefault("p_sprache", "D")
    return hidden


def fetch_sheet(hidden, dims):
    params = dict(hidden)
    params.update(dims)
    t = get(BASE + "!isgbe.indikatoren_set_page?" + urllib.parse.urlencode(params))
    m = re.search(r'href="([^"]*prc_download_csv\?[^"]*)"', t)
    if not m:
        raise RuntimeError("no CSV link in response")
    link = html.unescape(m.group(1))
    if link.startswith("/"):
        link = "https://www.gbe-bund.de" + link
    return get(link, binary=True).decode("windows-1252")


def sheet_ok(txt, year, age_label, sex_code):
    sex_label = {"1000004": "Alle Geschlechter", "42": "Männlich", "43": "Weiblich"}[sex_code]
    age_text = {"alle": "Alle Altersgruppen", "18-29": "18 bis unter 30", "30-44": "30 bis unter 45",
                "45-64": "45 bis unter 65", "65plus": "65 Jahre"}[age_label]
    return (f"Jahr:;{year}" in txt and f"Geschlecht:;{sex_label}" in txt and f"Alter:;{age_text}" in txt
            and "Bildung:;Alle Bildungsgruppen" in txt)


def conv(s):
    s = s.strip()
    return None if s.lower() in ("", "-", ".", "x", "...", "/") else float(s.replace(".", "").replace(",", "."))


def parse(csv_text):
    """(categories, [(region, [values])]) from a sheet: header line ';"cat1";"cat2";...' then '"region";"v";...'."""
    cats, rows = None, []
    for line in csv_text.splitlines():
        if cats is None and line.startswith(';"'):
            cats = [c.strip() for c in re.findall(r'"([^"]*)"', line)]
            continue
        if cats is not None and line.startswith('"'):
            cells = re.findall(r'"([^"]*)"', line)
            if len(cells) >= len(cats) + 1:
                rows.append((cells[0].strip(), [conv(v) for v in cells[1:len(cats) + 1]]))
    return cats or [], rows


def build():
    out = OUT / "gbe_geda_alcohol_long.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["thema", "indicator", "survey", "year", "age", "sex", "region", "category", "value_pct"])
        n = 0
        for p in sorted(RAW.glob("*.csv")):
            thema, year, age, sex = p.stem.split("_")
            year = year.replace("-", "/")
            if thema not in TABLES:
                continue
            _, indicator, survey, _, _ = TABLES[thema]
            cats, rows = parse(p.read_text(encoding="utf-8"))
            for region, vals in rows:
                for cat, v in zip(cats, vals):
                    w.writerow([thema, indicator, survey, year, age, sex, region, cat, v])
                    n += 1
    print(f"wrote {out} ({n} rows)")


def scrape():
    aid = open_session()
    for thema, (search, indicator, survey, years, cat) in TABLES.items():
        hidden = open_table(aid, search, thema)
        print(f"table {thema} ({indicator}, {survey}): indicator {hidden.get('p_indnr')}")
        for ycode, ylabel in years.items():
            for acode, alabel in AGES.items():
                for scode, slabel in SEXES.items():
                    raw = RAW / f"{thema}_{ylabel.replace('/', '-')}_{alabel}_{slabel}.csv"
                    if raw.exists() and sheet_ok(raw.read_text(encoding="utf-8"), ylabel, alabel, scode):
                        continue
                    dims = {"D.002": acode, "D.003": scode, "D.355": cat, "D.371": EDU_ALL}
                    if ycode:
                        dims["D.000"] = ycode
                    txt = None
                    for attempt in range(3):
                        try:
                            txt = fetch_sheet(hidden, dims)
                        except Exception as e:
                            print(f"   error {raw.name}: {e}")
                            txt = None
                        if txt and sheet_ok(txt, ylabel, alabel, scode):
                            break
                        time.sleep(3 + 5 * attempt)
                        aid = open_session()
                        hidden = open_table(aid, search, thema)
                    if not (txt and sheet_ok(txt, ylabel, alabel, scode)):
                        print(f"FAILED {raw.name}")
                        continue
                    raw.write_text(txt, encoding="utf-8")
                    time.sleep(0.7)
    build()


if __name__ == "__main__":
    if "--build" in sys.argv:
        build()
    else:
        scrape()
