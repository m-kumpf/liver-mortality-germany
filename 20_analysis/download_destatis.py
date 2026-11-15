"""Step 4: download the GENESIS-Online population tables into 04_destatis/.

  12411-0041  mid-year population of Germany by single year of age, sex and nationality
  12411-0042  mid-year population by Land, sex and nationality

A GENESIS-Online API token is required (free registration at https://genesis.destatis.de/datenbank/online):
set the environment variable GENESIS_TOKEN or write the token to 00_meta/.genesis_token.

Run from the project root:  python3 20_analysis/download_destatis.py
Standard library only.
"""
import io
import json
import os
import pathlib
import ssl
import sys
import time
import urllib.parse
import urllib.request
import zipfile

try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context()

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "04_destatis"
OUT.mkdir(exist_ok=True)
BASE = "https://genesis.destatis.de/genesisWS/rest/2020/"
TABLES = {
    "12411-0041": "durchschnittsbevoelkerung_de_jahre_nationalitaet_geschlecht_altersjahre",
    "12411-0042": "durchschnittsbevoelkerung_bundeslaender_jahre_nationalitaet_geschlecht",
}
START_YEAR = 1998


def token():
    t = os.environ.get("GENESIS_TOKEN")
    f = ROOT / "00_meta" / ".genesis_token"
    if not t and f.exists():
        t = f.read_text().strip()
    if not t:
        sys.exit("No API token: set GENESIS_TOKEN or create 00_meta/.genesis_token")
    return t


def call(method, **params):
    data = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
    req = urllib.request.Request(BASE + method, data=data, method="POST",
                                 headers={"username": token(), "password": "",
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=300, context=SSL_CTX) as r:
        return r.read()


def unzip_if_needed(raw):
    """GENESIS delivers ffcsv files as a ZIP even with compress=false."""
    if raw[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(raw))
        raw = z.read(z.namelist()[0])
    return raw.decode("utf-8-sig").encode("utf-8")


def fetch_tablefile(code, startyear=None, endyear=None):
    params = dict(name=code, area="all", compress="false", transpose="false", format="ffcsv", language="de")
    if startyear:
        params["startyear"] = startyear
    if endyear:
        params["endyear"] = endyear
    raw = call("data/tablefile", **params)
    if raw[:200].decode("utf-8", "replace").lstrip().startswith("{"):
        return None, json.loads(raw)
    return unzip_if_needed(raw), None


def download(code, stem, startyear, chunk=5):
    """Download one table as flat CSV; tables too large for one request (status code 98) are fetched in year chunks."""
    raw, status = fetch_tablefile(code, startyear)
    if status is not None and status.get("Status", {}).get("Code") == 98:
        parts = []
        for a in range(startyear, 2026, chunk):
            r, st = fetch_tablefile(code, a, a + chunk - 1)
            if r is None:
                print(f"   {a}-{a + chunk - 1}: {st.get('Status')}")
                continue
            lines = r.decode("utf-8").splitlines(keepends=True)
            parts.append("".join(lines if not parts else lines[1:]))
            time.sleep(1)
        if not parts:
            return False
        raw = "".join(parts).encode("utf-8")
    elif status is not None:
        print(f"{code}: {status.get('Status')}")
        return False
    path = OUT / f"{code}_{stem}.csv"
    path.write_bytes(raw)
    print(f"{code}: {len(raw) // 1024} kB -> {path.name}")
    return True


if __name__ == "__main__":
    for code, stem in TABLES.items():
        download(code, stem, START_YEAR)
        time.sleep(2)
