"""Price observations, freshness, baseline-first forecasting with time-based validation. No invented prices; missing != 0."""
import math, datetime as dt
import numpy as np
import db

STALE_DAYS = 45
MIN_MONTHS = 12          # below this no forecast is produced
SEASONAL_MIN = 24        # seasonal-naive needs two full yearly cycles

def backfill(c):
    """Copy v7 market_prices into price_observations (idempotent). DEMO-tagged rows are marked simulated and unverified."""
    n0 = c.execute("SELECT COUNT(*) FROM price_observations").fetchone()[0]
    c.execute("""INSERT OR IGNORE INTO price_observations(crop,district,market,price_type,unit,price_rwf,observed_on,source,verified,is_simulated)
        SELECT p.crop, m.district, m.name, 'retail', 'kg', p.price_kg, p.day, COALESCE(p.source,'unknown'), CASE WHEN p.source LIKE '%DEMO%' THEN 0 ELSE 1 END, CASE WHEN p.source LIKE '%DEMO%' THEN 1 ELSE 0 END
        FROM market_prices p JOIN markets m ON m.id=p.market_id""")
    c.commit(); return c.execute("SELECT COUNT(*) FROM price_observations").fetchone()[0] - n0

def freshness(observed_on, today=None):
    today = today or dt.date.today(); d = (today - dt.date.fromisoformat(observed_on)).days
    return d, ("fresh" if d <= 30 else "stale" if d <= STALE_DAYS else "old")

def latest(c, crop, district=None, price_type="retail"):
    """Most recent observation (district=None -> national mean of each district's latest). Returns dict or None - NEVER zero."""
    q = "SELECT * FROM price_observations WHERE crop=? AND price_type=?"; a = [crop, price_type]
    if district: q += " AND district=?"; a.append(district)
    r = c.execute(q + " ORDER BY observed_on DESC, id DESC LIMIT 1", a).fetchone()
    if not r: return None
    r = dict(r); r["age_days"], r["freshness"] = freshness(r["observed_on"]); r["usable"] = r["freshness"] != "old" and not r["is_simulated"] and bool(r["verified"])
    return r

def by_district(c, crop):
    out = []
    for d in c.execute("SELECT name, province FROM districts ORDER BY province, name").fetchall():
        o = c.execute("SELECT AVG(price_rwf) p, MAX(observed_on) day, MAX(is_simulated) sim, MIN(verified) ver, GROUP_CONCAT(DISTINCT source) src FROM price_observations WHERE crop=? AND district=? AND price_type='retail' AND observed_on=(SELECT MAX(observed_on) FROM price_observations WHERE crop=? AND district=? AND price_type='retail')", (crop, d[0], crop, d[0])).fetchone()
        if o["p"] is None: out.append(dict(district=d[0], province=d[1], price=None)); continue
        age, fr = freshness(o["day"]); out.append(dict(district=d[0], province=d[1], price=round(o["p"]), day=o["day"], age_days=age, freshness=fr, simulated=bool(o["sim"]), verified=bool(o["ver"]), source=o["src"]))
    return out

def monthly(c, crop, district=None):
    q = "SELECT substr(observed_on,1,7) m, AVG(price_rwf) p, COUNT(*) n, MAX(is_simulated) sim FROM price_observations WHERE crop=? AND price_type='retail'"; a = [crop]
    if district: q += " AND district=?"; a.append(district)
    return [dict(month=r["m"], price=r["p"], n=r["n"], simulated=bool(r["sim"])) for r in c.execute(q + " GROUP BY m ORDER BY m", a).fetchall()]

# ---------------- models (all use only data available at the forecast origin) ----------------
def _naive(h, hist): return [hist[-1]] * h
def _seasonal(h, hist):
    return [hist[len(hist) - 12 + (i % 12)] for i in range(h)] if len(hist) >= SEASONAL_MIN else None
def _trend(h, hist):
    y = np.array(hist[-12:], float); x = np.arange(len(y)); b, a = np.polyfit(x, y, 1); b *= 0.5          # damped slope
    return [max(1.0, float(a + b * (len(y) - 1) + b * k)) for k in range(1, h + 1)]
MODELS = {"naive": _naive, "seasonal_naive": _seasonal, "linear_trend_damped": _trend}

def forecast_monthly(values, horizon=3, folds=6):
    """values: chronological monthly mean prices. Rolling-origin evaluation (train strictly before each test month), compared to the naive baseline."""
    vals = [float(v) for v in values if v is not None and v > 0]
    if len(vals) < MIN_MONTHS: return dict(status="insufficient_data", reason=f"Need at least {MIN_MONTHS} monthly observations, have {len(vals)}.", n=len(vals))
    errs = {m: {k: [] for k in range(1, horizon + 1)} for m in MODELS}
    start = max(MIN_MONTHS - 3, len(vals) - folds - horizon)
    for o in range(start, len(vals) - 1):                          # origin o: train = vals[:o+1], test = following months
        hist = vals[:o + 1]
        for name, fn in MODELS.items():
            p = fn(horizon, hist) if name != "seasonal_naive" or len(hist) >= SEASONAL_MIN else None
            if p is None: continue
            for k in range(1, horizon + 1):
                if o + k < len(vals): errs[name][k].append(vals[o + k] - p[k - 1])
    mae = {}
    for m, ek in errs.items():
        allv = [abs(x) for k in ek for x in ek[k]]; mae[m] = float(np.mean(allv)) if allv else None
    cand = {m: v for m, v in mae.items() if v is not None}
    best = min(cand, key=cand.get); base = cand["naive"]
    chosen = best if cand[best] < base * 0.98 else "naive"          # adopt a complex model only if it clearly beats the baseline
    p = MODELS[chosen](horizon, vals); fc = []
    for k in range(1, horizon + 1):
        ek = errs[chosen][k]
        if len(ek) >= 3: s = float(np.std(ek, ddof=1)); lo, hi = max(0.0, p[k - 1] - 1.28 * s), p[k - 1] + 1.28 * s       # ~80% interval from validation errors
        else: lo = hi = None
        fc.append(dict(h=k, point=round(p[k - 1]), low=None if lo is None else round(lo), high=None if hi is None else round(hi)))
    return dict(status="ok", model=chosen, baseline="naive", mae={k: (round(v) if v is not None else None) for k, v in mae.items()}, beats_baseline=chosen != "naive", n=len(vals), forecast=fc,
                interval="80% empirical interval from rolling-origin validation errors (None = too few validation points)",
                note="Estimate based on past prices only. It is not a guarantee; supply, weather, fuel and policy shocks are not modelled.")

def next_months(last_month, k):
    y, m = map(int, last_month.split("-")); out = []
    for i in range(k): m += 1; y += (m - 1) // 12; m = (m - 1) % 12 + 1; out.append(f"{y}-{m:02d}")
    return out

def forecast_for(c, crop, district=None):
    ms = monthly(c, crop, district)
    f = forecast_monthly([m["price"] for m in ms])
    f["simulated_inputs"] = any(m["simulated"] for m in ms); f["history"] = ms
    if f["status"] == "ok":
        for row, mo in zip(f["forecast"], next_months(ms[-1]["month"], len(f["forecast"]))): row["month"] = mo
    return f

def chart(history, forecast, w=640, h=240, pad=36):
    """Server-side SVG geometry: history polyline, forecast polyline, interval polygon (units: RWF/kg)."""
    pts = [(m["month"], m["price"]) for m in history]; fc = forecast or []
    ys = [p for _, p in pts] + [r["high"] for r in fc if r.get("high")] + [r["low"] for r in fc if r.get("low") is not None] + [r["point"] for r in fc]
    if not pts: return None
    lo, hi = min(ys) * 0.95, max(ys) * 1.05; n = len(pts) + len(fc)
    X = lambda i: pad + (w - 2 * pad) * (i / max(1, n - 1)); Y = lambda v: h - pad - (h - 2 * pad) * ((v - lo) / ((hi - lo) or 1))
    hist = " ".join(f"{X(i):.1f},{Y(p):.1f}" for i, (_, p) in enumerate(pts))
    base = len(pts) - 1; fl = " ".join([f"{X(base):.1f},{Y(pts[-1][1]):.1f}"] + [f"{X(base + 1 + i):.1f},{Y(r['point']):.1f}" for i, r in enumerate(fc)]) if fc else ""
    band = ""
    if fc and all(r.get("low") is not None for r in fc):
        up = [f"{X(base + 1 + i):.1f},{Y(r['high']):.1f}" for i, r in enumerate(fc)]; dn = [f"{X(base + 1 + i):.1f},{Y(r['low']):.1f}" for i, r in reversed(list(enumerate(fc)))]
        band = " ".join([f"{X(base):.1f},{Y(pts[-1][1]):.1f}"] + up + dn)
    ticks = [dict(y=round(Y(v), 1), label=f"{v:,.0f}") for v in (lo, (lo + hi) / 2, hi)]
    labels = [dict(x=round(X(i), 1), t=pts[i][0][2:]) for i in range(0, len(pts), max(1, len(pts) // 6))]
    return dict(w=w, h=h, hist=hist, fc=fl, band=band, ticks=ticks, labels=labels, pad=pad)
