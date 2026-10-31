"""data.gov.rw (Rwanda Data Sharing Platform) connector.
Request shape (from the platform's API-access page): header  X-API-Key: <key>  and
    GET {BASE}/assets/public/<dataset-id>/download?format=json
The key is read ONLY from the environment / the local .env file (KIZA_DATAGOV_KEY), never stored in the database or shown in full.
The base URL is admin-editable because the API page cut it off in the screenshot we worked from: use "Test connection" to confirm.
Datasets are mapped onto the platform's own tables (market prices, district production) by column name; the admin can override the mapping."""
import os, re, csv, io, json, datetime as dt
from urllib.parse import urlparse
from flask import Blueprint, render_template, request, redirect, flash, jsonify, g
from .core import Q, Q1, X, need, audit
import db

bp = Blueprint("datagov", __name__)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BASE = "https://data.gov.rw/api/v1"
KINDS = {"market_prices": "Market prices (district, crop, price, date)", "production": "Production (district, crop, year, tonnes)", "raw": "Just store / preview (no import)"}
ALIASES = {
    "district": ["district", "akarere", "admin2", "adm2name", "admin2name", "location", "districtname"],
    "market": ["market", "marketname", "market_name", "marche"],
    "crop": ["crop", "commodity", "product", "item", "cmname", "cropname", "igihingwa"],
    "price": ["price", "pricekg", "pricerwf", "priceperkg", "retail", "unitprice", "value", "igiciro"],
    "day": ["date", "day", "period", "observationdate", "pricedate", "month"],
    "year": ["year", "seasonyear", "refyear"],
    "tonnes": ["tonnes", "production", "productiontonnes", "productionmt", "tons", "quantitytonnes", "value", "umusaruro"],
}


def _env_file():
    p = os.path.join(ROOT, ".env"); out = {}
    try:
        for ln in open(p, encoding="utf-8"):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1); out[k.strip()] = v.split(" #")[0].strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def api_key():
    return os.environ.get("KIZA_DATAGOV_KEY") or _env_file().get("KIZA_DATAGOV_KEY") or ""


def mask(k):
    return ("•••• " + k[-4:]) if len(k) > 8 else ""


def migrate():
    c = db.conn()
    try:
        c.executescript("""
CREATE TABLE IF NOT EXISTS datagov_sources(id INTEGER PRIMARY KEY, label TEXT NOT NULL, dataset_id TEXT UNIQUE NOT NULL, kind TEXT NOT NULL DEFAULT 'raw', fmt TEXT DEFAULT 'json',
  mapping TEXT, last_run TEXT, last_status TEXT, last_rows INTEGER, last_msg TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS datagov_settings(k TEXT PRIMARY KEY, v TEXT);
""")
        c.commit()
    finally:
        c.close()


def base_url():
    b = os.environ.get("KIZA_DATAGOV_BASE")
    if b:
        return b.rstrip("/")
    c = db.conn()
    try:
        r = c.execute("SELECT v FROM datagov_settings WHERE k='base'").fetchone()
    finally:
        c.close()
    return ((r["v"] if r else None) or DEFAULT_BASE).rstrip("/")


def _host_ok(url):
    h = (urlparse(url).hostname or "").lower()
    return os.environ.get("KIZA_DATAGOV_ANY_HOST") == "1" or h == "data.gov.rw" or h.endswith(".data.gov.rw") or h.endswith(".gov.rw")


class DGError(Exception):
    pass


def fetch(dataset_id, fmt="json", timeout=40):
    """Download one dataset. Returns (rows:list[dict], note:str). Raises DGError with a plain-language reason."""
    import requests
    key = api_key()
    if not key:
        raise DGError("No API key. Put KIZA_DATAGOV_KEY=... in the .env file next to app.py and restart.")
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", dataset_id or ""):
        raise DGError("Dataset id must be letters, numbers, - or _.")
    url = f"{base_url()}/assets/public/{dataset_id}/download"
    if not _host_ok(url):
        raise DGError("Base URL must be on data.gov.rw.")
    try:
        r = requests.get(url, params={"format": fmt}, headers={"X-API-Key": key, "Accept": "application/json, text/csv"}, timeout=timeout)
    except requests.exceptions.RequestException as e:
        raise DGError("Could not reach data.gov.rw (" + type(e).__name__ + "). The server needs internet access.")
    if r.status_code in (401, 403):
        raise DGError(f"data.gov.rw rejected the API key (HTTP {r.status_code}). The key may be expired or not allowed for this dataset.")
    if r.status_code == 404:
        raise DGError("HTTP 404: dataset id or base URL is wrong. Copy the exact URL from the API-access page.")
    if r.status_code == 429:
        raise DGError("HTTP 429: too many requests, try again later.")
    if r.status_code >= 400:
        raise DGError(f"HTTP {r.status_code} from data.gov.rw.")
    return parse(r.text, r.headers.get("content-type", ""))


def parse(text, ctype=""):
    text = text.lstrip("﻿")
    t = text.lstrip()
    if t[:1] in "[{":
        try:
            j = json.loads(t)
        except ValueError:
            raise DGError("Response was not valid JSON.")
        rows = _find_rows(j)
        if rows is None:
            raise DGError("JSON had no list of records.")
        return rows, "json"
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise DGError("Response had no rows.")
    return rows, "csv"


def _find_rows(j):
    if isinstance(j, list):
        return [r for r in j if isinstance(r, dict)]
    if isinstance(j, dict):
        for k in ("data", "records", "results", "items", "rows", "features"):
            if isinstance(j.get(k), list):
                return [(r.get("properties", r) if isinstance(r, dict) else r) for r in j[k] if isinstance(r, dict)]
            if isinstance(j.get(k), dict):
                x = _find_rows(j[k])
                if x is not None:
                    return x
        for v in j.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    return None


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def resolve(row_keys, override=None):
    """field -> actual column name"""
    nk = {_norm(k): k for k in row_keys}; out = {}
    for f, al in ALIASES.items():
        o = (override or {}).get(f)
        if o and o in row_keys:
            out[f] = o; continue
        for a in al:
            if _norm(a) in nk:
                out[f] = nk[_norm(a)]; break
        else:   # fuzzy: a column whose name contains an alias (e.g. Retail_Price contains 'price')
            used = set(out.values())
            for a in al:
                hit = next((orig for n, orig in nk.items() if len(_norm(a)) >= 4 and _norm(a) in n and orig not in used), None)
                if hit:
                    out[f] = hit; break
    return out


def _num(v):
    s = str(v).replace(",", "").replace(" ", "").strip()
    return float(s)


def _day(v):
    s = str(v).strip()[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    if re.fullmatch(r"\d{4}-\d{2}", s):
        return s + "-15"
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    raise ValueError("bad date")


def _canon_crop(c, name):
    n = str(name).strip()
    r = c.execute("SELECT name FROM crops WHERE lower(name)=lower(?)", (n,)).fetchone()
    return r["name"] if r else None


def _canon_district(c, name):
    n = str(name).strip()
    r = c.execute("SELECT name FROM districts WHERE lower(name)=lower(?)", (n,)).fetchone()
    return r["name"] if r else None


def import_rows(kind, rows, mapping=None, label="data.gov.rw"):
    """Map and load rows into the platform tables. Returns dict(ok, bad, issues, cols)."""
    if kind == "raw" or not rows:
        return dict(ok=0, bad=0, issues=[], cols=list(rows[0].keys())[:20] if rows else [])
    cols = resolve(list(rows[0].keys()), mapping)
    need_f = ("district", "crop", "price", "day") if kind == "market_prices" else ("district", "crop", "year", "tonnes")
    miss = [f for f in need_f if f not in cols]
    if miss:
        return dict(ok=0, bad=len(rows), issues=[("columns", "could not find: " + ", ".join(miss) + ". Columns in file: " + ", ".join(list(rows[0].keys())[:14]))], cols=list(rows[0].keys())[:20])
    c = db.conn(); ok = 0; issues = []; src = (f"data.gov.rw: {label}")[:120]
    try:
        for i, r in enumerate(rows, start=1):
            try:
                d = _canon_district(c, r[cols["district"]]); cr = _canon_crop(c, r[cols["crop"]])
                if not d: raise ValueError("unknown district " + str(r[cols["district"]])[:30])
                if not cr: raise ValueError("unknown crop " + str(r[cols["crop"]])[:30])
                if kind == "market_prices":
                    p = _num(r[cols["price"]]); day = _day(r[cols["day"]])
                    if not (0 < p < 1e6): raise ValueError("price out of range")
                    mk = str(r[cols["market"]]).strip() if "market" in cols and str(r.get(cols["market"], "")).strip() else d + " market"
                    m = c.execute("SELECT id FROM markets WHERE lower(name)=lower(?)", (mk,)).fetchone()
                    if not m:
                        ll = c.execute("SELECT lat,lng FROM districts WHERE name=?", (d,)).fetchone()
                        cur = c.execute("INSERT INTO markets(name,district,lat,lng) VALUES(?,?,?,?)", (mk, d, ll["lat"], ll["lng"])); mid = cur.lastrowid
                    else:
                        mid = m["id"]
                    c.execute("INSERT INTO market_prices(market_id,crop,day,price_kg,source) VALUES(?,?,?,?,?) ON CONFLICT(market_id,crop,day) DO UPDATE SET price_kg=excluded.price_kg, source=excluded.source", (mid, cr, day, p, src))
                else:
                    y = int(float(r[cols["year"]])); t = _num(r[cols["tonnes"]])
                    if not (1990 < y <= dt.date.today().year) or t < 0: raise ValueError("year/tonnes out of range")
                    c.execute("INSERT INTO production_history(district,year,crop,tonnes,source,is_demo) VALUES(?,?,?,?,?,0) ON CONFLICT(district,year,crop) DO UPDATE SET tonnes=excluded.tonnes, source=excluded.source, is_demo=0", (d, y, cr, t, src))
                ok += 1
            except Exception as e:
                issues.append((i, str(e)[:80]))
        c.commit()
        if kind == "market_prices" and ok:
            import esoko
            esoko.refresh(c)
    finally:
        c.close()
    return dict(ok=ok, bad=len(issues), issues=issues[:12], cols=list(rows[0].keys())[:20])


def run_source(s):
    """Fetch + import one source row (dict). Updates its status columns. Never raises."""
    status, msg, n = "ok", "", 0
    try:
        rows, how = fetch(s["dataset_id"], s.get("fmt") or "json")
        mp = None
        try:
            mp = json.loads(s["mapping"]) if s.get("mapping") else None
        except ValueError:
            pass
        res = import_rows(s["kind"], rows, mp, s["label"]); n = res["ok"]
        msg = f"{len(rows)} rows downloaded ({how}); {res['ok']} loaded, {res['bad']} skipped." + (" " + "; ".join(f"row {a}: {b}" for a, b in res["issues"][:3]) if res["issues"] else "")
        if s["kind"] != "raw" and res["ok"] == 0:
            status = "warn"
    except DGError as e:
        status, msg = "error", str(e)
    except Exception as e:
        status, msg = "error", "Unexpected: " + type(e).__name__
    c = db.conn()
    try:
        c.execute("UPDATE datagov_sources SET last_run=?, last_status=?, last_rows=?, last_msg=? WHERE id=?", (dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M"), status, n, msg[:400], s["id"]))
        c.execute("INSERT INTO sync_log(kind,status,detail) VALUES('datagov',?,?)", (status, (s["label"] + ": " + msg)[:400]))
        c.commit()
    finally:
        c.close()
    return status, msg


def run_all_sources():
    """For the scheduled job: every source, only when a key is configured."""
    if not api_key():
        return 0
    c = db.conn()
    try:
        srcs = [dict(r) for r in c.execute("SELECT * FROM datagov_sources").fetchall()]
    finally:
        c.close()
    for s in srcs:
        run_source(s)
    return len(srcs)


# ------------------------------------------------------------------ admin page
@bp.route("/admin/datagov", methods=["GET", "POST"])
@need("admin", "government")
def page():
    u = g.user; can = u["role"] == "admin"
    if request.method == "POST":
        if not can:
            flash("Only the admin can change data sources.", "err"); return redirect("/admin/datagov")
        a = request.form.get("a", "")
        if a == "base":
            b = request.form.get("base", "").strip().rstrip("/")
            if not b.startswith("https://") or not _host_ok(b):
                flash("Base URL must start with https:// and be on data.gov.rw.", "err")
            else:
                X("INSERT INTO datagov_settings(k,v) VALUES('base',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (b,)); audit("datagov.base", b); flash("Base URL saved.", "ok")
        elif a == "add":
            did = request.form.get("dataset_id", "").strip(); lab = request.form.get("label", "").strip()[:80] or did; kind = request.form.get("kind", "raw"); mp = request.form.get("mapping", "").strip()
            if not re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", did) or kind not in KINDS:
                flash("Dataset id looks wrong (letters, numbers, - and _ only).", "err")
            else:
                if mp:
                    try:
                        json.loads(mp)
                    except ValueError:
                        flash("Column mapping must be JSON like {\"price\":\"Retail\"}.", "err"); return redirect("/admin/datagov")
                try:
                    X("INSERT INTO datagov_sources(label,dataset_id,kind,mapping) VALUES(?,?,?,?)", (lab, did, kind, mp or None)); audit("datagov.add", did); flash("Dataset added. Press Import now.", "ok")
                except Exception:
                    flash("That dataset id is already added.", "err")
        elif a in ("run", "test", "del"):
            s = Q1("SELECT * FROM datagov_sources WHERE id=?", (request.form.get("id", 0),))
            if s and a == "del":
                X("DELETE FROM datagov_sources WHERE id=?", (s["id"],)); audit("datagov.del", s["dataset_id"]); flash("Removed.", "ok")
            elif s and a == "run":
                st, msg = run_source(s); audit("datagov.run", s["dataset_id"] + " " + st); flash(msg, "ok" if st == "ok" else "err")
            elif s:
                try:
                    rows, how = fetch(s["dataset_id"], s.get("fmt") or "json"); cols = resolve(list(rows[0].keys())) if rows else {}
                    flash(f"Connected. {len(rows)} rows ({how}). Columns: {', '.join(list(rows[0].keys())[:12]) if rows else '-'}. Recognised: {', '.join(f'{k}={v}' for k, v in cols.items()) or 'none'}.", "ok")
                except DGError as e:
                    flash(str(e), "err")
        return redirect("/admin/datagov")
    k = api_key()
    return render_template("v11/admin_datagov.html", key_ok=bool(k), key_mask=mask(k), base=base_url(), default_base=DEFAULT_BASE, srcs=Q("SELECT * FROM datagov_sources ORDER BY id"), kinds=KINDS, can=can,
                           log=Q("SELECT * FROM sync_log WHERE kind='datagov' ORDER BY id DESC LIMIT 8"))


@bp.get("/api/v11/datagov/status")
@need("admin", "government")
def status_api():
    return jsonify(key=bool(api_key()), base=base_url(), sources=Q("SELECT label,dataset_id,kind,last_run,last_status,last_rows FROM datagov_sources"))
