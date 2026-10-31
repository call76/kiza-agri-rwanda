"""v11 care: spray planner (when to spray), spray log with pre-harvest safe dates, field care timeline, disease pressure, reminders, achievements.
Timing guidance is derived from the stored forecast (weather table) and, in the browser, the live hourly forecast. It never gives product doses:
the product label and the sector agronomist decide what and how much. Crop schedules are GENERAL guidance, flagged as such in the UI."""
import datetime as dt
from flask import Blueprint, render_template, jsonify, session, request, redirect, flash, g
from .core import Q, Q1, X, need, notify, audit
import db

bp = Blueprint("care", __name__)
PURPOSES = ("fungicide", "insecticide", "herbicide", "foliar", "other")


def _lg():
    return session.get("lang", "en") if session.get("lang") in ("rw", "fr", "en") else "en"


def P(en, rw, fr=None, lg=None):
    lg = lg or _lg()
    return rw if lg == "rw" else ((fr or en) if lg == "fr" else en)


def migrate():
    c = db.conn()
    try:
        c.executescript("""
CREATE TABLE IF NOT EXISTS spray_log(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), field_id INTEGER REFERENCES fields(id), product TEXT NOT NULL, purpose TEXT,
  applied_on TEXT NOT NULL, phi_days INTEGER DEFAULT 0, safe_harvest TEXT, note TEXT, planned INTEGER DEFAULT 0, reminded INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS ix_spray_user ON spray_log(user_id, applied_on);
CREATE TABLE IF NOT EXISTS care_done(user_id INTEGER NOT NULL, field_id INTEGER NOT NULL, kind TEXT NOT NULL, window_start TEXT NOT NULL, done_on TEXT, PRIMARY KEY(user_id,field_id,kind,window_start));
CREATE TABLE IF NOT EXISTS badges(user_id INTEGER NOT NULL, code TEXT NOT NULL, earned_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id,code));
""")
        c.commit()
    finally:
        c.close()


# ------------------------------------------------------------------ spray windows from the stored forecast
def day_window(w, nxt=None, lg=None):
    """One forecast row -> dict(level good|ok|avoid, hours, why[]). Thresholds are conventional spraying rules of thumb (drift and wash-off)."""
    rp, wind, temp = (w.get("rain_prob") or 0), (w.get("wind") or 0), (w.get("temp") or 0)
    why = []
    if rp >= 50:
        why.append(P(f"rain likely ({rp}%) - product can wash off", f"imvura irashoboka ({rp}%) - umuti ushobora gukukumbwa", f"pluie probable ({rp}%) - lessivage", lg))
    if wind > 25:
        why.append(P(f"strong wind ({wind:.0f} km/h) - spray drift", f"umuyaga mwinshi ({wind:.0f} km/h) - umuti wakwirakwira", f"vent fort ({wind:.0f} km/h) - dérive", lg))
    if rp >= 50 or wind > 25:
        return dict(level="avoid", hours=None, why=why)
    hours = P("06:00-09:00 or 16:00-18:00", "06:00-09:00 cyangwa 16:00-18:00", "06:00-09:00 ou 16:00-18:00", lg)
    level = "good"
    if rp >= 30:
        level = "ok"; why.append(P(f"some rain chance ({rp}%)", f"imvura ishobora kugwa ({rp}%)", f"risque de pluie ({rp}%)", lg))
    if wind > 15:
        level = "ok"; why.append(P(f"breezy ({wind:.0f} km/h): spray only when calm", f"umuyaga ({wind:.0f} km/h): tera umuti ari mutuze", f"venteux ({wind:.0f} km/h)", lg))
    if temp >= 28:
        level = "ok"; hours = P("06:00-09:00 only (hot day)", "06:00-09:00 gusa (umunsi ushyushye)", "06:00-09:00 seulement (chaud)", lg)
    if nxt is not None and (nxt.get("rain_prob") or 0) >= 70 and level == "good":
        why.append(P("heavy rain tomorrow: spray early so it can dry", "imvura nyinshi ejo: tera kare kugira ngo wumuke", "forte pluie demain: traitez tôt", lg))
    if not why:
        why.append(P("calm and dry", "ituze kandi humutse", "calme et sec", lg))
    return dict(level=level, hours=hours, why=why)


def windows_3day(district, lg=None):
    wx = Q("SELECT * FROM weather WHERE district=? AND day>=? ORDER BY day LIMIT 3", (district, str(dt.date.today())))
    out = []
    for i, w in enumerate(wx):
        r = day_window(w, wx[i + 1] if i + 1 < len(wx) else None, lg)
        d = dt.date.fromisoformat(w["day"])
        lab = P("Today", "Uyu munsi", "Aujourd'hui", lg) if d == dt.date.today() else P("Tomorrow", "Ejo", "Demain", lg) if d == dt.date.today() + dt.timedelta(1) else d.strftime("%a %d %b")
        out.append(dict(day=w["day"], label=lab, demo=bool(w.get("is_demo")), **r))
    return out


# ------------------------------------------------------------------ field care timeline (general guidance)
CEREAL = {"Maize", "Rice", "Wheat", "Sorghum", "Millet", "Barley"}
LEGUME = {"Beans", "Soybean", "Groundnut", "Peas", "Cowpea", "Bush beans", "Climbing beans"}
POTATO = {"Potato", "Irish potato"}
VEG = {"Tomato", "Cabbage", "Carrot", "Onion", "Chilli", "Pepper", "Eggplant", "Cauliflower", "Lettuce", "Spinach", "Amaranth", "Cucumber", "Pumpkin"}
DISEASE = {"Potato": ("Late blight", "Ibihumyo by'ibibabi (late blight)"), "Tomato": ("Blight", "Indwara y'ibibabi (blight)"), "Beans": ("Rust / leaf spot", "Ingese / ibibara ku bibabi"),
           "Maize": ("Leaf blight / rust", "Ibibara ku bibabi by'ibigori"), "Rice": ("Blast", "Blast y'umuceri"), "Wheat": ("Rust", "Ingese y'ingano")}


def _sched(crop):
    if crop in CEREAL:
        return [("weed", "🌿", (14, 21), "First weeding", "Gusukura bwa mbere"), ("topdress", "🧪", (25, 35), "Top-dress fertilizer (not before heavy rain)", "Ongeramo ifumbire (imvura nyinshi itaraba)"), ("weed", "🌿", (40, 50), "Second weeding", "Gusukura bwa kabiri")]
    if crop in LEGUME:
        return [("weed", "🌿", (14, 21), "First weeding", "Gusukura bwa mbere"), ("weed", "🌿", (35, 45), "Second weeding", "Gusukura bwa kabiri")]
    if crop in POTATO:
        return [("earth", "⛰️", (21, 28), "Weed and earth-up the ridges", "Sukura kandi ushyire ubutaka ku mutumba"), ("weed", "🌿", (40, 50), "Second weeding", "Gusukura bwa kabiri")]
    if crop in VEG:
        return [("weed", "🌿", (14, 21), "Weeding", "Gusukura"), ("topdress", "🧪", (21, 30), "Top-dress fertilizer (not before heavy rain)", "Ongeramo ifumbire (imvura nyinshi itaraba)")]
    return [("weed", "🌿", (21, 30), "Weeding", "Gusukura"), ("weed", "🌿", (60, 75), "Second weeding", "Gusukura bwa kabiri")]


def tasks_for(u, lg=None):
    today = dt.date.today(); out = []
    wx = Q("SELECT * FROM weather WHERE district=? AND day>=? ORDER BY day LIMIT 3", (u["district"], str(today)))
    calm = [w["day"] for w in wx if (w.get("rain_prob") or 0) < 40 and (w.get("wind") or 0) <= 25]
    done = {(r["field_id"], r["kind"], r["window_start"]) for r in Q("SELECT * FROM care_done WHERE user_id=?", (u["id"],))}
    for f in Q("SELECT f.*, fa.name farm FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=? AND f.status IN ('Prepared','Planted','Growing','Flowering') ORDER BY f.id", (u["id"],)):
        if not f.get("planting_date") or not f.get("crop"):
            out.append(dict(field_id=f["id"], field=f["name"], crop=f["crop"] or "-", kind="setup", icon="📅", title=P("Add the planting date to get care reminders", "Shyiraho itariki yo gutera ubone ibyibutsa", "Ajoutez la date de plantation", lg), start=None, end=None, state="info", best=None, key=None)); continue
        try:
            p = dt.date.fromisoformat(f["planting_date"])
        except ValueError:
            continue
        days = (today - p).days
        for kind, ic, (a, b), ten, trw in _sched(f["crop"]):
            s, e = p + dt.timedelta(a), p + dt.timedelta(b)
            ws = str(s)
            if (f["id"], kind, ws) in done or e < today - dt.timedelta(7) or s > today + dt.timedelta(21):
                continue
            st = "overdue" if e < today else "due" if s <= today <= e else "upcoming"
            best = None
            if kind in ("topdress", "earth") and st != "upcoming":
                best = calm[0] if calm else None
            out.append(dict(field_id=f["id"], field=f["name"], crop=f["crop"], kind=kind, icon=ic, title=P(ten, trw, ten, lg), start=str(s), end=str(e), state=st, best=best, key=ws))
        # weekly scouting
        if f["status"] in ("Planted", "Growing", "Flowering") and days >= 7:
            nxt = today + dt.timedelta((7 - days % 7) % 7)
            out.append(dict(field_id=f["id"], field=f["name"], crop=f["crop"], kind="scout", icon="🔎", title=P("Walk the field and check leaves (also underneath) for spots, holes, insects", "Genda mu murima urebe ibibabi (no munsi) ibibara, imyobo, udukoko", "Inspectez feuilles et insectes", lg), start=str(nxt), end=str(nxt), state="due" if nxt == today else "upcoming", best=None, key=None))
        if f.get("expected_harvest"):
            try:
                h = dt.date.fromisoformat(f["expected_harvest"]); d = (h - today).days
                if -3 <= d <= 14:
                    out.append(dict(field_id=f["id"], field=f["name"], crop=f["crop"], kind="harvest", icon="🌾", title=P(f"Harvest in about {max(d, 0)} days: arrange storage and a buyer", f"Isarura mu minsi nka {max(d, 0)}: tegura aho kubika n'umuguzi", f"Récolte dans ~{max(d, 0)} j", lg), start=str(h - dt.timedelta(7)), end=str(h), state="due", best=None, key=None))
            except ValueError:
                pass
    order = {"overdue": 0, "due": 1, "info": 2, "upcoming": 3}
    out.sort(key=lambda t: (order.get(t["state"], 9), t["start"] or "9"))
    return out[:14]


def pressure(u, lg=None):
    """Fungal-disease pressure for the crops in the user's fields from the stored 3-day forecast."""
    wx = Q("SELECT * FROM weather WHERE district=? AND day>=? ORDER BY day LIMIT 3", (u["district"], str(dt.date.today())))
    if not wx:
        return []
    hum = sum((w.get("humidity") or 0) for w in wx) / len(wx); rp = sum((w.get("rain_prob") or 0) for w in wx) / len(wx); t = sum((w.get("temp") or 0) for w in wx) / len(wx)
    score = (1 if hum >= 75 else 0) + (1 if rp >= 50 else 0) + (1 if 10 <= t <= 26 else 0)
    lvl = "high" if score >= 3 else "moderate" if score == 2 else "low"
    out = []
    for r in Q("SELECT DISTINCT f.crop FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=? AND f.crop IS NOT NULL AND f.status!='Failed'", (u["id"],)):
        d = DISEASE.get(r["crop"])
        if d:
            out.append(dict(crop=r["crop"], disease=d[1] if (lg or _lg()) == "rw" else d[0], level=lvl, why=P(f"avg humidity {hum:.0f}%, rain chance {rp:.0f}%, {t:.0f}°C", f"ubuhehere {hum:.0f}%, imvura {rp:.0f}%, {t:.0f}°C", f"humidité {hum:.0f}%, pluie {rp:.0f}%", lg)))
    return out


# ------------------------------------------------------------------ reminders (called by the job and lazily when the farmer opens the app)
def send_reminders(uid=None):
    c = db.conn(); n = 0
    try:
        q = "SELECT s.*, u.district udist, u.phone, u.lang, u.sms_optin, u.id uid2 FROM spray_log s JOIN users u ON u.id=s.user_id WHERE s.planned=1 AND s.reminded=0 AND s.applied_on>=? AND s.applied_on<=?"
        a = [str(dt.date.today()), str(dt.date.today() + dt.timedelta(1))]
        if uid:
            q += " AND s.user_id=?"; a.append(uid)
        for s in c.execute(q, a).fetchall():
            lg = s["lang"] if s["lang"] in ("rw", "fr", "en") else "en"
            wx = [dict(r) for r in c.execute("SELECT * FROM weather WHERE district=? AND day>=? ORDER BY day LIMIT 4", (s["udist"], s["applied_on"])).fetchall()]
            w = wx[0] if wx and wx[0]["day"] == s["applied_on"] else None
            if w:
                r = day_window(w, wx[1] if len(wx) > 1 else None, lg)
                if r["level"] == "avoid":
                    alt = next((x for x in wx[1:] if day_window(x, None, lg)["level"] != "avoid"), None)
                    msg = P(f"Spray planned {s['applied_on']} ({s['product']}): weather is NOT suitable ({'; '.join(r['why'])})." + (f" Better: {alt['day']}." if alt else ""),
                            f"Gutera umuti {s['applied_on']} ({s['product']}): ikirere NTIGIKWIYE ({'; '.join(r['why'])})." + (f" Byaba byiza: {alt['day']}." if alt else ""), None, lg)
                else:
                    msg = P(f"Spray planned {s['applied_on']} ({s['product']}): good window {r['hours']}. Follow the label.", f"Gutera umuti {s['applied_on']} ({s['product']}): igihe cyiza {r['hours']}. Kurikiza ibivugwa ku mpapuro y'umuti.", None, lg)
            else:
                msg = P(f"Reminder: spray planned {s['applied_on']} ({s['product']}). Check the wind and rain first.", f"Kwibutsa: gutera umuti {s['applied_on']} ({s['product']}). Banza urebe umuyaga n'imvura.", None, lg)
            c.execute("INSERT INTO notifications(user_id,kind,message,link) VALUES(?,?,?,?)", (s["user_id"], "spray", msg, "/care"))
            try:
                from . import sms
                sms.queue(c, {"id": s["user_id"], "phone": s["phone"], "lang": lg, "sms_optin": s["sms_optin"]}, f"spray:{s['id']}", msg[:300], "spray")
            except Exception:
                pass
            c.execute("UPDATE spray_log SET reminded=1 WHERE id=?", (s["id"],)); n += 1
        c.commit()
    finally:
        c.close()
    return n


# ------------------------------------------------------------------ rain fell -> "prepare the field" reminder
RAIN_MM = 5.0


def rain_fell(district):
    """Return the wettest forecast/observed row of yesterday or today with at least RAIN_MM, else None."""
    t = dt.date.today()
    c = db.conn()
    try:
        r = c.execute("SELECT * FROM weather WHERE district=? AND day>=? AND day<=? AND COALESCE(rain_mm,0)>=? ORDER BY rain_mm DESC LIMIT 1", (district, str(t - dt.timedelta(1)), str(t), RAIN_MM)).fetchone()
        return dict(r) if r else None
    finally:
        c.close()


def rain_message(u, w, lg):
    mm = w["rain_mm"]; c = db.conn()
    try:
        names = ", ".join(r[0] for r in c.execute("SELECT f.name FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=? AND f.status!='Failed' LIMIT 3", (u["id"],)).fetchall())
    finally:
        c.close()
    en = f"Rain fell ({mm:.0f} mm). Prepare your field{'s ' + names if names else ''}: let water drain, loosen the soil, clear weeds, and plant or top-dress while the soil is moist. Hold any spraying until leaves are dry."
    rw = f"Imvura yaguye ({mm:.0f} mm). Tegura umurima{' (' + names + ')' if names else ''}: reka amazi ave, uhinge ubutaka, ukureho ibyatsi, utere cyangwa ushyiremo ifumbire ubutaka bugitose. Ntutere umuti kugeza ibibabi byumutse."
    fr = f"Il a plu ({mm:.0f} mm). Préparez vos champs : drainez, ameublissez le sol, désherbez, semez ou fertilisez sol humide. Pas de traitement avant que les feuilles sèchent."
    return P(en, rw, fr, lg)


def send_rain_reminders(uid=None):
    """Once per farmer per day when real rain >= RAIN_MM was recorded for their district: in-app notification + SMS (consent respected)."""
    c = db.conn(); n = 0; today = str(dt.date.today())
    try:
        q = "SELECT id, district, phone, lang, sms_optin FROM users WHERE role='farmer' AND district IS NOT NULL"
        a = []
        if uid:
            q += " AND id=?"; a.append(uid)
        cache = {}
        for u in [dict(r) for r in c.execute(q, a).fetchall()]:
            if u["district"] not in cache:
                cache[u["district"]] = rain_fell(u["district"])
            w = cache[u["district"]]
            if not w or c.execute("SELECT 1 FROM notifications WHERE user_id=? AND kind='rain' AND date(created_at)=date('now')", (u["id"],)).fetchone():
                continue
            lg = u["lang"] if u["lang"] in ("rw", "fr", "en") else "en"
            msg = rain_message(u, w, lg)
            c.execute("INSERT INTO notifications(user_id,kind,message,link) VALUES(?,?,?,?)", (u["id"], "rain", msg, "/care"))
            try:
                from . import sms
                sms.queue(c, u, f"rain:{u['id']}:{today}", msg[:300], "rain")
            except Exception:
                pass
            n += 1
        c.commit()
    finally:
        c.close()
    return n


# ------------------------------------------------------------------ page + actions
@bp.get("/care")
@need("farmer")
def care_page():
    u = g.user; send_reminders(u["id"]); send_rain_reminders(u["id"]); rain = rain_fell(u["district"])
    fields = Q("SELECT f.id, f.name, f.crop, f.expected_harvest, f.planting_date, fa.name farm, fa.lat, fa.lng FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=? AND f.status!='Failed' ORDER BY f.id", (u["id"],))
    log = Q("SELECT s.*, f.name fname, f.crop, f.expected_harvest FROM spray_log s LEFT JOIN fields f ON f.id=s.field_id WHERE s.user_id=? ORDER BY s.applied_on DESC, s.id DESC LIMIT 40", (u["id"],))
    today = str(dt.date.today())
    for s in log:
        s["warn"] = bool(s["expected_harvest"] and s["safe_harvest"] and s["expected_harvest"] < s["safe_harvest"])
    planned = [s for s in log if s["planned"] and s["applied_on"] >= today][::-1]
    history = [s for s in log if not s["planned"]]
    farm = next((f for f in fields if f["lat"] is not None and f["lng"] is not None), None) or Q1("SELECT lat, lng FROM districts WHERE name=?", (u["district"],)) or {"lat": -1.95, "lng": 30.06}
    return render_template("v11/care.html", fields=fields, planned=planned, history=history, win=windows_3day(u["district"]), tasks=tasks_for(u), press=pressure(u),
                           geo={"lat": farm["lat"], "lng": farm["lng"]}, today=today, rain=rain and rain_message(u, rain, _lg()), purposes=PURPOSES)


@bp.post("/care/spray")
@need("farmer")
def spray_add():
    u = g.user; f = request.form
    try:
        prod = f.get("product", "").strip()[:80]; assert prod
        purpose = f.get("purpose") if f.get("purpose") in PURPOSES else "other"
        day = dt.date.fromisoformat(f.get("applied_on", "")); assert dt.date.today() - dt.timedelta(30) <= day <= dt.date.today() + dt.timedelta(60)
        phi = int(f.get("phi_days") or 0); assert 0 <= phi <= 120
        fid = int(f.get("field_id") or 0)
        fld = Q1("SELECT f.* FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE f.id=? AND fa.user_id=?", (fid, u["id"])) if fid else None
        assert fld
    except (AssertionError, ValueError):
        flash("Please fill product, field, a date within the next 60 days and a pre-harvest interval from the label (0-120 days).", "err"); return redirect("/care")
    planned = 1 if (f.get("mode") == "plan" and day >= dt.date.today()) else 0
    safe = day + dt.timedelta(phi)
    X("INSERT INTO spray_log(user_id,field_id,product,purpose,applied_on,phi_days,safe_harvest,note,planned) VALUES(?,?,?,?,?,?,?,?,?)", (u["id"], fid, prod, purpose, str(day), phi, str(safe), (f.get("note") or "")[:200], planned))
    audit("spray.add", f"field {fid} {day}")
    if fld.get("expected_harvest") and fld["expected_harvest"] < str(safe):
        flash(f"⚠ Harvest of {fld['crop']} is planned for {fld['expected_harvest']} but this product is only safe to harvest after {safe}. Delay the harvest or choose another product.", "err")
    else:
        flash(("Spray planned. We will remind you with the weather check." if planned else "Spray saved.") + (f" Safe to harvest from {safe}." if phi else ""), "ok")
    return redirect("/care")


@bp.post("/care/spray/<int:sid>/<act>")
@need("farmer")
def spray_act(sid, act):
    u = g.user; s = Q1("SELECT * FROM spray_log WHERE id=? AND user_id=?", (sid, u["id"]))
    if s and act == "done":
        X("UPDATE spray_log SET planned=0, applied_on=?, safe_harvest=date(?, '+'||COALESCE(phi_days,0)||' day') WHERE id=?", (str(dt.date.today()), str(dt.date.today()), sid)); flash("Marked as done.", "ok")
    elif s and act == "delete":
        X("DELETE FROM spray_log WHERE id=?", (sid,)); flash("Removed.", "ok")
    return redirect("/care")


@bp.post("/care/task/done")
@need("farmer")
def task_done():
    u = g.user
    try:
        fid = int(request.form.get("field_id")); kind = request.form.get("kind", "")[:12]; ws = dt.date.fromisoformat(request.form.get("key", "")).isoformat()
        assert Q1("SELECT 1 x FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE f.id=? AND fa.user_id=?", (fid, u["id"]))
        X("INSERT OR REPLACE INTO care_done(user_id,field_id,kind,window_start,done_on) VALUES(?,?,?,?,?)", (u["id"], fid, kind, ws, str(dt.date.today()))); flash("Done! ✅", "ok")
    except Exception:
        pass
    return redirect("/care")


@bp.get("/api/v11/care/summary")
@need("farmer")
def summary_api():
    u = g.user; send_reminders(u["id"]); t = tasks_for(u); w = windows_3day(u["district"])
    return jsonify(tasks_due=sum(1 for x in t if x["state"] in ("due", "overdue")), windows=w, planned=Q1("SELECT COUNT(*) c FROM spray_log WHERE user_id=? AND planned=1 AND applied_on>=?", (u["id"], str(dt.date.today())))["c"])


# ------------------------------------------------------------------ achievements (derived from real records only)
def badge_state(u):
    uid = u["id"]; one = lambda sql, *a: (Q1(sql, a) or {}).get("c", 0) or 0
    farms = one("SELECT COUNT(*) c FROM farms WHERE user_id=?", uid)
    fields = one("SELECT COUNT(*) c FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=?", uid)
    lst = one("SELECT COUNT(*) c FROM listings WHERE seller_id=? AND status!='Withdrawn'", uid)
    ver = one("SELECT COUNT(*) c FROM listings WHERE seller_id=? AND verify_status='Verified'", uid)
    deals = one("SELECT COUNT(*) c FROM offers o JOIN listings l ON l.id=o.listing_id WHERE l.seller_id=? AND o.status='Completed'", uid)
    bought = one("SELECT COUNT(*) c FROM offers WHERE buyer_id=? AND status='Completed'", uid)
    spr = one("SELECT COUNT(*) c FROM spray_log WHERE user_id=? AND planned=0 AND phi_days IS NOT NULL", uid)
    exp = one("SELECT COUNT(*) c FROM expenses e JOIN fields f ON f.id=e.field_id JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=?", uid)
    scans = one("SELECT COUNT(*) c FROM scans WHERE user_id=?", uid)
    rep = one("SELECT COUNT(*) c FROM distress_reports WHERE farmer_id=?", uid)
    done = one("SELECT COUNT(*) c FROM care_done WHERE user_id=?", uid)
    role = u["role"]
    B = [("farm", "🌱", ("First farm", "Umurima wa mbere", "Première ferme"), ("Register your first farm", "Andikisha umurima wawe wa mbere", "Enregistrez une ferme"), farms, 1, "farmer"),
         ("fields", "🗺️", ("Field mapper", "Uzi imirima yawe", "Cartographe"), ("Register 3 fields", "Andikisha imirima 3", "3 champs"), fields, 3, "farmer"),
         ("sell", "🛒", ("First listing", "Igicuruzwa cya mbere", "Première annonce"), ("List a harvest for sale", "Shyira umusaruro ku isoko", "Mettez une récolte en vente"), lst, 1, "farmer"),
         ("verified", "✅", ("Verified harvest", "Umusaruro wemejwe", "Récolte vérifiée"), ("Get a harvest confirmed by an advisor", "Umujyanama yemeje umusaruro wawe", "Récolte confirmée"), ver, 1, "farmer"),
         ("deal", "🤝", ("First deal", "Ubucuruzi bwa mbere", "Première vente"), ("Complete a deal with a buyer", "Curuza n'umuguzi ubirangize", "Terminez une vente"), deals, 1, "farmer"),
         ("trusted", "⭐", ("Trusted seller", "Umucuruzi wizewe", "Vendeur de confiance"), ("Complete 5 deals", "Kurangiza ubucuruzi 5", "5 ventes"), deals, 5, "farmer"),
         ("safe", "🧴", ("Safe sprayer", "Utera umuti neza", "Traitement sûr"), ("Log 3 sprays with their pre-harvest interval", "Andika imiti 3 hamwe n'iminsi mbere y'isarura", "3 traitements avec DAR"), spr, 3, "farmer"),
         ("records", "📒", ("Record keeper", "Ubika inyandiko", "Tenue des comptes"), ("Record 5 expenses", "Andika ibyatanzwe 5", "5 dépenses"), exp, 5, "farmer"),
         ("doctor", "🔬", ("Crop doctor", "Muganga w'ibihingwa", "Docteur des cultures"), ("Scan a leaf with the crop scanner", "Genzura ikibabi n'igikoresho", "Scannez une feuille"), scans, 1, "farmer"),
         ("voice", "📢", ("Voice of farmers", "Ijwi ry'abahinzi", "Voix des agriculteurs"), ("Report a problem to the government", "Menyesha Leta ikibazo", "Signalez un problème"), rep, 1, "farmer"),
         ("caretaker", "🧑🏾‍🌾", ("Good caretaker", "Witaho umurima", "Bon soigneur"), ("Complete 3 field-care tasks", "Kora imirimo 3 yo kwita ku murima", "3 tâches"), done, 3, "farmer"),
         ("b1", "🛍️", ("First purchase", "Kugura bwa mbere", "Premier achat"), ("Complete a purchase", "Rangiza kugura", "Premier achat"), bought, 1, "buyer"),
         ("b5", "🏆", ("Regular buyer", "Umuguzi uhoraho", "Acheteur régulier"), ("Complete 5 purchases", "Rangiza kugura 5", "5 achats"), bought, 5, "buyer")]
    return [dict(code=c, icon=ic, title=P(*t), desc=P(*d), have=min(h, n), need=n, earned=h >= n) for c, ic, t, d, h, n, r in B if r == role]


def award(u):
    st = badge_state(u); have = {r["code"] for r in Q("SELECT code FROM badges WHERE user_id=?", (u["id"],))}
    for b in st:
        if b["earned"] and b["code"] not in have:
            X("INSERT OR IGNORE INTO badges(user_id,code) VALUES(?,?)", (u["id"], b["code"]))
    return st


@bp.get("/badges")
@need("farmer", "buyer")
def badges_page():
    st = award(g.user)
    return render_template("v11/badges.html", st=st, n=sum(1 for b in st if b["earned"]))


@bp.get("/api/v11/badges")
@need("farmer", "buyer")
def badges_api():
    st = award(g.user)
    return jsonify(earned=[b["code"] for b in st if b["earned"]], total=len(st), titles={b["code"]: b["icon"] + " " + b["title"] for b in st})
