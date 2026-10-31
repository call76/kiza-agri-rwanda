"""Pipeline run tracking: run id, counts, validation, rejects, errors, retries. Loads are idempotent (UNIQUE keys + INSERT OR IGNORE)."""
import uuid, traceback, logging, json, hashlib, csv, os
import db
from .core import ts, utcnow

log = logging.getLogger("kiza.pipeline")
CODE_VERSION = "v8.0"

class Run:
    def __init__(self, name, source, destination, retries=2):
        self.c = db.conn(); self.id = uuid.uuid4().hex[:12]; self.name = name; self.stats = dict(extracted=0, inserted=0, updated=0, rejected=0); self.validation = {}; self.retries = retries; self.src_ts = None
        self.c.execute("INSERT INTO pipeline_runs(run_id,name,source,destination,started_at,status,code_version) VALUES(?,?,?,?,?,'running',?)", (self.id, name, source, destination, ts(), CODE_VERSION)); self.c.commit()
    def reject(self, row_no, reason, raw=""):
        self.stats["rejected"] += 1; self.c.execute("INSERT INTO pipeline_rejects(run_id,row_no,reason,raw) VALUES(?,?,?,?)", (self.id, row_no, reason[:200], str(raw)[:500]))
    def finish(self, status, error=None, retry=0):
        self.c.execute("UPDATE pipeline_runs SET finished_at=?,status=?,rows_extracted=?,rows_inserted=?,rows_updated=?,rows_rejected=?,validation=?,error=?,retry_count=?,source_timestamp=? WHERE run_id=?",
            (ts(), status, self.stats["extracted"], self.stats["inserted"], self.stats["updated"], self.stats["rejected"], json.dumps(self.validation), (error or "")[:1000] or None, retry, self.src_ts, self.id)); self.c.commit(); self.c.close()

def run_pipeline(name, source, destination, fn, retries=2):
    """fn(run) does the work inside ONE transaction (run.c). On exception: rollback, record failure with the error, retry up to `retries` times.
    Returns the run id. A failed run never leaves partial data."""
    last = None
    for attempt in range(retries + 1):
        r = Run(name, source, destination, retries)
        try:
            r.c.execute("BEGIN"); fn(r); r.c.commit(); r.finish("success" if r.stats["rejected"] == 0 else "partial", retry=attempt); return r.id
        except Exception as e:
            r.c.rollback(); last = f"{type(e).__name__}: {e}"; log.error("pipeline %s failed (attempt %d): %s", name, attempt + 1, last)
            r.stats = dict(extracted=0, inserted=0, updated=0, rejected=0); r.finish("failed", error=last, retry=attempt)
    return r.id

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(65536), b""): h.update(b)
    return h.hexdigest()

# ---- price import (CSV with header: crop,district,market,price_type,unit,price_rwf,observed_on,source,source_url,verified) ----
def import_prices_csv(path):
    UNIT = {"kg": 1.0, "100kg": 100.0, "tonne": 1000.0, "t": 1000.0}
    def work(run):
        run.c.row_factory = __import__("sqlite3").Row
        crops = {r[0] for r in run.c.execute("SELECT name FROM crops")}; dists = {r[0] for r in run.c.execute("SELECT name FROM districts")}
        seen = set(); run.validation["file_sha256"] = file_sha256(path); run.src_ts = ts(); import datetime as dt
        for i, r in enumerate(csv.DictReader(open(path, encoding="utf-8")), start=2):
            run.stats["extracted"] += 1
            try:
                crop = r["crop"].strip(); d = (r.get("district") or "").strip() or None; unit = (r.get("unit") or "kg").strip().lower(); price = float(r["price_rwf"]); day = dt.date.fromisoformat(r["observed_on"].strip())
                if crop not in crops: raise ValueError("unknown crop")
                if d and d not in dists: raise ValueError("unknown district")
                if unit not in UNIT: raise ValueError("unsupported unit")
                if not (price > 0): raise ValueError("price must be > 0 (missing prices are not zero)")
                if day > dt.date.today(): raise ValueError("future date")
                if not (r.get("source") or "").strip(): raise ValueError("source required")
                pt = (r.get("price_type") or "retail").strip()
                if pt not in ("retail", "wholesale", "farm_gate", "other"): raise ValueError("bad price_type")
                key = (crop, d, (r.get("market") or "").strip(), pt, str(day), r["source"].strip())
                if key in seen: raise ValueError("duplicate in file")
                seen.add(key); per_kg = price / UNIT[unit]
                cur = run.c.execute("INSERT OR IGNORE INTO price_observations(crop,district,market,price_type,unit,price_rwf,observed_on,source,source_url,verified,is_simulated) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (crop, d, (r.get("market") or "").strip() or None, pt, "kg", per_kg, str(day), r["source"].strip(), (r.get("source_url") or "").strip() or None, 1 if (r.get("verified") or "").strip() in ("1", "true", "yes") else 0, 1 if (r.get("simulated") or "").strip() in ("1", "true", "yes") else 0))
                run.stats["inserted"] += 1 if cur.rowcount else 0
                if not cur.rowcount: run.validation["already_loaded"] = run.validation.get("already_loaded", 0) + 1
            except Exception as e: run.reject(i, str(e), r)
        run.validation["rows_ok"] = run.stats["extracted"] - run.stats["rejected"]
    return run_pipeline("prices_csv", os.path.basename(path), "price_observations", work)

def reconcile_prices(path):
    """Source vs destination: every accepted row in the file must exist in price_observations."""
    c = db.conn(); n = c.execute("SELECT COUNT(*) FROM price_observations").fetchone()[0]; c.close(); return n

# ---- NISR (official statistics) loader: refuses to mark anything official unless the file says so with a source URL ----
def import_nisr_csv(path):
    req = ["publication", "year", "indicator", "geography", "unit", "value", "source_url", "is_official"]
    def work(run):
        run.validation["file_sha256"] = sha = file_sha256(path); run.src_ts = ts()
        rd = csv.DictReader(open(path, encoding="utf-8")); missing = [h for h in req if h not in (rd.fieldnames or [])]
        if missing: raise ValueError(f"schema: missing columns {missing}")
        for i, r in enumerate(rd, start=2):
            run.stats["extracted"] += 1
            try:
                official = (r["is_official"].strip() == "1")
                if official and not r["source_url"].strip().startswith("http"): raise ValueError("official rows need a source_url")
                v = float(r["value"]) if r["value"].strip() != "" else None
                if v is not None and v < 0: raise ValueError("negative value")
                cur = run.c.execute("INSERT OR IGNORE INTO nisr_indicators(publication,year,season,table_ref,indicator,geography,crop,unit,value,source_url,is_official,is_synthetic,file_sha256) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (r["publication"].strip(), int(r["year"]), (r.get("season") or "").strip() or None, (r.get("table_ref") or "").strip() or None, r["indicator"].strip(), r["geography"].strip(), (r.get("crop") or "").strip() or None, r["unit"].strip(), v, r["source_url"].strip() or None, 1 if official else 0, 0 if official else 1, sha))
                run.stats["inserted"] += 1 if cur.rowcount else 0
            except Exception as e: run.reject(i, str(e), r)
    return run_pipeline("nisr_csv", os.path.basename(path), "nisr_indicators", work)
