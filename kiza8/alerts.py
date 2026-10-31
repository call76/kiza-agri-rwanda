"""Forecast-based weather alerts from the weather table (forecast rows: rain_mm, rain_prob, rain_7d). Rule-based on purpose: no ML is forced in.
Simulated weather rows (is_demo=1) create alerts flagged simulated and are NOT texted to farmers unless KIZA_ALERT_SIMULATED=1 (tests / demos)."""
import os, datetime as dt
import db
from . import sms
from .core import Tl, ts

HEAVY_DAY_MM = 25.0       # one-day forecast rain => heavy rain watch (indicative threshold, review with RAB/Meteo Rwanda)
HEAVY_7D_MM = 120.0
DRY_7D_MM = 8.0

def classify(rows):
    """rows: forecast days sorted by day -> list of alert dicts (kind, severity, window)."""
    out = []
    if not rows: return out
    days = [r["day"] for r in rows]; w0, w1 = days[0], days[-1]
    mx = max(rows, key=lambda r: r["rain_mm"] or 0)
    if (mx["rain_mm"] or 0) >= HEAVY_DAY_MM: out.append(dict(kind="heavy_rain", severity="warning" if mx["rain_mm"] >= 2 * HEAVY_DAY_MM else "watch", window_start=mx["day"], window_end=mx["day"], detail=f"{mx['rain_mm']:.0f} mm forecast"))
    r7 = max((r["rain_7d"] or 0) for r in rows)
    if r7 >= HEAVY_7D_MM: out.append(dict(kind="flood_risk", severity="watch", window_start=w0, window_end=w1, detail=f"{r7:.0f} mm in 7 days"))
    if r7 <= DRY_7D_MM and all((r["rain_prob"] or 0) <= 20 for r in rows): out.append(dict(kind="drought_risk", severity="watch", window_start=w0, window_end=w1, detail=f"{r7:.0f} mm in 7 days, low rain probability"))
    return out

def generate(allow_simulated=None):
    allow = allow_simulated if allow_simulated is not None else os.environ.get("KIZA_ALERT_SIMULATED") == "1"
    c = db.conn(); new = 0
    try:
        for d in c.execute("SELECT name FROM districts").fetchall():
            rows = [dict(r) for r in c.execute("SELECT * FROM weather WHERE district=? AND day>=? ORDER BY day LIMIT 3", (d[0], str(dt.date.today()))).fetchall()]
            sim = bool(rows) and any(r["is_demo"] for r in rows)
            for a in classify(rows):
                cur = c.execute("INSERT OR IGNORE INTO weather_alerts(district,kind,severity,window_start,window_end,source,is_simulated,detail) VALUES(?,?,?,?,?,?,?,?)", (d[0], a["kind"], a["severity"], a["window_start"], a["window_end"], "weather table (forecast)" if not sim else "SIMULATED weather", int(sim), a["detail"]))
                new += cur.rowcount
        c.commit()
    finally: c.close()
    return new

def notify_farmers(allow_simulated=None):
    """Queue one localized SMS per (farmer, alert). Dedupe key makes reruns safe. Opted-out users are recorded as 'blocked', never sent."""
    allow = allow_simulated if allow_simulated is not None else os.environ.get("KIZA_ALERT_SIMULATED") == "1"
    c = db.conn(); q = 0
    try:
        for a in c.execute("SELECT * FROM weather_alerts WHERE window_start>=? ORDER BY id", (str(dt.date.today()),)).fetchall():
            if a["is_simulated"] and not allow: continue
            for u in c.execute("SELECT id,phone,lang,sms_optin FROM users WHERE role='farmer' AND status='active' AND district=? AND email NOT LIKE '%@guest.kiza'", (a["district"],)).fetchall():
                lg = u["lang"] if u["lang"] in ("en", "rw") else "en"
                body = Tl("alert.sms." + a["kind"], lg, district=a["district"], day=a["window_start"], sev=Tl("alert.sev." + a["severity"], lg))
                if sms.queue(c, u, f"alert:{a['id']}:{u['id']}", body, "weather_alert"): q += 1
        c.commit()
    finally: c.close()
    return q
