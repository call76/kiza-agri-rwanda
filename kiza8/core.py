"""Shared helpers for the v8 layer: DB access (same per-request connection as v7), auth decorator, i18n, audit, tokens."""
import os, re, json, hashlib, secrets, datetime as dt
from functools import wraps
from flask import g, session, request, abort, redirect, flash
import db

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOADS_PRIVATE = os.environ.get("KIZA_PRIVATE_UPLOADS", os.path.join(os.path.dirname(BASE), "uploads", "private"))

def _c():
    if "db" not in g: g.db = db.conn()
    return g.db
def Q(sql, a=()): return [dict(r) for r in _c().execute(sql, a).fetchall()]
def Q1(sql, a=()): r = _c().execute(sql, a).fetchone(); return dict(r) if r else None
def X(sql, a=()): cur = _c().execute(sql, a); _c().commit(); return cur.lastrowid

def utcnow(): return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
def ts(d=None): return (d or utcnow()).strftime("%Y-%m-%d %H:%M:%S")
def today(): return str(dt.date.today())

def me():
    return Q1("SELECT * FROM users WHERE id=?", (session["uid"],)) if session.get("uid") else None

def need(*roles):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            u = me()
            if not u or u["status"] != "active": session.clear(); return redirect("/login")
            if roles and u["role"] not in roles: abort(403)
            g.user = u; return f(*a, **k)
        return w
    return deco

def audit(action, detail="", uid=None):
    """Audit trail. NEVER pass passwords/tokens in `detail`."""
    X("INSERT INTO audit_logs(user_id,action,detail,ip) VALUES(?,?,?,?)", (uid or session.get("uid"), action, str(detail)[:500], request.remote_addr if request else None))

def notify(uid, kind, msg, link="/notifications"):
    X("INSERT INTO notifications(user_id,kind,message,link) VALUES(?,?,?,?)", (uid, kind, msg, link))

def sha(t): return hashlib.sha256(t.encode()).hexdigest()

# ---------- i18n: central catalog (en.json / rw.json). fr falls back to en for v8 keys. ----------
_CAT = {}
def catalog(lang):
    if lang not in _CAT:
        p = os.path.join(BASE, "i18n", f"{lang}.json")
        _CAT[lang] = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    return _CAT[lang]
def reload_catalogs(): _CAT.clear()
MISSING = set()
def T(key, **kw):
    lg = session.get("lang", "en") if session else "en"
    s = catalog(lg).get(key) or catalog("en").get(key)
    if s is None: MISSING.add(key); s = key
    return s.format(**kw) if kw else s
def Tl(key, lang, **kw):
    """Translate for a given language without a request (SMS / email / jobs)."""
    s = catalog(lang).get(key) or catalog("en").get(key) or key
    return s.format(**kw) if kw else s

def rwf(v):
    return "–" if v is None else f"{v:,.0f} RWF"
def num_fmt(v, d=0):
    return "–" if v is None else (f"{v:,.{d}f}")
def local_time(s):
    """UTC 'YYYY-MM-DD HH:MM:SS' -> Rwanda local (CAT, UTC+2)."""
    try: return (dt.datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S") + dt.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
    except Exception: return s or ""

def fnum(name, lo=None, hi=None, opt=False, default=None):
    try:
        v = float(request.form.get(name, "")); assert (lo is None or v >= lo) and (hi is None or v <= hi); return v
    except Exception:
        if opt: return None
        if default is not None: return default
        raise ValueError(name)
