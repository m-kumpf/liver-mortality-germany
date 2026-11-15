"""Shared helpers for the WHO Mortality Database steps: age-group harmonisation of WHO rows,
standard populations, direct standardisation and Eurostat mid-year populations by 21 age groups.
"""
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
META = ROOT / "00_meta" / "standard_populations"

GROUPS = ["0", "1-4"] + [f"{a}-{a+4}" for a in range(5, 95, 5)] + ["95+"]
ESP2013 = dict(zip(GROUPS, [1000, 4000, 5500, 5500, 5500, 6000, 6000, 6500, 7000, 7000, 7000, 7000, 6500, 6000,
                            5500, 5000, 4000, 2500, 1500, 800, 200]))
assert sum(ESP2013.values()) == 100_000
# WHO world standard (Ahmad et al. 2001), percent; 95-99 and 100+ pooled into 95+
WHO2000 = {"0-4": 8.86, "5-9": 8.69, "10-14": 8.60, "15-19": 8.47, "20-24": 8.22, "25-29": 7.93, "30-34": 7.61,
           "35-39": 7.15, "40-44": 6.59, "45-49": 6.04, "50-54": 5.37, "55-59": 4.55, "60-64": 3.72, "65-69": 2.96,
           "70-74": 2.21, "75-79": 1.52, "80-84": 0.91, "85-89": 0.44, "90-94": 0.15, "95+": 0.045}


def write_standard_populations():
    META.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"age_group": list(ESP2013), "weight_per_100000": list(ESP2013.values()),
                  "source": "Eurostat (2013) Revision of the European Standard Population, Annex"}
                 ).to_csv(META / "esp2013.csv", index=False)
    pd.DataFrame({"age_group": list(WHO2000), "weight_percent": list(WHO2000.values()),
                  "source": "Ahmad OB et al. (2001) Age standardization of rates: a new WHO standard. GPE Discussion Paper 31"}
                 ).to_csv(META / "who_world_2000.csv", index=False)


def _isnan(x):
    return isinstance(x, float) and np.isnan(x)


def to_groups(row, prefix, top_override=None):
    """Map the WHO age columns of one row to the 21 groups according to its age format (Frmat).

    Returns (dict group -> value, top group) or (None, None) for unsupported formats.
    top_override collapses the row to the top group of the all-cause row of the same country, year and sex.
    Death rows whose age cells sum to less than the all-ages total (cells suppressed for confidentiality,
    Germany from 2021) are rescaled proportionally to the total of known age.
    """
    f = str(row["Frmat"]).zfill(2)
    v = lambda i: row.get(f"{prefix}{i}", np.nan)
    g = {}
    if f == "00":
        top = "95+"
    elif f == "01":
        top = "90-94"
    elif f in ("02", "03"):
        top = "85-89"
    else:
        return None, None
    g["0"] = v(2)
    g["1-4"] = v(3) if f == "03" else np.nansum([v(3), v(4), v(5), v(6)])
    cols = {f"{a}-{a+4}": 7 + (a - 5) // 5 for a in range(5, 95, 5)}
    cols["95+"] = 25
    for grp, i in cols.items():
        g[grp] = v(i)
    if top_override is not None:
        top = min(top, top_override, key=GROUPS.index)
    else:
        # rows that deliver fewer groups than their format declares: last non-missing group is the top
        present = [x for x in GROUPS[2:] if not _isnan(g[x])]
        if present and GROUPS.index(present[-1]) < GROUPS.index(top):
            top = present[-1]
    t = GROUPS.index(top)
    g[top] = np.nansum([g[x] for x in GROUPS[t:]])
    for x in GROUPS[:t]:
        if _isnan(g[x]):
            g[x] = 0.0
    for x in GROUPS[t + 1:]:
        g[x] = np.nan
    if prefix == "Deaths":
        total = row.get("Deaths1", np.nan)
        unk = row.get("Deaths26", np.nan)
        unk = 0.0 if (unk is None or _isnan(unk)) else float(unk)
        known = np.nansum([g[x] for x in GROUPS[:t + 1]])
        if total is not None and not _isnan(total):
            target = float(total) - unk
            if known > 0 and target - known > 0.5:
                f = target / known
                for x in GROUPS[:t + 1]:
                    g[x] = g[x] * f
    return g, top


def collapse(g, top):
    """Collapse a 21-group dict so that `top` is the open-ended last group."""
    t = GROUPS.index(top)
    out = {x: g[x] for x in GROUPS[:t]}
    out[top] = np.nansum([g[x] for x in GROUPS[t:]])
    return out


def sdr(d, p, top, std, pool_0_4=False):
    """Directly standardised rate per 100 000; standard weights above `top` are merged into it."""
    order = GROUPS[:GROUPS.index(top) + 1]
    w = dict(std)
    extra = GROUPS[GROUPS.index(top) + 1:]
    if pool_0_4:
        w = {("0-4" if k in ("0", "1-4") else k): v for k, v in w.items()}
        w["0-4"] = std.get("0-4", 0)
    w_top = sum(std.get(x, 0) for x in [top] + extra)
    keys = (["0-4"] + order[2:]) if pool_0_4 else order
    dd = dict(d)
    pp = dict(p)
    if pool_0_4:
        dd["0-4"] = dd.pop("0") + dd.pop("1-4")
        pp["0-4"] = pp.pop("0") + pp.pop("1-4")
    total_w = sum(w.get(k, 0) for k in keys[:-1]) + w_top
    r = 0.0
    for k in keys:
        wk = w_top if k == top else w.get(k, 0)
        if pp[k] and not np.isnan(pp[k]) and pp[k] > 0:
            r += dd[k] / pp[k] * wk
        elif dd[k] > 0:
            return np.nan
    return r / total_w * 100_000


def eurostat_pop():
    """Mid-year population (mean of 1 January of year t and t+1) by geo, year, sex and 21 age groups."""
    frames = []
    for sx in ["M", "F"]:
        d = pd.read_csv(ROOT / "02_eurostat" / f"demo_pjan_{sx}.csv")
        d = d[~d.age.isin(["TOTAL", "UNK"])].copy()

        def grp(a):
            if a == "Y_LT1":
                return "0"
            if a == "Y_OPEN":
                return "95+"
            n = int(a[1:])
            if n <= 4:
                return "1-4"
            if n >= 95:
                return "95+"
            lo = n // 5 * 5
            return f"{lo}-{lo+4}"

        d["grp"] = d.age.map(grp)
        d["sex"] = {"M": "1", "F": "2"}[sx]
        frames.append(d.groupby(["geo", "time", "sex", "grp"])["value"].sum().reset_index())
    e = pd.concat(frames)
    e2 = e.copy()
    e2["time"] = e2["time"] - 1
    m = e.merge(e2, on=["geo", "time", "sex", "grp"], suffixes=("", "_next"))
    m["mid"] = (m["value"] + m["value_next"]) / 2
    out = {}
    for (geo, yr, sx), sub in m.groupby(["geo", "time", "sex"]):
        g = {k: np.nan for k in GROUPS}
        g.update(dict(zip(sub.grp, sub.mid)))
        if any(np.isnan(v) for v in g.values()):
            continue
        out[(geo, int(yr), sx)] = (g, "95+")
    return out
