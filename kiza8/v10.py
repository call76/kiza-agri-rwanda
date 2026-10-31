"""v10: sourced season & inputs page, 'Today' live card API, status endpoint for the assistant."""
import datetime as dt
from flask import Blueprint, render_template, jsonify, session, request
from .core import Q, Q1, me
from . import knowledge as K, assistant as A

bp = Blueprint("v10", __name__)

def _lg(): return session.get("lang", "en") if session.get("lang") in ("rw", "fr", "en") else "en"

@bp.get("/season")
def season_page():
    s, label = K.current_season(); lg = _lg()
    months = [("Jan", "Mut", "Janv"), ("Feb", "Gas", "Févr"), ("Mar", "Wer", "Mars"), ("Apr", "Mut", "Avr"), ("May", "Gic", "Mai"), ("Jun", "Kam", "Juin"),
              ("Jul", "Nya", "Juil"), ("Aug", "Kan", "Août"), ("Sep", "Nze", "Sept"), ("Oct", "Ukw", "Oct"), ("Nov", "Ugu", "Nov"), ("Dec", "Uku", "Déc")]
    def tag(m):  # m = 1..12 -> which season colours the month
        if m in (9, 10, 11, 12, 1, 2): return "A"
        if m in (3, 4, 5, 6): return "B"
        return "C"
    cal = [dict(m=m, label=months[m - 1][0 if lg == "en" else (1 if lg == "rw" else 2)], s=tag(m), now=(m == dt.date.today().month)) for m in range(1, 13)]
    return render_template("v10/season.html", s=s, label=label, K=K, cal=cal, sub=K.SUBSIDY, out=K.OUTLOOK, lg=lg, tips=K.TIPS, ai=A.ai_enabled())

@bp.get("/api/v10/today")
def today_api():
    """Everything the 'Today' card needs, in the visitor's language. Public data only + the user's own district."""
    import rules
    u = me(); lg = _lg(); dist = (u or {}).get("district") or request.args.get("district") or "Musanze"
    if not Q1("SELECT 1 x FROM districts WHERE name=?", (dist,)): dist = "Musanze"
    s, label = K.current_season(); P = lambda en, kr, fr: kr if lg == "rw" else (fr if lg == "fr" else en)
    wx = Q("SELECT * FROM weather WHERE district=? ORDER BY day LIMIT 3", (dist,))
    w = None
    if wx:
        adv = [t for _, t in rules.weather_advice(wx)]
        w = dict(temp=wx[0]["temp"], rain_prob=wx[0]["rain_prob"], rain_mm=wx[0]["rain_mm"], advice=adv[0] if adv else "", demo=bool(wx[0].get("is_demo")), fetched=wx[0].get("fetched_at"))
    pr = Q("SELECT crop, current_price_rwf p, change_pct c, predicted_trend t, as_of FROM esoko_prices WHERE district=? ORDER BY ABS(change_pct) DESC LIMIT 3", (dist,))
    ur = next(r for r in K.SUBSIDY["rows"] if r["name"] == "Urea")
    return jsonify(
        district=dist, season=label, season_text=s["rwd" if lg == "rw" else ("frd" if lg == "fr" else "en")],
        outlook=K.OUTLOOK["rw" if lg == "rw" else ("fr" if lg == "fr" else "en")], weather=w, prices=pr,
        urea=P(f"Urea {ur['farmer']:,} RWF/kg after {ur['pct']}% subsidy", f"Urea {ur['farmer']:,} RWF/kg nyuma ya nkunganire ya {ur['pct']}%", f"Urée {ur['farmer']:,} RWF/kg après {ur['pct']}% de subvention"),
        t=dict(season=P("Season", "Igihembwe", "Saison"), weather=P("Weather", "Ikirere", "Météo"), prices=P("Price movers", "Ibiciro bihinduka", "Prix"), ask=P("Ask KIZA", "Baza KIZA", "Demander à KIZA"),
               more=P("Season & inputs", "Igihembwe n'ifumbire", "Saison & intrants"), none_w=P("Weather loads when the server is online.", "Ikirere kiza seriveri ifite internet.", "La météo se charge quand le serveur est en ligne."),
               none_p=P("No price data loaded yet.", "Nta makuru y'ibiciro arashyirwaho.", "Pas encore de prix."), today=P("Today in", "Uyu munsi i", "Aujourd'hui à")))

@bp.get("/api/v10/ai-status")
def ai_status():
    return jsonify(ai=A.ai_enabled(), model=A.MODEL if A.ai_enabled() else None, web=A.WEB and A.ai_enabled())
