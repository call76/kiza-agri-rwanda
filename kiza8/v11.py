"""v11: farm health score, daily plan, profit simulator, planting calendar, live farm weather page, command-palette search.
All numbers come from the platform's own tables (farms, fields, weather, prices, crops) and the sourced facts in knowledge.py.
Nothing here invents data: a block with no data says so."""
import datetime as dt
from flask import Blueprint, render_template, jsonify, session, request
from .core import Q, Q1, me, need
from . import knowledge as K

bp = Blueprint("v11", __name__)
ALL = ("farmer", "buyer", "extension", "government", "admin")


def _lg():
    return session.get("lang", "en") if session.get("lang") in ("rw", "fr", "en") else "en"


def _P(en, rw, fr=None):
    lg = _lg()
    return rw if lg == "rw" else ((fr or en) if lg == "fr" else en)


def _month_idx(d):
    return d.year * 12 + d.month


# ---------------------------------------------------------------- farm health
def health(u):
    """Score 0-100 from real records. Returns None when the farmer has no field yet."""
    rows = Q("SELECT f.*, fa.soil_ph, fa.district fdist FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=? AND f.status!='Failed'", (u["id"],))
    if not rows:
        return None
    crops = {c["name"]: c for c in Q("SELECT * FROM crops")}
    s_code = K.current_season()[1][-1]
    comps = []

    # 1) soil pH fit
    vals = []
    for r in rows:
        c = crops.get(r["crop"]); ph = r.get("soil_ph")
        if not c or ph is None or c["ph_min"] is None:
            continue
        gap = max(c["ph_min"] - ph, ph - c["ph_max"], 0)
        vals.append(max(25, 100 - gap * 45))
    if vals:
        sc = sum(vals) / len(vals)
        comps.append(dict(key="soil", icon="🌍", label=_P("Soil fit", "Ubutaka", "Sol"), score=round(sc),
                          note=_P("Soil pH suits your crops.", "pH y'ubutaka ikwiranye n'ibihingwa byawe.", "Le pH convient.") if sc >= 80 else
                          _P("Soil pH is outside the crop's comfort range - test and consider lime/compost.", "pH y'ubutaka iri hanze y'ikwiye igihingwa - gerageza ubutaka, utekereze ku ishwagara/ifumbire y'imborera.", "pH hors plage - testez, chaulage/compost.")))

    # 2) weather risk next 3 days
    import rules
    wx = Q("SELECT * FROM weather WHERE district=? ORDER BY day LIMIT 3", (u["district"],))
    if wx:
        warns = sum(1 for k, _ in rules.weather_advice(wx) if k == "warn")
        sc = max(35, 100 - warns * 22)
        comps.append(dict(key="weather", icon="⛅", label=_P("Weather", "Ikirere", "Météo"), score=sc,
                          note=_P("No weather risk in the next 3 days.", "Nta kibazo cy'ikirere mu minsi 3 iri imbere.", "Aucun risque météo sous 3 jours.") if sc >= 90 else
                          _P("Weather warnings for the next 3 days - see Weather.", "Hari impuruza z'ikirere mu minsi 3 iri imbere.", "Alertes météo sous 3 jours.")))

    # 3) season fit for fields not yet growing
    vals = []
    for r in rows:
        c = crops.get(r["crop"])
        if c and r["status"] in ("Planned", "Prepared") and c.get("seasons"):
            vals.append(100 if s_code in c["seasons"] else 50)
    if vals:
        sc = sum(vals) / len(vals)
        comps.append(dict(key="season", icon="🗓️", label=_P("Season fit", "Igihembwe", "Saison"), score=round(sc),
                          note=_P("Your planned crops fit this season.", "Ibihingwa wateguye bijyanye n'igihembwe.", "Cultures adaptées à la saison.") if sc >= 80 else
                          _P("Some planned crops are not typical for this season.", "Bimwe mu bihingwa ntibisanzwe muri iki gihembwe.", "Certaines cultures ne sont pas de saison.")))

    # 4) LUC alignment
    al = [r["luc_status"] for r in rows if r["luc_status"] in ("aligned", "not_aligned")]
    if al:
        sc = sum(100 if x == "aligned" else 40 for x in al) / len(al)
        comps.append(dict(key="luc", icon="📍", label=_P("LUC match", "Guhuza na LUC", "LUC"), score=round(sc),
                          note=_P("Fields follow your sector's priority crop.", "Imirima ihuje n'igihingwa cy'ibanze cy'umurenge.", "Conforme à la culture prioritaire.") if sc >= 80 else
                          _P("A field is not the sector's priority crop - confirm with your agronomist.", "Umurima umwe si igihingwa cy'ibanze cy'umurenge - baza umukozi w'ubuhinzi.", "Confirmez avec l'agronome.")))

    # 5) market trend of your crops
    tr = {r["crop"]: r["predicted_trend"] for r in Q("SELECT crop, predicted_trend FROM esoko_prices WHERE district=?", (u["district"],))}
    vals = [100 if tr[r["crop"]] == "rising" else (45 if tr[r["crop"]] == "falling" else 75) for r in rows if r["crop"] in tr]
    if vals:
        sc = sum(vals) / len(vals)
        comps.append(dict(key="market", icon="📈", label=_P("Market", "Isoko", "Marché"), score=round(sc),
                          note=_P("Prices for your crops are steady or rising.", "Ibiciro by'ibihingwa byawe birahagaze cyangwa biriyongera.", "Prix stables ou en hausse.") if sc >= 75 else
                          _P("Prices for some of your crops are falling - plan storage or early sale.", "Ibiciro bimwe biragabanuka - tekereza kubika cyangwa kugurisha kare.", "Prix en baisse - stockage ou vente rapide.")))

    # 6) harvest timing
    today = dt.date.today(); vals = []
    for r in rows:
        if r["status"] in ("Planted", "Growing", "Flowering") and r.get("expected_harvest"):
            try:
                vals.append(55 if dt.date.fromisoformat(r["expected_harvest"]) < today else 100)
            except ValueError:
                pass
    if vals:
        sc = sum(vals) / len(vals)
        comps.append(dict(key="harvest", icon="🌾", label=_P("Harvest timing", "Isarura", "Récolte"), score=round(sc),
                          note=_P("Harvest dates are on schedule.", "Amatariki y'isarura ni ayo.", "Récoltes dans les temps.") if sc >= 80 else
                          _P("A field is past its expected harvest date - update its status or harvest.", "Umurima wararenze itariki y'isarura - uvugurure cyangwa usarure.", "Récolte en retard.")))

    if not comps:
        return dict(score=None, comps=[], fields=len(rows))
    w = dict(soil=.25, weather=.25, season=.15, luc=.1, market=.15, harvest=.1)
    tw = sum(w[c["key"]] for c in comps)
    score = round(sum(c["score"] * w[c["key"]] for c in comps) / tw)
    label = _P("Excellent", "Byiza cyane", "Excellent") if score >= 85 else _P("Healthy", "Birakomeye", "Sain") if score >= 70 else _P("Watch", "Reba neza", "À surveiller") if score >= 50 else _P("At risk", "Biri mu kaga", "À risque")
    return dict(score=score, label=label, comps=comps, fields=len(rows),
                ha=round(sum(r["size_ha"] for r in rows), 2))


@bp.get("/api/v11/health")
@need("farmer")
def health_api():
    from flask import g
    return jsonify(health=health(g.user))


# ---------------------------------------------------------------- daily plan
def plan(u):
    """Prioritised to-do list for today, each line with the reason (real records only)."""
    import rules
    items = []
    add = lambda lvl, ic, tx, link="": items.append(dict(level=lvl, icon=ic, text=tx, link=link))
    dist = u.get("district") or "Musanze"
    wx = Q("SELECT * FROM weather WHERE district=? ORDER BY day LIMIT 3", (dist,))
    for k, t in (rules.weather_advice(wx) if wx else [])[:2]:
        add("warn" if k == "warn" else "info", "⛅", t, "/weather")
    if u["role"] == "farmer":
        n = Q1("SELECT COUNT(*) c FROM offers o JOIN listings l ON l.id=o.listing_id WHERE l.seller_id=? AND o.status='Pending'", (u["id"],))["c"]
        if n:
            add("ok", "🤝", _P(f"{n} buyer offer(s) are waiting for your answer.", f"Ibyifuzo {n} by'abaguzi bitegereje igisubizo cyawe.", f"{n} offre(s) en attente."), "/offers")
        for f in Q("SELECT f.name, f.crop, f.expected_harvest, f.status FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=? AND f.expected_harvest IS NOT NULL AND f.status IN ('Planted','Growing','Flowering') ORDER BY f.expected_harvest LIMIT 2", (u["id"],)):
            try:
                d = (dt.date.fromisoformat(f["expected_harvest"]) - dt.date.today()).days
            except ValueError:
                continue
            add("info", "🌾", _P(f"{f['crop']} in {f['name']}: harvest in about {max(d, 0)} days - line up a buyer.", f"{f['crop']} muri {f['name']}: isarura mu minsi nka {max(d, 0)} - shaka umuguzi.", f"{f['crop']} ({f['name']}): récolte dans ~{max(d, 0)} j."), "/market")
        h = health(u)
        for c in (h or {}).get("comps", []):
            if c["score"] < 70:
                add("warn", c["icon"], c["note"], "/farms")
        mine = {f["crop"] for f in Q("SELECT f.crop FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=?", (u["id"],))}
        for r in Q("SELECT crop, predicted_trend t, change_pct c FROM esoko_prices WHERE district=? AND predicted_trend IN ('rising','falling') ORDER BY ABS(change_pct) DESC", (dist,)):
            if r["crop"] in mine:
                add("ok" if r["t"] == "rising" else "warn", "📈", _P(f"{r['crop']} price is {r['t']} ({r['c']:+.1f}%) in {dist}.", f"Igiciro cya {r['crop']} {'kiriyongera' if r['t']=='rising' else 'kiragabanuka'} ({r['c']:+.1f}%) i {dist}.", f"Prix {r['crop']} {r['t']} ({r['c']:+.1f}%)."), "/prices?crop=" + r["crop"])
                break
    if u["role"] == "extension":
        n = Q1("SELECT COUNT(*) c FROM listings WHERE verify_status='Pending' AND district=?", (dist,))["c"]
        if n:
            add("warn", "✔", _P(f"{n} harvest(s) waiting for a farm visit in {dist}.", f"Imyaka {n} itegereje gusurwa i {dist}.", f"{n} récolte(s) à visiter."), "/verify")
    ur = next(r for r in K.SUBSIDY["rows"] if r["name"] == "Urea")
    s, label = K.current_season()
    add("info", "🧪", _P(f"Season {label}: Urea costs you {ur['farmer']:,} RWF/kg after the {ur['pct']}% Nkunganire subsidy.", f"Igihembwe {label}: Urea wishyura {ur['farmer']:,} RWF/kg nyuma ya nkunganire ya {ur['pct']}%.", f"Saison {label}: urée {ur['farmer']:,} RWF/kg après {ur['pct']}%."), "/season")
    return items[:7]


@bp.get("/api/v11/plan")
@need(*ALL)
def plan_api():
    from flask import g
    return jsonify(items=plan(g.user), hello=_P("Your plan for today", "Gahunda yawe y'uyu munsi", "Votre plan du jour"))


# ---------------------------------------------------------------- search (command palette)
@bp.get("/api/v11/search")
@need(*ALL)
def search_api():
    q = (request.args.get("q") or "").strip()[:40]
    if len(q) < 2:
        return jsonify(crops=[], districts=[], listings=[])
    like = "%" + q.lower() + "%"
    crops = [dict(name=r["name"], link="/prices?crop=" + r["name"]) for r in Q("SELECT name FROM crops WHERE lower(name) LIKE ? ORDER BY name LIMIT 6", (like,))]
    ds = [dict(name=r["name"], sub=r["province"], link="/weather?district=" + r["name"]) for r in Q("SELECT name, province FROM districts WHERE lower(name) LIKE ? ORDER BY name LIMIT 5", (like,))]
    ls = [dict(name=f"{r['crop']} · {int(r['available_kg'])} kg", sub=r["district"], link="/market?crop=" + r["crop"])
          for r in Q("SELECT crop, available_kg, district FROM listings WHERE status IN ('Available','Offer Received') AND verify_status='Verified' AND (lower(crop) LIKE ? OR lower(COALESCE(village,'')) LIKE ?) ORDER BY id DESC LIMIT 5", (like, like))]
    return jsonify(crops=crops, districts=ds, listings=ls)


# ---------------------------------------------------------------- profit simulator
@bp.get("/profit")
@need("farmer", "buyer", "extension", "admin", "government")
def profit_page():
    from flask import g
    u = g.user; dist = u.get("district") or "Musanze"
    crops = Q("SELECT name, yield_t_ha, price_kg, cost_ha, cycle_days FROM crops ORDER BY name")
    live = {r["crop"]: r["current_price_rwf"] for r in Q("SELECT crop, current_price_rwf FROM esoko_prices WHERE district=?", (dist,))}
    nat = {r["crop"]: r["p"] for r in Q("SELECT crop, AVG(price_kg) p FROM market_prices m WHERE day=(SELECT MAX(day) FROM market_prices WHERE crop=m.crop) GROUP BY crop")}
    for c in crops:
        c["price_src"] = "district" if c["name"] in live else ("market" if c["name"] in nat else "baseline")
        c["price"] = round(live.get(c["name"]) or nat.get(c["name"]) or c["price_kg"] or 0)
    sub = {r["name"]: r for r in K.SUBSIDY["rows"]}
    fert = dict(
        urea=dict(retail=sub["Urea"]["retail"], farmer=sub["Urea"]["farmer"], pct=sub["Urea"]["pct"]),
        npk=dict(retail=sub["NPK 17-17-17 (Tweze)"]["retail"], farmer=sub["NPK 17-17-17 (Tweze)"]["farmer"], pct=sub["NPK 17-17-17 (Tweze)"]["pct"]),
        avg_kg_ha=K.APPLICATION_NOTE["kg_ha_2026"], season=K.SUBSIDY["season"], src=K.SUBSIDY["sources"][0])
    mine = Q("SELECT f.crop, SUM(f.size_ha) ha FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=? AND f.crop IS NOT NULL GROUP BY f.crop ORDER BY ha DESC", (u["id"],))
    return render_template("v11/profit.html", crops=crops, fert=fert, district=dist, mine=mine)


# ---------------------------------------------------------------- planting calendar
PLANT_MONTHS = {"A": (9, 10), "B": (2, 3, 4), "C": (6, 7)}   # general guidance for Rwanda's bimodal rain pattern


@bp.get("/calendar")
@need(*ALL)
def calendar_page():
    from flask import g
    u = g.user; today = dt.date.today(); s, label = K.current_season()
    crops = Q("SELECT name, seasons, cycle_days, yield_t_ha, price_kg, water_need FROM crops WHERE seasons IS NOT NULL ORDER BY name")
    trend = {r["crop"]: (r["predicted_trend"], r["change_pct"]) for r in Q("SELECT crop, predicted_trend, change_pct FROM esoko_prices WHERE district=?", (u.get("district") or "Musanze",))}
    rows = []
    for c in crops:
        cyc = int(c["cycle_days"] or 120); marks = [0] * 12; harv = [0] * 12
        for sc in (c["seasons"] or "").replace(" ", "").split(","):
            for m in PLANT_MONTHS.get(sc, ()):
                marks[m - 1] = 1
                hm = (m - 1 + round(cyc / 30.4)) % 12
                harv[hm] = 1
        now = 1 if marks[today.month - 1] else 0
        t = trend.get(c["name"])
        rows.append(dict(name=c["name"], plant=marks, harvest=harv, cycle=cyc, now=now, trend=t[0] if t else None, chg=t[1] if t else None, water=c["water_need"]))
    rows.sort(key=lambda r: (-r["now"], 0 if r["trend"] == "rising" else 1, r["cycle"]))
    mine = Q("SELECT f.name, f.crop, f.status, f.planting_date, f.expected_harvest FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=? AND f.expected_harvest IS NOT NULL ORDER BY f.expected_harvest LIMIT 8", (u["id"],)) if u["role"] == "farmer" else []
    for m in mine:
        try:
            m["days"] = (dt.date.fromisoformat(m["expected_harvest"]) - today).days
        except ValueError:
            m["days"] = None
    months = [_P(*x) for x in [("Jan", "Mut", "Janv"), ("Feb", "Gas", "Févr"), ("Mar", "Wer", "Mars"), ("Apr", "Mut", "Avr"), ("May", "Gic", "Mai"), ("Jun", "Kam", "Juin"),
                               ("Jul", "Nya", "Juil"), ("Aug", "Kan", "Août"), ("Sep", "Nze", "Sept"), ("Oct", "Ukw", "Oct"), ("Nov", "Ugu", "Nov"), ("Dec", "Uku", "Déc")]]
    return render_template("v11/calendar.html", rows=rows, months=months, cur=today.month - 1, label=label, mine=mine)


# ---------------------------------------------------------------- live farm (browser fetches Open-Meteo directly)
@bp.get("/live")
@need(*ALL)
def live_page():
    from flask import g
    u = g.user
    farms = Q("SELECT name, lat, lng, district FROM farms WHERE user_id=? AND lat IS NOT NULL AND lng IS NOT NULL", (u["id"],)) if u["role"] == "farmer" else []
    places = [dict(name=f["name"], lat=f["lat"], lng=f["lng"], kind="farm") for f in farms]
    places += [dict(name=d["name"], lat=d["lat"], lng=d["lng"], kind="district") for d in Q("SELECT name, lat, lng FROM districts ORDER BY name")]
    start = next((p for p in places if p["kind"] == "farm"), None) or next((p for p in places if p["name"] == u.get("district")), places[0] if places else dict(name="Kigali", lat=-1.95, lng=30.06))
    return render_template("v11/live.html", places=places, start=start)
