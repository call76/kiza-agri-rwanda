"""KIZA-AGRI - Rwanda smart agriculture platform (Flask + SQLite trial). Grow Smarter. Sell Better. Plan Together."""
import urllib.parse, gzip as _gz, os, re, json, time, secrets, hmac, datetime as dt, logging
from functools import wraps
from flask import send_from_directory, Flask, Response, render_template, request, redirect, session, flash, abort, jsonify, g
from markupsafe import Markup
from werkzeug.security import generate_password_hash, check_password_hash
import statistics, csv, io
from urllib.parse import urlencode
import disease, db, rules, mlclient, loaders, weather_live, esoko, sync, ussd
from i18n_fr import FR, FRL, MSG
from kiza8 import i18n_post

app = Flask(__name__)
def _secret():  # stable key so sessions/forms survive restarts
    if os.environ.get("KIZA_SECRET"): return os.environ["KIZA_SECRET"]
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".secret_key")
    if not os.path.exists(p): open(p, "w").write(secrets.token_hex(32))
    return open(p).read().strip()
app.secret_key = _secret()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", MAX_CONTENT_LENGTH=12 * 1024 * 1024)
logging.basicConfig(filename=os.path.join(os.path.dirname(os.path.abspath(__file__)), "kiza.log"), level=logging.ERROR)
# v10: REAL mode by default (clean database, no demo rows). Set KIZA_DEMO=1 to get the old demo data.
# Hackathon: on Render (which sets RENDER=true) default to the DEMO database so the sample logins work, unless KIZA_DEMO=0 is set explicitly.
_DEMO = os.environ.get("KIZA_DEMO") == "1" or (bool(os.environ.get("RENDER")) and os.environ.get("KIZA_DEMO") != "0")
if not os.path.exists(db.DB) and not _DEMO: db.init_real()
else: db.init()
HOME = {"farmer": "/farmer", "buyer": "/buyer", "extension": "/advisor/home", "government": "/gov", "admin": "/admin"}
STAFF = ("extension", "government", "admin")
TODAY = lambda: str(dt.date.today())

# ---------- helpers ----------
def _c():
    if "db" not in g: g.db = db.conn()
    return g.db
def Q(sql, a=()): return [dict(r) for r in _c().execute(sql, a).fetchall()]
def Q1(sql, a=()): r = _c().execute(sql, a).fetchone(); return dict(r) if r else None
def X(sql, a=()): cur = _c().execute(sql, a); _c().commit(); return cur.lastrowid
@app.teardown_appcontext
def _close(e):
    if "db" in g: g.db.close()
def audit(action, detail=""): X("INSERT INTO audit_logs(user_id,action,detail,ip) VALUES(?,?,?,?)", (session.get("uid"), action, detail, request.remote_addr))
def notify(uid, kind, msg, link="/notifications"): X("INSERT INTO notifications(user_id,kind,message,link) VALUES(?,?,?,?)", (uid, kind, msg, link))
def me(): return Q1("SELECT * FROM users WHERE id=?", (session["uid"],)) if session.get("uid") else None
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
def num(name, lo=None, hi=None, default=None, opt=False):
    try: v = float(request.form.get(name, "")); assert (lo is None or v >= lo) and (hi is None or v <= hi); return v
    except Exception:
        if opt: return None
        if default is not None: return default
        raise ValueError(name)

# ---------- security + i18n ----------
@app.before_request
def csrf():
    if "csrf" not in session: session["csrf"] = secrets.token_hex(16)
    if request.method == "POST" and session.get("guest") and (request.path.startswith(("/market/", "/offers/", "/distress")) ):
        flash("Guest accounts can explore only. Create a free account to sell, make offers or report problems.", "err"); return redirect(request.referrer or "/register")
    if request.method == "POST" and request.path in ("/ussd", "/api/assistant", "/api/v8/sms/dlr", "/login", "/register"): return None   # read-only endpoints: never blocked by an expired token
    if request.method == "POST" and request.form.get("_csrf") != session["csrf"]:
        flash("Your page expired. Please try again.", "err"); return redirect(request.path if request.path in ("/login", "/register") else (request.referrer or "/login"))
LANGS = ("en", "rw", "fr")
def _L(en, rw, fr=None):
    lg = session.get("lang")
    return rw if lg == "rw" else ((fr or FRL.get(en, en)) if lg == "fr" else en)
app.jinja_env.globals["L"] = _L
def _tm(m):
    lg = session.get("lang"); e = MSG.get(m)
    return (e[0] if lg == "rw" else e[1] if lg == "fr" else m) if e else m
app.jinja_env.filters["tm"] = _tm
app.jinja_env.globals["csrf_input"] = lambda: Markup('<input type="hidden" name="_csrf" value="%s">' % session.get("csrf", ""))

RW = {"Today": "Uyu munsi", "My Farms": "Imirima yanjye", "Crop Advisor": "Inama ku bihingwa", "Weather": "Ikirere", "Fertilizer": "Ifumbire (Nkunganire)",
 "Report a problem": "Menyesha ikibazo", "Marketplace": "Isoko", "Offers": "Ibyifuzo", "Prices": "Ibiciro", "Government": "Leta", "Login": "Injira", "Register": "Iyandikishe",
 "Logout": "Sohoka", "Get started": "Tangira", "Phone number": "Numero ya telefone", "Email (optional)": "Imeri (si ngombwa)", "Password": "Ijambo ry'ibanga", "Confirm password": "Subiramo ijambo ry'ibanga",
 "Full name": "Amazina yombi", "District": "Akarere", "Sector": "Umurenge", "Create account": "Fungura konti", "I am a": "Ndi", "Farmer": "Umuhinzi", "Buyer / Trader": "Umuguzi / Umucuruzi",
 "Phone or email": "Telefone cyangwa imeri", "What to do now": "Icyo gukora nonaha", "Welcome back": "Murakaza neza", "Show": "Erekana", "Hide": "Hisha", "My fields": "Imirima yanjye",
 "Sell my harvest": "Gurisha umusaruro", "Report a problem to the government": "Menyesha Leta ikibazo", "Send report": "Ohereza", "Calculate": "Kubara", "Analyse": "Isesengura",
 "Language": "Ururimi", "Create your account": "Fungura konti yawe", "Already have an account?": "Usanzwe ufite konti?", "New here?": "Uri mushya hano?", "Save": "Bika",
 "Open market price": "Igiciro ku isoko risanzwe", "Subsidized price": "Igiciro cya Nkunganire", "You save": "Uzigama", "Command Center": "Ikigo cy'ubugenzuzi", "Data": "Amakuru", "Soil": "Ubutaka", "Farm": "Ubuhinzi", "Market": "Isoko", "Help": "Ubufasha", "Assistant": "Umufasha (AI)", "Contact support": "Vugana n'ubufasha", "Help center": "Ikigo cy'ubufasha", "About": "Abo turi bo", "Support inbox": "Ubutumwa bw'ubufasha", "Try as guest": "Gerageza nk'umushyitsi", "Guest": "Umushyitsi", "Create free account": "Fungura konti y'ubuntu", "Features": "Ibyo dukora", "How it works": "Uko bikora", "Platform": "Urubuga", "Support": "Ubufasha", "Home": "Ahabanza", "Notifications": "Ibimenyetso", "Contrast": "Itandukaniro", "Admin": "Ubuyobozi", "Audit log": "Amateka y'ibikorwa"}
def tl(en, rw, fr_=None, lang=None):
    lg = lang or session.get("lang")
    return rw if lg == "rw" else ((fr_ or FRL.get(en, en)) if lg == "fr" else en)
def tr(k):
    lg = session.get("lang")
    return RW.get(k, k) if lg == "rw" else (FR.get(k, k) if lg == "fr" else k)

@app.route("/lang/<code>")
def lang(code):
    session["lang"] = code if code in LANGS else "en"; session["lang_chosen"] = True
    if session.get("uid"): X("UPDATE users SET lang=? WHERE id=?", (session["lang"], session["uid"]))
    nxt = request.args.get("next", "")
    if nxt.startswith("/") and not nxt.startswith("//"): return redirect(nxt)
    ref = request.referrer or ""
    return redirect(ref if ref.startswith(request.host_url) and "/welcome" not in ref else "/")

@app.get("/welcome")
def welcome(): return render_template("welcome.html")

def is_advisor(u): return bool(u and u["role"] == "extension" and (u.get("village") or "").strip())
def scope(u, p=""):
    """SQL limit for what a staff member may verify: village advisor = own village; district officer = own district; government/admin = all."""
    if u["role"] != "extension": return "", ()
    if is_advisor(u): return f" AND {p}district=? AND lower(trim(COALESCE({p}village,'')))=?", (u["district"], u["village"].strip().lower())
    return f" AND {p}district=?", (u["district"],)
def _pv(u):
    sc, a = scope(u)
    return Q1("SELECT COUNT(*) c FROM listings WHERE verify_status='Pending' AND status IN ('Available','Offer Received','Reserved')" + sc, a)["c"]

@app.context_processor
def ctx():
    u = me(); n = Q1("SELECT COUNT(*) c FROM notifications WHERE user_id=? AND is_read=0", (u["id"],))["c"] if u else 0
    demo = bool(Q1("SELECT 1 x FROM market_prices WHERE source LIKE '%DEMO%' LIMIT 1") or Q1("SELECT 1 x FROM weather WHERE is_demo=1 LIMIT 1") or Q1("SELECT 1 x FROM soil_profiles WHERE is_demo=1 LIMIT 1"))
    return {"is_demo": demo, "user": u, "unread": n, "today": TODAY(), "t": tr, "lang": session.get("lang", "en"), "homes": HOME, "home_url": HOME[u["role"]] if u else "/", "advisor": is_advisor(u), "csrf_token": session.get("csrf", ""), "pending_verify": (_pv(u) if u and u["role"] in STAFF else 0), "is_guest": bool(u and u["email"].endswith("@guest.kiza"))}

@app.after_request
def _fast(r):
    try: i18n_post.translate_response(r, session.get("lang", "en"))
    except Exception: logging.exception("i18n")
    r.headers.setdefault("X-Content-Type-Options", "nosniff")
    if request.path.startswith("/static/"): r.headers["Cache-Control"] = "public, max-age=3600"
    if (r.status_code == 200 and not r.direct_passthrough and r.mimetype in ("text/html", "application/json", "text/css", "application/javascript", "text/javascript")
            and "gzip" in request.headers.get("Accept-Encoding", "") and "Content-Encoding" not in r.headers):
        d = r.get_data()
        if len(d) > 700: r.set_data(_gz.compress(d, 5)); r.headers["Content-Encoding"] = "gzip"; r.headers["Vary"] = "Accept-Encoding"
    return r
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600

@app.errorhandler(403)
def e403(e): return (jsonify(error="forbidden") if request.path.startswith("/api/") else render_template("msg.html", title="No access", msg="Your role cannot open this page.")), 403
@app.errorhandler(404)
def e404(e): return (jsonify(error="not found") if request.path.startswith("/api/") else render_template("msg.html", title="Not found", msg="This page does not exist.")), 404
@app.errorhandler(Exception)
def e500(e):
    if hasattr(e, "code"): return e
    logging.exception(e)
    if request.path.startswith("/api/"): return jsonify(error="server error"), 500
    return render_template("msg.html", title="Something went wrong", msg="We logged the problem. Please try again."), 500

# ---------- public + auth ----------
@app.get("/")
def index():
    if not session.get("lang_chosen") and not session.get("uid"): return redirect("/welcome")
    return render_template("landing.html", s=Q1("SELECT (SELECT COUNT(*) FROM users WHERE role='farmer' AND email NOT LIKE '%@guest.kiza') f,(SELECT COUNT(*) FROM farms) fa,(SELECT COALESCE(SUM(size_ha),0) FROM fields WHERE status NOT IN ('Planned','Prepared','Failed')) ha,(SELECT COUNT(*) FROM listings WHERE verify_status='Verified' AND status IN ('Available','Offer Received','Reserved')) l"))

def norm_phone(p):
    d = re.sub(r"\D", "", p or "")
    if d.startswith("250"): d = "0" + d[3:]
    if len(d) == 9 and d[0] == "7": d = "0" + d
    return d if re.fullmatch(r"07[2389]\d{7}", d) else None

FAILS = {}
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ip = request.remote_addr; FAILS[ip] = [t for t in FAILS.get(ip, []) if time.time() - t < 600]
        ident = request.form.get("ident", "").strip()
        if len(FAILS[ip]) >= 8: flash("Too many attempts. Please wait 10 minutes.", "err")
        else:
            u = Q1("SELECT * FROM users WHERE email=?", (ident.lower(),)) if "@" in ident else (Q1("SELECT * FROM users WHERE phone=?", (norm_phone(ident),)) if norm_phone(ident) else None)
            if u and u["status"] == "active" and check_password_hash(u["pw_hash"], request.form.get("password", "")):
                lang_ = session.get("lang") or u["lang"]; session.clear(); session["uid"] = u["id"]; session["lang"] = lang_ if lang_ in LANGS else "en"; session["lang_chosen"] = True; audit("login", u["email"]); return redirect(HOME[u["role"]])
            FAILS[ip].append(time.time()); flash("Wrong phone/email or password.", "err")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    ds = Q("SELECT name FROM districts ORDER BY name")
    if request.method == "POST":
        f = request.form; role = f.get("role"); phone = norm_phone(f.get("phone")); email = f.get("email", "").strip().lower(); pw = f.get("password", "")
        err = None
        if role not in ("farmer", "buyer"): err = "Choose Farmer or Buyer."
        elif not f.get("name", "").strip(): err = "Please enter your full name."
        elif not phone: err = "Enter a valid Rwandan phone number (e.g. 0788 123 456)."
        elif email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email): err = "That email does not look right."
        elif f.get("district") not in [d["name"] for d in ds]: err = "Choose your district."
        elif role == "farmer" and not f.get("sector", "").strip(): err = "Enter your sector (umurenge)."
        elif len(pw) < 8 or not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw): err = "Password needs 8+ characters with letters and numbers."
        elif pw != f.get("password2"): err = "The two passwords do not match."
        elif Q1("SELECT id FROM users WHERE phone=?", (phone,)): err = "This phone number is already registered. Try logging in."
        elif email and Q1("SELECT id FROM users WHERE email=?", (email,)): err = "This email is already registered."
        if err: flash(err, "err")
        else:
            uid = X("INSERT INTO users(name,email,phone,pw_hash,role,district,sector,lang) VALUES(?,?,?,?,?,?,?,?)", (f["name"].strip()[:80], email or f"p{phone}@phone.kiza", phone, generate_password_hash(pw), role, f["district"], f.get("sector", "").strip()[:60], f.get("lang", "en")))
            lg = f.get("lang", "en"); lg = lg if lg in LANGS else "en"; session.clear(); session["uid"] = uid; session["lang"] = lg; session["lang_chosen"] = True; audit("register", phone); return redirect(HOME[role])
    return render_template("register.html", ds=ds, f=request.form)

@app.post("/logout")
def logout(): session.clear(); return redirect("/")

# ---------- farmer: passport, LUC, advisor ----------
def own_farm(fid):
    f = Q1("SELECT * FROM farms WHERE id=?", (fid,))
    if not f or f["user_id"] != g.user["id"]: abort(403)
    return f
def wx3(d): return Q("SELECT * FROM weather WHERE district=? ORDER BY day LIMIT 3", (d,))
def avg_prices(): return {r["crop"]: r["p"] for r in Q("SELECT crop, AVG(price_kg) p FROM market_prices m WHERE day=(SELECT MAX(day) FROM market_prices WHERE crop=m.crop) GROUP BY crop")}
def luc(district, sector, crop):
    z = Q1("SELECT mandated_crop FROM luc_zones WHERE district=? AND lower(sector)=lower(?)", (district, (sector or "").strip()))
    return ("unknown", None) if not z else (("aligned" if z["mandated_crop"] == crop else "not_aligned"), z["mandated_crop"])

def deal_stats(uid):
    """Seller track record: accepted/completed deals, kg, revenue, average buyer rating."""
    a = Q1("SELECT COUNT(*) n, COALESCE(SUM(o.qty_kg),0) kg, COALESCE(SUM(o.qty_kg*o.price_kg),0) rwf, SUM(o.status='Completed') done, AVG(o.rating) rating, COUNT(o.rating) nr FROM offers o JOIN listings l ON l.id=o.listing_id WHERE l.seller_id=? AND o.status IN ('Accepted','Completed')", (uid,))
    a["done"] = a["done"] or 0; a["rating"] = round(a["rating"], 1) if a["rating"] else None; return a

@app.get("/farmer")
@need("farmer")
def farmer():
    u = g.user; farms = Q("SELECT * FROM farms WHERE user_id=?", (u["id"],))
    try:
        from kiza8 import care as _care; _care.send_rain_reminders(u["id"])
    except Exception: pass
    fields = Q("SELECT f.*, fa.name farm FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=?", (u["id"],))
    wx = wx3(u["district"]); acts = [(k, t, "/weather") for k, t in rules.weather_advice(wx)] if wx else []
    for f in fields:
        if f["luc_status"] == "not_aligned": acts.append(("warn", f"{f['crop']} in {f['name']} is not your sector's LUC priority crop - confirm with your agronomist.", "/farms"))
        if f["status"] in ("Growing", "Flowering", "Planted") and f["expected_harvest"]:
            d = (dt.date.fromisoformat(f["expected_harvest"]) - dt.date.today()).days
            if d <= 14: acts.append(("info", f"Harvest reminder: {f['crop']} in {f['name']} ready in about {max(d,0)} days.", "/market"))
    for k, t in rules.soil_advice(Q1("SELECT * FROM soil_profiles WHERE district=?", (u["district"],)))[:2]:
        if k != "ok": acts.append((k, t, "/soil"))
    pend = Q1("SELECT COUNT(*) c FROM offers o JOIN listings l ON l.id=o.listing_id WHERE l.seller_id=? AND o.status='Pending'", (u["id"],))["c"]
    if pend: acts.insert(0, ("ok", f"{pend} buyer offer(s) waiting for your answer.", "/offers"))
    for r in Q("SELECT crop, predicted_trend, change_pct FROM esoko_prices WHERE district=?", (u["district"],)):
        if r["crop"] in {f["crop"] for f in fields} and r["predicted_trend"] in ("rising", "falling"): acts.append(("ok" if r["predicted_trend"] == "rising" else "warn", f"{r['crop']} price is {r['predicted_trend']} ({r['change_pct']:+.1f}% recent change) in {u['district']}.", "/prices?crop=" + r["crop"]))
    stale = Q("SELECT * FROM listings WHERE seller_id=? AND status IN ('Available','Offer Received','Reserved') AND available_kg>0 AND (harvest_date IS NULL OR harvest_date<=date('now')) AND date(COALESCE(last_confirmed, created_at))<=date('now','-14 day') ORDER BY id LIMIT 5", (u["id"],))
    sched = Q("SELECT * FROM listings WHERE seller_id=? AND status!='Withdrawn' AND harvest_date>date('now') ORDER BY harvest_date LIMIT 5", (u["id"],))
    from kiza8 import knowledge as _K
    _fm = next((f for f in farms if f.get("lat") is not None and f.get("lng") is not None), None) or Q1("SELECT lat, lng FROM districts WHERE name=?", (u["district"],)) or {"lat": -1.95, "lng": 30.06}
    return render_template("farmer.html", geo={"lat": _fm["lat"], "lng": _fm["lng"]}, season=_K.current_season()[1], stale=stale, sched=sched, farms=farms, fields=fields, wx=wx, acts=acts[:8], notes=Q("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 4", (u["id"],)), sales=deal_stats(u["id"]),
                           lst=Q1("SELECT COUNT(*) n, COALESCE(SUM(verify_status='Verified' AND status IN ('Available','Offer Received','Reserved')),0) live, COALESCE(SUM(verify_status IN ('Pending','Needs visit')),0) wait FROM listings WHERE seller_id=? AND status!='Withdrawn'", (u["id"],)))

@app.route("/farms", methods=["GET", "POST"])
@need("farmer")
def farms():
    ds = Q("SELECT * FROM districts ORDER BY name")
    if request.method == "POST":
        try:
            d = request.form.get("district"); dd = next(x for x in ds if x["name"] == d); sp = num("soil_ph", 3, 9, opt=True)
            if sp is None: pr = Q1("SELECT ph_level FROM soil_profiles WHERE district=?", (d,)); sp = pr["ph_level"] if pr else None
            fid = X("INSERT INTO farms(user_id,name,size_ha,lat,lng,district,sector,soil_type,soil_ph,irrigation) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (g.user["id"], request.form["name"].strip()[:80] or "My farm", num("size_ha", .01, 10000), num("lat", -3, 0, opt=True) or dd["lat"], num("lng", 28, 31, opt=True) or dd["lng"], d,
                     request.form.get("sector", "").strip()[:60] or g.user["sector"], request.form.get("soil_type", "")[:40], sp, 1 if request.form.get("irrigation") else 0))
            audit("farm.create", str(fid)); flash("Farm registered. Now add a field.", "ok"); return redirect(f"/farms/{fid}")
        except Exception: flash("Please check the farm details (name, size above 0, district).", "err")
    return render_template("farms.html", farms=Q("SELECT * FROM farms WHERE user_id=?", (g.user["id"],)), ds=ds)

@app.get("/farms/<int:fid>")
@need("farmer")
def farm(fid):
    f = own_farm(fid); z = Q1("SELECT mandated_crop FROM luc_zones WHERE district=? AND lower(sector)=lower(?)", (f["district"], f["sector"] or ""))
    return render_template("farm.html", f=f, fields=Q("SELECT * FROM fields WHERE farm_id=?", (fid,)), crops=Q("SELECT name FROM crops ORDER BY name"), season=rules.season(), lucz=z)

@app.post("/farms/<int:fid>/fields")
@need("farmer")
def add_field(fid):
    f = own_farm(fid)
    try:
        crop = Q1("SELECT * FROM crops WHERE name=?", (request.form.get("crop"),)); assert crop
        ha = num("size_ha", .01, 10000); pd = request.form.get("planting_date") or TODAY(); status = request.form.get("status", "Planned"); assert status in ("Planned", "Prepared", "Planted", "Growing")
        ls, mand = luc(f["district"], f["sector"], crop["name"])
        if ls == "not_aligned" and not request.form.get("confirm"):
            flash(f"LUC guardrail: the priority crop for {f['sector']} sector is {mand}, not {crop['name']}. Check with your sector agronomist, then tick the confirmation box to continue.", "err"); return redirect(f"/farms/{fid}")
        X("INSERT INTO fields(farm_id,name,size_ha,crop,season,planting_date,expected_harvest,luc_status,status) VALUES(?,?,?,?,?,?,?,?,?)",
          (fid, request.form["name"].strip()[:60] or "Field", ha, crop["name"], rules.season(), pd, str(dt.date.fromisoformat(pd) + dt.timedelta(crop["cycle_days"])), ls, status))
        audit("field.create", f"farm {fid} {crop['name']} luc={ls}"); flash("Field created." + (" LUC: aligned with your sector's priority crop." if ls == "aligned" else ""), "ok")
    except Exception: flash("Please check the field details.", "err")
    return redirect(f"/farms/{fid}")

@app.post("/fields/<int:fid>/status")
@need("farmer")
def field_status(fid):
    fl = Q1("SELECT f.*, fa.user_id FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE f.id=?", (fid,))
    if not fl or fl["user_id"] != g.user["id"]: abort(403)
    s = request.form.get("status")
    if s in ("Planned", "Prepared", "Planted", "Growing", "Flowering", "Harvesting", "Harvested", "Failed"): X("UPDATE fields SET status=? WHERE id=?", (s, fid)); audit("field.status", f"{fid}->{s}")
    return redirect(f"/farms/{fl['farm_id']}")

@app.get("/advisor")
@need("farmer")
def advisor():
    fs = Q("SELECT * FROM farms WHERE user_id=?", (g.user["id"],))
    if not fs: flash("Register a farm first.", "err"); return redirect("/farms")
    farm = next((f for f in fs if str(f["id"]) == request.args.get("farm")), fs[0]); wx = wx3(farm["district"]); crops = Q("SELECT * FROM crops")
    if not crops: return render_template("msg.html", title="Crop data not loaded yet", msg="An administrator must load the crops dataset first (Data page).")
    res = rules.advise(crops, farm, wx[0] if wx else None, avg_prices())
    for r in res: r["luc"], r["luc_crop"] = luc(farm["district"], farm["sector"], r["crop"])
    mand = next((r["luc_crop"] for r in res if r["luc_crop"]), None)
    return render_template("advisor.html", farms=fs, farm=farm, res=res, top=res[0], mand=mand, wx=wx[0] if wx else None, season=rules.season())

@app.get("/weather")
@need("farmer", "extension", "admin")
def weather():
    d = request.args.get("district") or g.user["district"]; wx = wx3(d)
    live = bool(wx) and not wx[0]["is_demo"]; stale = live and (wx[0]["fetched_at"] or "")[:10] < str(dt.date.today() - dt.timedelta(1))
    return render_template("weather.html", live=live, stale=stale, wx=wx, tips=rules.weather_advice(wx) if wx else [], ds=Q("SELECT name FROM districts ORDER BY name"), d=d)

@app.route("/fertilizer", methods=["GET", "POST"])
@need("farmer", "extension", "admin")
def fertilizer():
    out = None; crops = Q("SELECT name FROM crops ORDER BY name")
    fields = Q("SELECT f.*, fa.name farm FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=?", (g.user["id"],)) if g.user["role"] == "farmer" else []
    if request.method == "POST":
        try:
            crop = request.form["crop"]; ha = num("ha", .01, 10000)
            rs = Q("SELECT * FROM fertilizer_subsidies WHERE crop=? ORDER BY stage", (crop,)); rows, warn = rules.fert_calc(rs, ha)
            tot = lambda k: sum(r[k] for r in rows if r[k] is not None)
            out = {"rows": rows, "warn": warn, "crop": crop, "ha": ha, "market": tot("market_cost"), "subsidy": tot("subsidy_cost"), "saving": tot("saving"), "kg": round(tot("kg"), 1)}
            if not rs: flash("No fertilizer data is loaded for this crop yet.", "err")
        except Exception: flash("Please choose a crop and a field size above 0.", "err")
    ds = Q("SELECT name FROM districts ORDER BY name")
    dist = request.values.get("district") or g.user["district"] or ""
    want = [r["fertilizer"] for r in out["rows"]] if out else []
    outl = find_outlets(dist, g.user.get("sector"), want)
    return render_template("fertilizer.html", out=out, crops=crops, fields=fields, ds=ds, dist=dist, outlets=outl, magic=magic_plan(fields, dist, g.user.get("sector")), qs=urllib.parse.quote)

def magic_plan(fields, district, sector):
    """MAGIC PLAN: one tap for the whole farm. Sums fertilizer over all the farmer's fields, shows the Nkunganire saving, the best outlet for each fertilizer,
    and a rain-aware 'apply today or wait' tip from the stored 3-day forecast. Shopping list can be shared on WhatsApp."""
    tot = {}; saving = 0; market = 0; sub = 0
    for f in fields:
        if not f.get("crop"): continue
        rows, _ = rules.fert_calc(Q("SELECT * FROM fertilizer_subsidies WHERE crop=?", (f["crop"],)), f["size_ha"])
        for r in rows:
            t = tot.setdefault(r["fertilizer"], {"fertilizer": r["fertilizer"], "kg": 0, "market": 0, "subsidy": 0, "fields": set()})
            t["kg"] += r["kg"]; t["market"] += r["market_cost"] or 0; t["subsidy"] += r["subsidy_cost"] or 0; t["fields"].add(f["name"])
    if not tot: return None
    outs = find_outlets(district, sector, list(tot))
    for t in tot.values():
        t["kg"] = round(t["kg"]); t["fields"] = ", ".join(sorted(t["fields"])); market += t["market"]; sub += t["subsidy"]
        t["best"] = next((o for o in outs if t["fertilizer"] in o["has"] and o["stock"] != "Out of stock"), None)
    wx = wx3(district); rain = next((w for w in wx[:2] if (w["rain_prob"] or 0) >= 70 or (w["rain_mm"] or 0) >= 10), None)
    tip = ("rain", "Heavy rain is likely soon: wait for a dry day before spreading, or the fertilizer washes away. Buy now and store it dry.") if rain else \
          ("ok", "No heavy rain expected in the next 2 days: good time to apply, and best on moist soil.") if wx else None
    lines = [f"- {t['fertilizer']}: {t['kg']} kg" + (f" ({t['best']['name']}, {t['best']['district']})" if t["best"] else "") for t in tot.values()]
    msg = "KIZA-AGRI: my fertilizer list\n" + "\n".join(lines) + f"\nI save {market - sub:,} RWF with Nkunganire."
    return {"items": list(tot.values()), "market": market, "subsidy": sub, "saving": market - sub, "tip": tip, "wa": "https://wa.me/?text=" + urllib.parse.quote(msg)}

STOCK_RANK = {"In stock": 0, "Low": 1, "Out of stock": 2}
def find_outlets(district, sector=None, want=()):
    """Cooperatives / agro-dealers in a district: in-stock first, then the farmer's own sector, then ones that carry the fertilizer the farmer needs."""
    rows = Q("SELECT * FROM fertilizer_outlets WHERE district=?", (district,)) if district else []
    for r in rows:
        have = [x.strip().lower() for x in (r["fertilizers"] or "").split(",")]
        r["has"] = [w for w in want if w.lower() in have]; r["missing"] = [w for w in want if w.lower() not in have]
        r["near"] = bool(sector) and (r["sector"] or "").lower() == sector.lower()
    rows.sort(key=lambda r: (STOCK_RANK.get(r["stock"], 1), not r["near"], len(r["missing"]), -r["subsidized"], r["name"]))
    return rows

@app.get("/api/nearest-district")
@need("farmer", "extension", "admin")
def nearest_district():
    """GPS -> nearest district centroid (so the farmer does not have to pick the district)."""
    try: la, ln = float(request.args["lat"]), float(request.args["lng"])
    except Exception: return jsonify(error="lat and lng required"), 400
    ds = Q("SELECT name, lat, lng FROM districts WHERE lat IS NOT NULL")
    if not ds: return jsonify(error="no districts"), 404
    d = min(ds, key=lambda r: (r["lat"] - la) ** 2 + (r["lng"] - ln) ** 2)
    return jsonify(district=d["name"])

@app.get("/api/fertilizer/outlets")
@need("farmer", "extension", "admin")
def api_outlets():
    d = request.args.get("district") or g.user["district"] or ""
    want = [x for x in request.args.get("fert", "").split(",") if x]
    return jsonify(district=d, outlets=find_outlets(d, g.user.get("sector"), want))

# ---------- distress registry ----------
KINDS_D = ["Glut / no buyers", "Price manipulation by middlemen", "Spoilage / storage problem", "Other"]
@app.route("/distress", methods=["GET", "POST"])
@need("farmer")
def distress():
    if request.method == "POST":
        try:
            kind = request.form["kind"]; assert kind in KINDS_D; crop = request.form["crop"]; assert Q1("SELECT 1 x FROM crops WHERE name=?", (crop,))
            rid = X("INSERT INTO distress_reports(farmer_id,district,crop,kind,qty_kg,details) VALUES(?,?,?,?,?,?)", (g.user["id"], g.user["district"], crop, kind, num("qty_kg", 1, 1e8), request.form.get("details", "")[:600]))
            for s in Q("SELECT id FROM users WHERE role IN ('extension','government','admin')"): notify(s["id"], "distress", f"New distress report: {kind} - {crop} in {g.user['district']}.", "/distress/inbox")
            audit("distress.create", str(rid)); flash("Report sent to the government team. Thank you.", "ok")
        except Exception: flash("Please choose a crop, a problem type and enter the quantity in kg.", "err")
        return redirect("/distress")
    return render_template("distress.html", kinds=KINDS_D, crops=Q("SELECT name FROM crops ORDER BY name"), mine=Q("SELECT * FROM distress_reports WHERE farmer_id=? ORDER BY id DESC", (g.user["id"],)))

@app.route("/distress/inbox", methods=["GET", "POST"])
@need(*STAFF)
def distress_inbox():
    if request.method == "POST":
        r = Q1("SELECT * FROM distress_reports WHERE id=?", (request.form.get("id"),)); st = request.form.get("status")
        if r and st in ("New", "Reviewing", "Resolved"):
            X("UPDATE distress_reports SET status=?, officer_note=? WHERE id=?", (st, request.form.get("note", "")[:300], r["id"])); audit("distress.update", f"{r['id']}->{st}")
            if st != "New": notify(r["farmer_id"], "distress", f"Your {r['crop']} report is now: {st}.", "/distress")
        return redirect("/distress/inbox")
    rows = Q("SELECT d.*, u.name farmer, u.phone FROM distress_reports d JOIN users u ON u.id=d.farmer_id ORDER BY CASE d.status WHEN 'New' THEN 0 WHEN 'Reviewing' THEN 1 ELSE 2 END, d.id DESC")
    return render_template("distress_inbox.html", rows=rows)

# ---------- marketplace ----------
def mask(p): return (p[:4] + "***" + p[-3:]) if p and len(p) >= 8 else "-"
def image_ok(field, maxpx=1280):
    """Validate + re-encode an uploaded photo as JPEG. Returns stored file name, None if nothing uploaded; raises ValueError if invalid."""
    f = request.files.get(field)
    if not f or not f.filename: return None
    from PIL import Image, ImageOps
    try:
        im = Image.open(f.stream); im.verify(); f.stream.seek(0); im = Image.open(f.stream)
        if im.format not in ("JPEG", "PNG", "WEBP"): raise ValueError
        im = ImageOps.exif_transpose(im).convert("RGB"); im.thumbnail((maxpx, maxpx)); os.makedirs(UPLOADS, exist_ok=True)
        name = secrets.token_hex(12) + ".jpg"; im.save(os.path.join(UPLOADS, name), "JPEG", quality=85); return name
    except Exception: raise ValueError("Please upload a JPG, PNG or WEBP photo.")
UPLOADS = os.environ.get("KIZA_UPLOADS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads"))
@app.get("/media/<name>")
def media(name):
    if not re.fullmatch(r"[0-9a-f]{24}\.jpg", name): abort(404)
    r = send_from_directory(UPLOADS, name); r.headers["Cache-Control"] = "private, max-age=86400"; return r

def plausibility(l):
    """Cross-check a listing against the farmer's registered fields (declared area x typical yield). Returns list of (level, text)."""
    out = []; c = Q1("SELECT yield_t_ha FROM crops WHERE name=?", (l["crop"],))
    ha = Q1("SELECT COALESCE(SUM(f.size_ha),0) ha FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=? AND f.crop=? AND f.status!='Failed'", (l["seller_id"], l["crop"]))["ha"]
    if not ha: out.append(("bad", "No registered field with this crop - ask the farmer to show the field."))
    elif c:
        mx = ha * c["yield_t_ha"] * 1000 * 1.25
        out.append(("bad", f"Claimed {l['qty_kg']:.0f} kg is above what {ha:g} ha can typically give (about {mx:.0f} kg max).") if l["qty_kg"] > mx else ("ok", f"Claimed quantity fits {ha:g} ha of registered {l['crop']} (typical max about {mx:.0f} kg)."))
    if not l.get("photo"): out.append(("warn", "No photo of the harvest uploaded."))
    if l.get("lat") is None: out.append(("warn", "No GPS location given."))
    if not l.get("village"): out.append(("warn", "Village not given."))
    return out

SORTS = {"new": "l.id DESC", "price_asc": "l.price_kg ASC, l.id DESC", "price_desc": "l.price_kg DESC, l.id DESC", "qty": "l.available_kg DESC, l.id DESC"}
PER_PAGE = 12
@app.get("/market")
@need("farmer", "buyer", *STAFF)
def market():
    u = g.user; a, w = [], "l.status IN ('Available','Offer Received','Reserved')"
    for k, col in (("crop", "l.crop"), ("district", "l.district")):
        if request.args.get(k): w += f" AND {col}=?"; a.append(request.args[k])
    if not request.args.get("future"): w += " AND (l.harvest_date IS NULL OR l.harvest_date<=date('now'))"   # v8: future harvests stay hidden unless the buyer asks for them
    if request.args.get("q"): w += " AND (lower(COALESCE(l.village,'')) LIKE ? OR lower(COALESCE(l.sector,'')) LIKE ?)"; a += ["%" + request.args["q"].lower().strip() + "%"] * 2
    if request.args.get("verified") or u["role"] == "buyer": w += " AND l.verify_status='Verified'"   # buyers NEVER see unconfirmed harvests
    sort = request.args.get("sort") if request.args.get("sort") in SORTS else "new"
    try: page = max(1, int(request.args.get("page", 1)))
    except ValueError: page = 1
    total = Q1("SELECT COUNT(*) c FROM listings l WHERE " + w, a)["c"]; pages = max(1, -(-total // PER_PAGE)); page = min(page, pages)
    ls = Q("SELECT l.*, u.name seller, u.photo seller_photo, v.name advisor, (SELECT ROUND(AVG(o.rating),1) FROM offers o JOIN listings x ON x.id=o.listing_id WHERE x.seller_id=l.seller_id AND o.rating IS NOT NULL) rating "
           "FROM listings l JOIN users u ON u.id=l.seller_id LEFT JOIN users v ON v.id=l.verified_by WHERE " + w + f" ORDER BY (l.verify_status='Verified') DESC, {SORTS[sort]} LIMIT {PER_PAGE} OFFSET {(page - 1) * PER_PAGE}", a)
    acc = {r["listing_id"] for r in Q("SELECT listing_id FROM offers WHERE buyer_id=? AND status IN ('Accepted','Completed')", (u["id"],))}; avg = avg_prices()
    for l in ls:
        l["phone"] = l["contact"] if (u["role"] in STAFF or u["id"] == l["seller_id"] or l["id"] in acc) else mask(l["contact"])
        m = avg.get(l["crop"]); l["mkt"] = round(m) if m else None; l["diff"] = round((l["price_kg"] / m - 1) * 100) if m else None
    mine = Q("SELECT * FROM listings WHERE seller_id=? ORDER BY id DESC", (u["id"],)) if u["role"] == "farmer" else []
    vil = [r["village"] for r in Q("SELECT DISTINCT village FROM users WHERE role='extension' AND status='active' AND district=? AND COALESCE(village,'')!='' ORDER BY village", (u["district"],))] if u["role"] == "farmer" else []
    watches = Q("SELECT * FROM watches WHERE user_id=? ORDER BY id DESC", (u["id"],)) if u["role"] == "buyer" else []
    base = urlencode({k: v for k, v in request.args.items() if k != "page" and v}); base = base + "&" if base else ""
    return render_template("market.html", ls=ls, crops=Q("SELECT name FROM crops ORDER BY name"), ds=Q("SELECT name FROM districts ORDER BY name"), f=request.args, mine=mine, vil=vil,
                           watches=watches, page=page, pages=pages, total=total, base=base, sort=sort)

@app.post("/market/watch")
@need("buyer")
def watch_add():
    crop, dist = request.form.get("crop", ""), request.form.get("district", "")
    if not Q1("SELECT 1 x FROM crops WHERE name=?", (crop,)): flash("Choose a crop first, then set the alert.", "err")
    elif Q1("SELECT COUNT(*) c FROM watches WHERE user_id=?", (g.user["id"],))["c"] >= 10: flash("You can keep up to 10 alerts. Remove one first.", "err")
    else:
        dist = dist if Q1("SELECT 1 x FROM districts WHERE name=?", (dist,)) else ""
        X("INSERT OR IGNORE INTO watches(user_id,crop,district) VALUES(?,?,?)", (g.user["id"], crop, dist)); flash("Alert saved. You will be notified when a confirmed harvest of this crop appears.", "ok")
    return redirect("/market")

@app.post("/market/watch/<int:wid>/delete")
@need("buyer")
def watch_del(wid):
    X("DELETE FROM watches WHERE id=? AND user_id=?", (wid, g.user["id"])); flash("Alert removed.", "ok"); return redirect("/market")

@app.post("/market/sell")
@need("farmer")
def sell():
    f = request.form
    try:
        crop = f["crop"]; assert Q1("SELECT 1 x FROM crops WHERE name=?", (crop,)); q = num("qty_kg", 1, 1e8); pr = num("price_kg", 1, 1e6)
        village = f.get("village", "").strip()[:60]; sector = f.get("sector", "").strip()[:60] or g.user["sector"]; con = norm_phone(f.get("contact")) or g.user["phone"]
        assert village and con
        lat, lng = num("lat", -3, 0, opt=True), num("lng", 28, 31, opt=True); photo = image_ok("photo")
        hd = f.get("harvest_date") or None
        if hd: assert dt.date.fromisoformat(hd) <= dt.date.today() + dt.timedelta(days=366)
        X("INSERT INTO listings(seller_id,crop,qty_kg,available_kg,price_kg,district,quality,village,sector,lat,lng,contact,photo,harvest_date,notes,auto_accept) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (g.user["id"], crop, q, q, pr, g.user["district"], f.get("quality", "Good")[:20], village, sector, lat, lng, con, photo, hd, f.get("notes", "").strip()[:300], 1 if f.get("auto_accept") else 0))
        adv = Q("SELECT id FROM users WHERE role='extension' AND status='active' AND district=? AND lower(trim(COALESCE(village,'')))=?", (g.user["district"], village.lower()))
        for s in adv or Q("SELECT id FROM users WHERE role='extension' AND status='active' AND district=?", (g.user["district"],)): notify(s["id"], "verify", f"New harvest to confirm on the ground: {q:.0f} kg {crop} in {village}.", "/verify")
        audit("listing.create", f"{crop} {q}kg {village}")
        flash(f"Scheduled! Your harvest will appear to buyers on {hd}, after your advisor has confirmed it. Until then it stays off the marketplace." if (hd and hd > TODAY()) else None, "ok") if (hd and hd > TODAY()) else flash("Listed! Your village agricultural advisor will visit your farm to confirm the crop. Buyers see your harvest only after it is confirmed." if adv else "Listed! No advisor is registered for this village yet, so the district officer will check it. Buyers see your harvest only after it is confirmed.", "ok")
    except ValueError as e: flash(str(e) if "photo" in str(e) else "Check crop, quantity, price, harvest date and contact.", "err")
    except Exception: flash("Choose a crop, enter quantity, price, your village and a valid phone number.", "err")
    return redirect("/market")

@app.post("/market/<int:lid>/cancel")
@need("farmer")
def cancel_listing(lid):
    l = Q1("SELECT * FROM listings WHERE id=? AND seller_id=?", (lid, g.user["id"]))
    if not l: abort(403)
    X("UPDATE listings SET status='Withdrawn' WHERE id=?", (lid,)); flash("Listing withdrawn.", "ok"); return redirect("/market")

# ---------- harvest verification (sector / village officers) ----------
REJECT_REASONS = ["Crop not found at the farm", "Quantity far below what was claimed", "Different crop from the one listed", "Crop is not ready / not harvested", "Farmer could not be reached or refused the visit", "Other (explain in the note)"]
@app.route("/verify", methods=["GET", "POST"])
@need("extension", "admin")
def verify():
    """Village agricultural advisor confirms ON THE GROUND that the farmer really has the crop. Only confirmed listings reach buyers."""
    u = g.user; sc, sa = scope(u, "l."); sc0, sa0 = scope(u)
    if request.method == "POST":
        l = Q1("SELECT * FROM listings l WHERE id=?" + sc.replace("l.", ""), (request.form.get("id"),) + sa); dec = request.form.get("decision")
        if not l or dec not in ("Verified", "Rejected", "Needs visit"): abort(403)
        f = request.form; note = f.get("note", "").strip()[:300]; reason = f.get("reason", "").strip()[:120]; back = request.referrer or "/verify"
        vq = num("verified_qty", 1, 1e8, opt=True); lat, lng = num("lat", -3, 0, opt=True), num("lng", 28, 31, opt=True)
        if dec == "Verified" and not f.get("visited"): flash("To confirm, tick that you visited the farm and saw the crop yourself.", "err"); return redirect(back)
        if dec == "Rejected" and reason not in REJECT_REASONS: flash("Choose the reason for rejecting - the farmer will see it.", "err"); return redirect(back)
        if dec == "Rejected" and reason.startswith("Other") and len(note) < 5: flash("Please explain the reason in the note.", "err"); return redirect(back)
        X("UPDATE listings SET verify_status=?, verified_by=?, verified_at=?, verify_note=?, visited=?, verified_qty=?, visit_lat=?, visit_lng=?, reject_reason=? WHERE id=?",
          (dec, u["id"], TODAY(), note, 1 if (dec == "Verified" and f.get("visited")) else 0, vq if dec == "Verified" else None, lat, lng, reason if dec == "Rejected" else None, l["id"]))
        if dec == "Verified" and vq and vq < l["available_kg"]: X("UPDATE listings SET available_kg=? WHERE id=?", (vq, l["id"]))
        if dec == "Verified" and l["verify_status"] != "Verified":
            for wt in Q("SELECT DISTINCT user_id FROM watches WHERE crop=? AND (district='' OR district=?)", (l["crop"], l["district"])): notify(wt["user_id"], "alert", f"New confirmed harvest: {(vq or l['available_kg']):.0f} kg {l['crop']} in {l['district']} at {l['price_kg']:.0f} RWF/kg.", "/market?crop=" + l["crop"])
        msg = {"Verified": f"Your {l['crop']} listing was CONFIRMED by the village advisor - buyers can now see it." + (f" Quantity confirmed: {vq:.0f} kg." if vq else ""),
               "Rejected": f"Your {l['crop']} listing was REJECTED. Reason: {reason}.", "Needs visit": f"The advisor will visit your farm to check your {l['crop']}. Please be there."}[dec]
        notify(l["seller_id"], "verify", msg + (f" Note: {note}" if note else ""), "/market"); audit("listing.verify", f"{l['id']} {dec} {reason}"); flash(f"Listing #{l['id']}: {dec}.", "ok")
        return redirect(back)
    st = request.args.get("status", "Pending"); w, a = ["l.status!='Withdrawn'"], []
    if st != "All": w.append("l.verify_status=?"); a.append(st)
    for k, col in (("district", "l.district"), ("crop", "l.crop")):
        if request.args.get(k) and u["role"] != "extension" or (k == "crop" and request.args.get(k)): w.append(f"{col}=?"); a.append(request.args[k])
    if request.args.get("q"): w.append("(lower(COALESCE(l.village,'')) LIKE ? OR lower(COALESCE(l.sector,'')) LIKE ?)"); a += ["%" + request.args["q"].lower().strip() + "%"] * 2
    rows = Q("SELECT l.*, u.name seller, u.photo seller_photo, u.phone seller_phone FROM listings l JOIN users u ON u.id=l.seller_id WHERE " + " AND ".join(w) + sc + " ORDER BY l.id DESC LIMIT 100", tuple(a) + sa)
    for l in rows: l["checks"] = plausibility(l)
    cnt = {r["verify_status"]: r["c"] for r in Q("SELECT verify_status, COUNT(*) c FROM listings WHERE status!='Withdrawn'" + sc0 + " GROUP BY verify_status", sa0)}
    kpi = Q1("SELECT COALESCE(SUM(verify_status='Pending'),0) pend, COALESCE(SUM(verify_status='Needs visit'),0) visit, COALESCE(SUM(verify_status='Verified'),0) ver, COALESCE(SUM(verify_status='Rejected'),0) rej, COALESCE(SUM(CASE WHEN verify_status='Verified' THEN COALESCE(verified_qty,qty_kg) END),0) kg FROM listings WHERE status!='Withdrawn'" + sc0, sa0)
    fsc, fa = (" AND district=? AND lower(trim(COALESCE(village,'')))=?", (u["district"], u["village"].strip().lower())) if is_advisor(u) else ((" AND district=?", (u["district"],)) if u["role"] == "extension" else ("", ()))
    kpi["farmers"] = Q1("SELECT COUNT(*) c FROM users WHERE role='farmer' AND status='active' AND email NOT LIKE '%@guest.kiza'" + fsc, fa)["c"]
    return render_template("verify.html", kpi=kpi, rows=rows, st=st, f=request.args, cnt=cnt, crops=Q("SELECT name FROM crops ORDER BY name"), ds=Q("SELECT name FROM districts ORDER BY name"), reasons=REJECT_REASONS)

# ---------- village advisors (admin / government create them) ----------
@app.route("/admin/advisors", methods=["GET", "POST"])
@need("admin")
def advisors():
    ds = [d["name"] for d in Q("SELECT name FROM districts ORDER BY name")]
    if request.method == "POST":
        f = request.form
        if f.get("toggle"):
            x = Q1("SELECT * FROM users WHERE id=? AND role='extension'", (f.get("toggle"),))
            if x: X("UPDATE users SET status=? WHERE id=?", ("inactive" if x["status"] == "active" else "active", x["id"])); audit("advisor.toggle", str(x["id"]))
            return redirect("/admin/advisors")
        name, phone, village, sector, dist = f.get("name", "").strip()[:80], norm_phone(f.get("phone")), f.get("village", "").strip()[:60], f.get("sector", "").strip()[:60], f.get("district")
        if not name or not phone or dist not in ds or not village: flash("Enter name, valid phone, district and village.", "err")
        elif Q1("SELECT 1 x FROM users WHERE phone=?", (phone,)): flash("This phone number is already registered.", "err")
        else:
            pw = secrets.token_urlsafe(7)
            X("INSERT INTO users(name,email,phone,pw_hash,role,district,sector,village,lang) VALUES(?,?,?,?,'extension',?,?,?,'rw')", (name, f"p{phone}@phone.kiza", phone, generate_password_hash(pw), dist, sector, village))
            audit("advisor.create", f"{name} {dist}/{village}"); flash(f"Advisor created. Login: {phone} - password: {pw} (shown once, give it to the advisor).", "ok")
        return redirect("/admin/advisors")
    rows = Q("SELECT u.*, (SELECT COUNT(*) FROM listings l WHERE l.district=u.district AND lower(trim(COALESCE(l.village,'')))=lower(trim(u.village)) AND l.verify_status='Pending' AND l.status!='Withdrawn') pending, (SELECT COUNT(*) FROM listings l WHERE l.verified_by=u.id) done FROM users u WHERE role='extension' ORDER BY (COALESCE(village,'')='') , district, village")
    return render_template("advisors.html", rows=rows, ds=ds)

EXPORTS = {
 "listings": "SELECT l.id, l.created_at, u.name farmer, u.phone farmer_phone, l.crop, l.qty_kg, l.available_kg, l.price_kg, l.district, l.sector, l.village, l.status, l.verify_status, v.name confirmed_by, l.verified_at, l.verified_qty, l.visited, l.reject_reason, l.verify_note FROM listings l JOIN users u ON u.id=l.seller_id LEFT JOIN users v ON v.id=l.verified_by ORDER BY l.id DESC",
 "offers": "SELECT o.id, o.created_at, l.crop, o.qty_kg, o.price_kg, o.qty_kg*o.price_kg total_rwf, o.status, o.completed_at, o.rating, s.name seller, b.name buyer, l.district, l.village FROM offers o JOIN listings l ON l.id=o.listing_id JOIN users s ON s.id=l.seller_id JOIN users b ON b.id=o.buyer_id ORDER BY o.id DESC",
 "advisors": "SELECT u.id, u.name, u.phone, u.district, u.sector, u.village, u.status, (SELECT COUNT(*) FROM listings l WHERE l.verified_by=u.id AND l.verify_status='Verified') confirmed, (SELECT COUNT(*) FROM listings l WHERE l.verified_by=u.id AND l.verify_status='Rejected') rejected FROM users u WHERE u.role='extension' ORDER BY u.district, u.village"}
@app.get("/admin/export/<kind>.csv")
@need("admin")
def export_csv(kind):
    if kind not in EXPORTS: abort(404)
    rows = Q(EXPORTS[kind]); out = io.StringIO(); out.write("\ufeff"); wr = csv.writer(out)
    safe = lambda v: ("'" + v) if isinstance(v, str) and v != "" and v[0] in "=+-@\t\r" else ("" if v is None else v)   # spreadsheet formula-injection guard
    if rows: wr.writerow(rows[0].keys()); [wr.writerow([safe(v) for v in r.values()]) for r in rows]
    audit("export", kind); return Response(out.getvalue(), mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment; filename=kiza-{kind}-{TODAY()}.csv"})

# ---------- profile (all roles) ----------
@app.route("/profile", methods=["GET", "POST"])
@need()
def profile():
    u = g.user; ds = Q("SELECT name FROM districts ORDER BY name"); guest_ = u["email"].endswith("@guest.kiza")
    if request.method == "POST":
        f = request.form
        if guest_: flash("Guest accounts cannot be edited. Create a free account first.", "err"); return redirect("/profile")
        name = f.get("name", "").strip()[:80]; phone = norm_phone(f.get("phone")); email = f.get("email", "").strip().lower(); err = None
        if not name: err = "Please enter your name."
        elif not phone: err = "Enter a valid Rwandan phone number."
        elif email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email): err = "That email does not look right."
        elif f.get("district") not in [d["name"] for d in ds]: err = "Choose your district."
        elif Q1("SELECT id FROM users WHERE phone=? AND id!=?", (phone, u["id"])): err = "This phone number belongs to another account."
        elif email and Q1("SELECT id FROM users WHERE email=? AND id!=?", (email, u["id"])): err = "This email belongs to another account."
        new_pw = f.get("new_password", "")
        if not err and new_pw:
            if not check_password_hash(u["pw_hash"], f.get("old_password", "")): err = "Current password is wrong."
            elif len(new_pw) < 8 or not re.search(r"[A-Za-z]", new_pw) or not re.search(r"\d", new_pw): err = "New password needs 8+ characters with letters and numbers."
        try: photo = image_ok("photo", 600) if not err else None
        except ValueError as e: err = str(e); photo = None
        if err: flash(err, "err")
        else:
            X("UPDATE users SET name=?, phone=?, email=?, district=?, sector=?, village=?, bio=?, lang=?, photo=COALESCE(?,photo) WHERE id=?",
              (name, phone, email or u["email"], u["district"] if u["role"] == "extension" else f["district"], u["sector"] if u["role"] == "extension" else f.get("sector", "").strip()[:60], u["village"] if u["role"] == "extension" else f.get("village", "").strip()[:60], f.get("bio", "").strip()[:300], f.get("lang") if f.get("lang") in LANGS else "en", photo, u["id"]))   # advisors cannot move themselves: scope is assigned by admin
            if new_pw: X("UPDATE users SET pw_hash=? WHERE id=?", (generate_password_hash(new_pw), u["id"]))
            session["lang"] = f.get("lang") if f.get("lang") in LANGS else session.get("lang", "en"); audit("profile.update", ""); flash("Profile saved.", "ok"); return redirect("/profile")
    st = Q1("SELECT COUNT(*) n, SUM(verify_status='Verified') v FROM listings WHERE seller_id=?", (u["id"],)); sc = Q1("SELECT COUNT(*) n FROM scans WHERE user_id=?", (u["id"],))["n"]
    done = sum(bool(u.get(k)) for k in ("photo", "phone", "district", "sector", "village", "bio")); return render_template("profile.html", ds=ds, st=st, sc=sc, pct=round(100 * done / 6), guest_=guest_)

@app.get("/u/<int:uid>")
@need()
def public_profile(uid):
    p = Q1("SELECT id,name,role,district,sector,village,bio,photo,created_at FROM users WHERE id=? AND status='active' AND email NOT LIKE '%@guest.kiza'", (uid,))
    if not p: abort(404)
    seeall = g.user["id"] == uid or g.user["role"] in STAFF
    ls = Q("SELECT * FROM listings WHERE seller_id=? AND status IN ('Available','Offer Received','Reserved')" + ("" if seeall else " AND verify_status='Verified'") + " ORDER BY id DESC LIMIT 12", (uid,))
    st = Q1("SELECT COUNT(*) n, COALESCE(SUM(verify_status='Verified'),0) v FROM listings WHERE seller_id=?", (uid,))
    rv = Q("SELECT o.rating, o.review, o.completed_at, b.name buyer FROM offers o JOIN listings l ON l.id=o.listing_id JOIN users b ON b.id=o.buyer_id WHERE l.seller_id=? AND o.rating IS NOT NULL ORDER BY o.id DESC LIMIT 5", (uid,)) if p["role"] == "farmer" else []
    return render_template("public_profile.html", p=p, ls=ls, st=st, deal=deal_stats(uid) if p["role"] == "farmer" else None, rv=rv)

# ---------- crop scanner ----------
SCANS = {}
def _rb(p):
    with open(p, 'rb') as fh: return fh.read()
@app.route("/scan", methods=["GET", "POST"])
@need("farmer", "buyer", "extension", "admin")
def scan():
    u = g.user; crops = [c["name"] for c in Q("SELECT name FROM crops ORDER BY name")]; res = None
    if request.method == "POST":
        ip = request.remote_addr; SCANS[ip] = [t for t in SCANS.get(ip, []) if time.time() - t < 3600]
        if len(SCANS[ip]) >= 30: flash("Too many scans this hour. Please try later.", "err"); return redirect("/scan")
        try:
            img = image_ok("photo")
            if not img: raise ValueError("Please choose or take a photo of the plant leaf.")
            SCANS[ip].append(time.time()); crop = request.form.get("crop", ""); crop = crop if crop in crops else ""
            syms = [s for s in request.form.getlist("sym") if s in disease.SYMPTOMS]; path = os.path.join(UPLOADS, img)
            cs = disease.colour_screen(path); ai = disease.ai_diagnose(_rb(path), crop)
            inferred = [s for s in cs.get("infer", []) if s not in syms]; allsyms = syms + inferred
            cand = disease.rank(crop, allsyms) if crop else []
            res = {"img": img, "crop": crop, "cs": cs, "ai": ai, "syms": syms, "inferred": inferred, "cand": cand, "generic": bool(crop) and crop not in disease.D}
            X("INSERT INTO scans(user_id,image,crop,mode,symptoms,result) VALUES(?,?,?,?,?,?)", (u["id"], img, ai.get("crop") if ai else crop, "ai" if ai else "screen", ",".join(allsyms), json.dumps({"cs": cs, "ai": ai, "cand": [c["name"] for c in cand]})))
            audit("scan", crop or "unknown")
        except ValueError as e: flash(str(e), "err")
    hist = Q("SELECT * FROM scans WHERE user_id=? ORDER BY id DESC LIMIT 6", (u["id"],))
    return render_template("scan.html", crops=crops, res=res, SY=disease.SYMPTOMS, SYR=disease.SYMPTOMS_RW, hist=hist, ai_on=bool(os.environ.get("ANTHROPIC_API_KEY")))

@app.post("/market/<int:lid>/offer")
@need("buyer")
def make_offer(lid):
    import kiza8.inventory as inv
    l = Q1("SELECT * FROM listings WHERE id=?", (lid,))
    try: assert l; q = num("qty_kg", .1, 1e8); pr = num("price_kg", 1, 1e6); inv.create_offer(lid, g.user["id"], q, pr)
    except Exception: flash("Offer not valid: quantity must be within what is available.", "err"); return redirect("/market")
    notify(l["seller_id"], "offer", f"New offer: {q:.0f} kg {l['crop']} at {pr:.0f} RWF/kg from {g.user['name']}.", "/offers"); audit("offer.create", f"listing {lid}")
    flash("Offer sent. The farmer will be notified.", "ok"); return redirect("/offers")

@app.get("/offers")
@need("farmer", "buyer")
def offers():
    if g.user["role"] == "farmer": os_ = Q("SELECT o.*, l.crop, l.price_kg list_price, u.name buyer, u.phone contact FROM offers o JOIN listings l ON l.id=o.listing_id JOIN users u ON u.id=o.buyer_id WHERE l.seller_id=? ORDER BY o.id DESC", (g.user["id"],))
    else: os_ = Q("SELECT o.*, l.crop, l.price_kg list_price, u.name buyer, u.phone contact FROM offers o JOIN listings l ON l.id=o.listing_id JOIN users u ON u.id=l.seller_id WHERE o.buyer_id=? ORDER BY o.id DESC", (g.user["id"],))
    return render_template("offers.html", os=os_)

@app.post("/offers/<int:oid>/<act>")
@need("farmer")
def answer_offer(oid, act):
    import kiza8.inventory as inv
    o = Q1("SELECT o.*, l.seller_id, l.crop FROM offers o JOIN listings l ON l.id=o.listing_id WHERE o.id=?", (oid,))
    if not o or o["seller_id"] != g.user["id"] or act not in ("accept", "reject", "cancel"): abort(403)
    try:
        if act == "accept": inv.accept_offer(oid, g.user["id"]); notify(o["buyer_id"], "offer", f"Your offer for {o['qty_kg']:.0f} kg {o['crop']} was ACCEPTED.", "/offers")
        else: inv.release(oid, g.user["id"], "Rejected" if act == "reject" else "Cancelled"); notify(o["buyer_id"], "offer", f"Your {o['crop']} offer was {'declined' if act == 'reject' else 'cancelled by the seller'}.", "/offers")
    except inv.StockError as e:
        flash("Not enough quantity left." if str(e) == "insufficient" else "This offer can no longer be changed.", "err"); return redirect("/offers")
    audit("offer." + act, str(oid)); flash("Offer " + {"accept": "accepted.", "reject": "declined.", "cancel": "cancelled."}[act], "ok"); return redirect("/offers")

@app.post("/offers/<int:oid>/buyer-cancel")
@need("buyer")
def buyer_cancel_offer(oid):
    import kiza8.inventory as inv
    o = Q1("SELECT o.*, l.seller_id, l.crop FROM offers o JOIN listings l ON l.id=o.listing_id WHERE o.id=?", (oid,))
    if not o or o["buyer_id"] != g.user["id"]: abort(403)
    try: inv.release(oid, g.user["id"], "Cancelled")
    except inv.StockError: flash("This offer can no longer be cancelled.", "err"); return redirect("/offers")
    notify(o["seller_id"], "offer", f"{g.user['name']} cancelled the {o['crop']} offer ({o['qty_kg']:.0f} kg). The quantity is available again.", "/offers"); audit("offer.buyer_cancel", str(oid)); flash("Offer cancelled.", "ok"); return redirect("/offers")

@app.post("/offers/<int:oid>/complete")
@need("buyer")
def complete_offer(oid):
    import kiza8.inventory as inv
    o = Q1("SELECT o.*, l.seller_id, l.crop FROM offers o JOIN listings l ON l.id=o.listing_id WHERE o.id=?", (oid,))
    if not o or o["buyer_id"] != g.user["id"] or o["status"] != "Accepted": abort(403)
    rating = int(num("rating", 1, 5, default=5)); review = request.form.get("review", "").strip()[:300]
    try: inv.complete(oid, g.user["id"], rating, review, TODAY())
    except inv.StockError: abort(403)
    notify(o["seller_id"], "offer", f"Deal completed: {o['qty_kg']:.0f} kg {o['crop']}. {g.user['name']} rated you {rating}/5." + (f" \"{review}\"" if review else ""), "/offers")
    audit("offer.complete", f"{oid} {rating}"); flash("Thank you! Deal completed and the farmer was rated.", "ok"); return redirect("/offers")

# ---------- E-Soko prices ----------
@app.get("/prices")
@need("farmer", "buyer", *STAFF)
def prices():
    crops = Q("SELECT DISTINCT crop name FROM market_prices ORDER BY crop")
    if not crops: return render_template("msg.html", title="No price data yet", msg="An administrator must load crops and market prices first (Data page).")
    crop = request.args.get("crop") or crops[0]["name"]
    trends = Q("SELECT e.*, d.province FROM esoko_prices e JOIN districts d ON d.name=e.district WHERE e.crop=? ORDER BY e.current_price_rwf DESC", (crop,))
    rows = Q("SELECT m.name market, m.district, m.lat, m.lng, p.day, p.price_kg FROM market_prices p JOIN markets m ON m.id=p.market_id WHERE p.crop=? ORDER BY p.day", (crop,))
    days = sorted({r["day"] for r in rows}); origin = Q1("SELECT * FROM districts WHERE name=?", (g.user["district"],)); cmp = []
    if days:
        for m in [r for r in rows if r["day"] == days[-1]]:
            ok = origin and None not in (origin["lat"], origin["lng"], m["lat"], m["lng"]); km = rules.haversine(origin["lat"], origin["lng"], m["lat"], m["lng"]) if ok else None
            cmp.append(dict(m, km=round(km) if ok else "n/a", net=m["price_kg"] - rules.KM_COST * (km or 0)))
        cmp.sort(key=lambda x: -x["net"])
    series = [sum(r["price_kg"] for r in rows if r["day"] == d) / len([r for r in rows if r["day"] == d]) for d in days]
    gaps = [(dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days for a, b in zip(days, days[1:])]; weekly = bool(gaps) and statistics.median(gaps) <= 10
    fc = mlclient.call("/ml/price-forecast", {"crop": crop, "prices": series}) if len(series) >= 4 and weekly else None
    age = (dt.date.today() - dt.date.fromisoformat(days[-1])).days if days else None
    srcs = [r["source"] for r in Q("SELECT DISTINCT source FROM market_prices WHERE crop=?", (crop,))]
    return render_template("prices.html", crop=crop, crops=crops, trends=trends, cmp=cmp[:8], series=series, fc=fc if mlclient.valid_forecast(fc) else None, mine=g.user["district"], asof=days[-1] if days else None, age=age, srcs=srcs, weekly=weekly)

# ---------- soil + live data fusion ----------
@app.get("/soil")
@need("farmer", "extension", "admin")
def soil():
    d = request.args.get("district") or g.user["district"]; p = Q1("SELECT * FROM soil_profiles WHERE district=?", (d,)); wx = wx3(d)
    return render_template("soil.html", d=d, p=p, tips=rules.field_advice(p, wx), wx=wx, ds=Q("SELECT name FROM districts ORDER BY name"), allp=Q("SELECT * FROM soil_profiles ORDER BY district"))

@app.get("/api/live/<district>")
@need()
def live_api(district):
    d = Q1("SELECT name FROM districts WHERE lower(name)=lower(?)", (district,)) or abort(404); p = Q1("SELECT * FROM soil_profiles WHERE district=?", (d["name"],)); wx = wx3(d["name"])
    return jsonify(district=d["name"], weather=wx, soil=p, advice=[{"level": k, "text": t} for k, t in rules.field_advice(p, wx)],
                   prices=Q("SELECT crop, current_price_rwf, predicted_trend, change_pct, as_of FROM esoko_prices WHERE district=? ORDER BY crop", (d["name"],)))

@app.get("/notifications")
@need()
def notifications():
    ns = Q("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50", (g.user["id"],)); X("UPDATE notifications SET is_read=1 WHERE user_id=?", (g.user["id"],))
    return render_template("notifications.html", ns=ns)

# ---------- government: Imihigo command center ----------
def imihigo_data():
    ds = Q("SELECT name, province, lat, lng FROM districts ORDER BY name"); tg = Q("SELECT district, crop, target_ha FROM imihigo_targets ORDER BY crop")
    act = {(r["district"], r["crop"]): r["ha"] for r in Q("SELECT fa.district, f.crop, SUM(f.size_ha) ha FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE f.status IN ('Planted','Growing','Flowering','Harvesting','Harvested') GROUP BY fa.district, f.crop")}
    out = []
    for d in ds:
        rows = [{"crop": t["crop"], "target": t["target_ha"], "actual": round(act.get((d["name"], t["crop"]), 0), 1), "pct": round(act.get((d["name"], t["crop"]), 0) / t["target_ha"] * 100)} for t in tg if t["district"] == d["name"]]
        T, A = sum(r["target"] for r in rows), sum(r["actual"] for r in rows); pct = round(A / T * 100) if T else None
        out.append(dict(d, rows=rows, target=T, actual=round(A, 1), pct=pct, color="#9aa5a0" if pct is None else "#2e9e5b" if pct >= 90 else "#e6a118" if pct >= 60 else "#d64545",
                        distress=Q1("SELECT COUNT(*) c FROM distress_reports WHERE district=? AND status!='Resolved'", (d["name"],))["c"]))
    return out

@app.get("/imihigo")
@need("government", "admin")
def imihigo(): return render_template("imihigo.html", D=imihigo_data(), has_leaflet=os.path.exists(os.path.join(app.root_path, "static", "vendor", "leaflet", "leaflet.js")))

@app.get("/api/imihigo")
@need("government", "admin")
def imihigo_api(): return jsonify(imihigo_data())

@app.route("/rules", methods=["GET", "POST"])
@need("extension", "admin")
def rules_page():
    if request.method == "POST" and request.form.get("id"):
        X("UPDATE fertilizer_subsidies SET approval='approved', approved_by=?, source=? WHERE id=?", (g.user["id"], (request.form.get("source") or "Approved by officer")[:160], request.form["id"]))
        audit("subsidy.approve", request.form["id"]); flash("Approved.", "ok"); return redirect("/rules")
    return render_template("rules.html", rs=Q("SELECT * FROM fertilizer_subsidies ORDER BY crop, stage"))

@app.route("/admin/data", methods=["GET", "POST"])
@need("admin")
def admin_data():
    if request.method == "POST":
        kind = request.form.get("kind"); fl = request.files.get("file")
        if kind in ("prices", "soil"):
            started = sync.start_async(kind); audit("sync." + kind, "started" if started else "already running")
            flash(f"{'Started' if started else 'Already running'}: {kind} sync. It runs in the background (soil takes ~6 minutes because the provider limits requests). Reload this page to see the result.", "ok")
        elif kind == "weather":
            ok, fail = weather_live.refresh(_c()); audit("weather.refresh", f"{len(ok)} ok, {len(fail)} failed"); sync.log("weather", "ok" if ok and not fail else "partial" if ok else "failed", f"{len(ok)} districts updated" + (f", {len(fail)} failed" if fail else ""))
            flash(f"Live weather updated for {len(ok)} districts." + (f" Failed: {', '.join(n for n, _ in fail[:6])} ({fail[0][1]}). Check internet; old data kept." if fail else ""), "err" if fail else "ok")
        elif kind in loaders.KINDS and fl and fl.filename.lower().endswith((".csv", ".xlsx")):
            try:
                raw = fl.stream.read(); text = loaders.xlsx_to_csv(raw) if fl.filename.lower().endswith(".xlsx") else raw.decode("utf-8-sig"); r = loaders.load(kind, text, g.user["id"], _c())
            except Exception: r = {"ok": 0, "bad": 0, "issues": [(1, "could not read the file (use UTF-8 CSV or .xlsx)")]}
            audit("dataset.upload", f"{kind}: {r['ok']} ok, {r['bad']} rejected"); flash(f"{kind}: {r['ok']} rows loaded, {r['bad']} rejected." + "".join(f" [row {i}: {m}]" for i, m in r["issues"][:4]), "ok" if not r["bad"] else "err")
        else: flash("Choose a dataset and a .csv or .xlsx file.", "err")
        return redirect("/admin/data")
    w = Q1("SELECT COUNT(*) n, MAX(fetched_at) last, SUM(is_demo) demo FROM weather")
    syncs = {r["kind"]: r for r in Q("SELECT * FROM sync_log WHERE id IN (SELECT MAX(id) FROM sync_log GROUP BY kind)")}
    return render_template("data.html", syncs=syncs, running=sorted(sync.RUNNING), auto=sync.AUTO, kinds=loaders.KINDS, help=loaders.HELP, cnt={k: Q1(f"SELECT COUNT(*) c FROM {k}")["c"] for k in loaders.KINDS}, w=w, logs=Q("SELECT * FROM data_quality_logs ORDER BY id DESC LIMIT 15"))

@app.get("/admin/template/<kind>.csv")
@need("admin")
def template_csv(kind):
    if kind not in loaders.KINDS: abort(404)
    return Response(",".join(loaders.KINDS[kind]) + "\n", mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={kind}_template.csv"})

@app.get("/audit")
@need("admin")
def audit_page(): return render_template("audit.html", logs=Q("SELECT a.*, u.email FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 100"))


# ---------- USSD (feature-phone access) ----------
USSD_HITS, SIM_HITS = {}, {}
def _rate(store, key, n, per=60):
    now = time.time()
    if len(store) > 5000: store.clear()
    h = [t for t in store.get(key, []) if now - t < per]; h.append(now); store[key] = h; return len(h) > n

@app.post("/ussd")
def ussd_gateway():
    """Gateway callback (Africa's Talking style: sessionId, phoneNumber, text). Set KIZA_USSD_TOKEN and give the gateway the URL /ussd?token=...; without a token the endpoint is
    read-only (prices, weather, soil, crop tips) and farmer reports are switched off, because the phone number is the identity."""
    tok = os.environ.get("KIZA_USSD_TOKEN", "")
    if tok and not hmac.compare_digest(tok, request.values.get("token", "") or request.headers.get("X-Kiza-Token", "")): return Response("END Unauthorized", 403, mimetype="text/plain")
    ph = norm_phone(request.form.get("phoneNumber"))
    if _rate(USSD_HITS, ph or request.remote_addr, 40): return Response("END Too many requests. Try again in a minute.", mimetype="text/plain")
    c = db.conn()
    try: out = ussd.handle((request.form.get("text") or "")[:200], ph, c, write=bool(tok))
    except Exception as e: logging.exception(e); out = "END Service error. Please try again."
    finally: c.close()
    return Response(out, mimetype="text/plain")

CROP_RW = {"ibirayi": "Potato", "ibigori": "Maize", "ibishyimbo": "Beans", "imyumbati": "Cassava", "umuceri": "Rice", "inyanya": "Tomato", "ibijumba": "Sweet potato", "ibitoki": "Banana (cooking)",
 "ibitunguru": "Onion", "amashu": "Cabbage", "ubunyobwa": "Groundnut", "ingano": "Wheat", "amasaka": "Sorghum", "ikawa": "Coffee (Arabica)", "icyayi": "Tea (green leaf)", "soya": "Soybean",
 "amashaza": "Garden peas", "karoti": "Carrot", "avoka": "Avocado", "imyembe": "Mango", "inanasi": "Pineapple", "amatunda": "Passion fruit", "ibihaza": "Pumpkin", "dodo": "Amaranth",
 "isombe": "Cassava leaves", "urutoki": "Banana (cooking)"}
def _has(m, *ws):
    """True if any keyword occurs in m. Short keywords (<=3 letters: hi, ph, dap, npk) must be whole words, so 'photo' is not 'ph' and 'which' is not 'hi'."""
    return any((re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", m) if len(w) <= 3 else w in m) for w in ws)

def find_crop(m):
    """Catalogue crop named in the message as a whole word (longest name first, so 'sweet potato' beats 'potato'; 'price' never matches 'rice')."""
    names = sorted((c["name"] for c in Q("SELECT name FROM crops")), key=len, reverse=True)
    for n in names:
        if re.search(r"(?<![a-z])" + re.escape(n.lower()) + r"s?(?![a-z])", m): return n
    return next((v for k, v in sorted(CROP_RW.items(), key=lambda kv: -len(kv[0])) if re.search(r"(?<![a-z])" + re.escape(k), m)), None)
def _assistant_base(msg, u, lang):
    m = msg.lower().strip(); rw = lang == "rw" or _has(m, "ibiciro", "igiciro", "ifumbire", "ikirere", "nigute", "ndashaka", "mfasha", "murakoze", "muraho", "amakuru", "gurisha", "umusaruro", "ubutaka", "ubufasha")
    L = lambda en, kr: kr if rw else (FRL.get(en, en) if lang == "fr" else en)
    dist = next((d["name"] for d in Q("SELECT name FROM districts") if d["name"].lower() in m), None) or (u["district"] if u else "Musanze")
    crop = find_crop(m)
    chips = [L("Potato price", "Igiciro cy'ibirayi"), L("Weather today", "Ikirere uyu munsi"), L("Fertilizer help", "Ifumbire"), L("Contact support", "Vugana n'ubufasha")]
    if _has(m, "hello", "hi", "muraho", "mwaramutse", "bonjour", "amakuru") and len(m) < 25:
        return L("Hello! I am the KIZA-AGRI assistant. Ask me about prices, weather, soil, fertilizer or how to use the platform.", "Muraho! Ndi umufasha wa KIZA-AGRI. Mbaza ku biciro, ikirere, ubutaka, ifumbire cyangwa uko wakoresha urubuga."), [], chips
    if _has(m, "price", "igiciro", "ibiciro", "cost of", "how much", "angahe"):
        q = "SELECT * FROM esoko_prices WHERE district=?" + (" AND crop=?" if crop else "") + " ORDER BY crop"; r = Q(q, (dist, crop) if crop else (dist,))
        if r:
            tx = "; ".join(f"{x['crop']}: {x['current_price_rwf']:.0f} RWF/kg ({x['predicted_trend']}, {x['change_pct']:+.1f}%)" for x in r[:4])
            return L(f"Latest prices in {dist}: {tx}. Source: E-Soko pipeline (latest published data, not a live tick).", f"Ibiciro bya vuba i {dist}: {tx}. Inkomoko: E-Soko (amakuru aheruka gutangazwa)."), [{"l": L("Open price page", "Fungura ibiciro"), "h": "/prices" + (f"?crop={crop}" if crop else "")}], chips
        ap = avg_prices()
        if ap and (not crop or crop in ap): return L("Average market prices: ", "Ibiciro bisanzwe ku isoko: ") + ", ".join(f"{k} {v:.0f} RWF/kg" for k, v in ap.items() if not crop or k == crop), [{"l": L("Open price page", "Fungura ibiciro"), "h": "/prices"}], chips
        return L("No price data is loaded yet. An administrator must load market prices.", "Nta makuru y'ibiciro arashyirwaho. Umuyobozi agomba kuyashyiraho."), [], chips
    if _has(m, "weather", "rain", "ikirere", "imvura", "forecast", "spray"):
        wx = wx3(dist)
        if wx: return L(f"Forecast advice for {dist}: ", f"Inama z'ikirere i {dist}: ") + " ".join(t for _, t in rules.weather_advice(wx)), [{"l": L("Full weather", "Ikirere cyose"), "h": "/weather"}], chips
        return L("No weather data for this district yet.", "Nta makuru y'ikirere kuri ako karere."), [], chips
    if _has(m, "soil", "ubutaka", "ph", "lime"):
        p = Q1("SELECT * FROM soil_profiles WHERE district=?", (dist,))
        if p: return L(f"{dist} soil: {p['soil_type'] or 'n/a'}, pH {p['ph_level']}. Likely limiting nutrient: {p['main_nutrient_deficit'] or 'n/a'}. Suggested: {p['recommended_fertilizer'] or 'n/a'}. This is a screening estimate, not a lab test.", f"Ubutaka bw'i {dist}: {p['soil_type'] or '-'}, pH {p['ph_level']}. Intungamubiri nkeya: {p['main_nutrient_deficit'] or '-'}. Inama: {p['recommended_fertilizer'] or '-'}. Ni igereranya, si ibipimo bya laboratwari."), [{"l": L("Soil page", "Ubutaka"), "h": "/soil"}], chips
    if _has(m, "fertili", "ifumbire", "nkunganire", "subsid", "dap", "urea", "npk"):
        return L("The Nkunganire engine calculates kg needed and compares open-market vs subsidized cost, so you see your saving. Open it, pick your crop and field size.", "Nkunganire ibara ifumbire ukeneye n'igiciro ku isoko risanzwe ugereranyije na Nkunganire, ukabona ayo wizigamira. Hitamo igihingwa n'ubuso bw'umurima."), [{"l": L("Fertilizer calculator", "Kubara ifumbire"), "h": "/fertilizer" if u and u["role"] in ("farmer",) else "/rules"}], chips
    if _has(m, "what to plant", "which crop", "crop", "plant", "gihinga", "igihingwa", "ibihingwa", "ndahinga", "advisor", "inama"):
        return L("The Crop Advisor scores each crop for your farm (temperature, rain, soil pH, season) and shows the reasons and risks.", "Inama ku bihingwa zitanga amanota ku gihingwa cyose ku murima wawe (ubushyuhe, imvura, pH, igihembwe) zikanagaragaza impamvu n'ingaruka."), [{"l": L("Open Crop Advisor", "Fungura inama"), "h": "/advisor"}], chips
    if _has(m, "scan", "disease", "sick", "pest", "leaf", "irwaye", "indwara", "ibyonnyi", "amababi", "kirwaye"):
        return L("Use the Crop Scanner: upload a photo of the leaf, pick your crop and symptoms, and get likely problems with simple advice. Always confirm with your extension officer.", "Koresha Scanner y'ibihingwa: shyiraho ifoto y'ikibabi, uhitemo igihingwa n'ibimenyetso, ubone ibishoboka n'inama yoroshye. Buri gihe emeza n'umukozi w'ubuhinzi."), [{"l": L("Open scanner", "Fungura scanner"), "h": "/scan"}], chips
    if _has(m, "verif", "kwemeza", "check farmer", "true", "lying"):
        return L("Officers verify each harvest listing: photo, GPS location, village and a check against the farmer's registered fields. Verified listings show a green badge.", "Abakozi bemeza buri musaruro: ifoto, aho uri, umudugudu no kugereranya n'imirima yanditse. Ibyemejwe bifite ikimenyetso kibisi."), [{"l": L("Marketplace", "Isoko"), "h": "/market"}], chips
    if _has(m, "sell", "buyer", "offer", "market", "gurisha", "umuguzi", "isoko", "umusaruro"):
        return L("Farmers list their harvest in the Marketplace; buyers send offers; the phone number is shared only after you accept an offer.", "Abahinzi bashyira umusaruro mu Isoko; abaguzi bohereza ibyifuzo; telefone isangizwa nyuma yo kwemera icyifuzo."), [{"l": L("Marketplace", "Isoko"), "h": "/market"}], chips
    if _has(m, "distress", "glut", "spoil", "problem", "ikibazo", "report", "menyesha"):
        return L("Use 'Report a problem' to tell the government about gluts, price manipulation or spoilage. Officers triage it and you get notified.", "Koresha 'Menyesha ikibazo' ubwire Leta ibyerekeye umusaruro mwinshi, ibiciro bibangamira cyangwa kubora. Uzamenyeshwa uko bigenda."), [{"l": L("Report a problem", "Menyesha ikibazo"), "h": "/distress"}], chips
    if _has(m, "guest", "umushyitsi", "register", "sign up", "account", "konti", "login", "injira", "iyandikishe"):
        return L("Create a free account with just your phone number, or log in.", "Fungura konti y'ubuntu ukoresheje telefone gusa, cyangwa winjire."), [{"l": L("Register", "Iyandikishe"), "h": "/register"}, {"l": L("Login", "Injira"), "h": "/login"}], chips
    if _has(m, "contact", "support", "help", "human", "agent", "ubufasha", "vugana", "telefone"):
        return L("Our support team reads every message. Send yours and we will answer.", "Itsinda ryacu ry'ubufasha risoma ubutumwa bwose. Ohereza ubwawe turagusubiza."), [{"l": L("Contact support", "Vugana n'ubufasha"), "h": "/contact"}], chips
    return L("I can help with prices, weather, soil, fertilizer, crop advice, selling and reporting problems. Try one of the buttons, or contact support for anything else.", "Nshobora gufasha ku biciro, ikirere, ubutaka, ifumbire, inama ku bihingwa, kugurisha no kumenyesha ibibazo. Hitamo kimwe, cyangwa uvugane n'ubufasha."), [{"l": L("Contact support", "Vugana n'ubufasha"), "h": "/contact"}], chips

def assistant_reply(msg, u, lang):
    """Works for every account type (guest, farmer, buyer, advisor, government, admin). Signed-in users also get answers about THEIR own data."""
    m = msg.lower().strip(); real = bool(u and not u["email"].endswith("@guest.kiza"))
    rw = lang == "rw" or _has(m, "yanjye", "wanjye", "ibyanjye"); P = lambda en, kr, fr_: kr if rw else (fr_ if lang == "fr" else en)
    if real:
        chips2 = [P("My listings", "Imyaka nashyizeho", "Mes annonces"), P("My offers", "Ibyifuzo byanjye", "Mes offres"), P("Weather today", "Ikirere uyu munsi", "Météo du jour"), P("Contact support", "Vugana n'ubufasha", "Contacter l'assistance")]
        if _has(m, "my listing", "my harvest", "my crops for sale", "imyaka nashyizeho", "umusaruro wanjye", "imyaka yanjye", "mes annonces", "ma récolte", "ma recolte"):
            if u["role"] == "farmer":
                c = {r["verify_status"]: r["c"] for r in Q("SELECT verify_status, COUNT(*) c FROM listings WHERE seller_id=? AND status!='Withdrawn' GROUP BY verify_status", (u["id"],))}
                if not c: return P("You have no listings yet. Add one in the Marketplace: crop, kg, price and village.", "Nta musaruro urashyiraho. Shyiraho mu Isoko: igihingwa, kg, igiciro n'umudugudu.", "Vous n'avez pas encore d'annonce. Ajoutez-en une sur le Marché : culture, kg, prix et village."), [{"l": P("Marketplace", "Isoko", "Marché"), "h": "/market"}], chips2
                return P(f"Your listings: {c.get('Verified',0)} verified (visible to buyers), {c.get('Pending',0)} waiting for the advisor visit, {c.get('Needs visit',0)} visit planned, {c.get('Rejected',0)} rejected.", f"Imyaka yawe: {c.get('Verified',0)} yemejwe (abaguzi barayibona), {c.get('Pending',0)} itegereje gusurwa, {c.get('Needs visit',0)} igomba gusurwa, {c.get('Rejected',0)} yanzwe.", f"Vos annonces : {c.get('Verified',0)} vérifiées (visibles aux acheteurs), {c.get('Pending',0)} en attente de visite, {c.get('Needs visit',0)} visite prévue, {c.get('Rejected',0)} refusées."), [{"l": P("Open my listings", "Fungura imyaka yanjye", "Mes annonces"), "h": "/market"}], chips2
        if _has(m, "my offer", "ibyifuzo byanjye", "mes offres", "offers waiting", "ibyifuzo"):
            if u["role"] == "farmer": n = Q1("SELECT COUNT(*) c FROM offers o JOIN listings l ON l.id=o.listing_id WHERE l.seller_id=? AND o.status='Pending'", (u["id"],))["c"]
            elif u["role"] == "buyer": n = Q1("SELECT COUNT(*) c FROM offers WHERE buyer_id=? AND status='Pending'", (u["id"],))["c"]
            else: n = None
            if n is not None: return P(f"You have {n} offer(s) waiting for an answer.", f"Ufite ibyifuzo {n} bitegereje igisubizo.", f"Vous avez {n} offre(s) en attente de réponse."), [{"l": P("Open offers", "Fungura ibyifuzo", "Voir les offres"), "h": "/offers"}], chips2
        if _has(m, "my field", "my farm", "imirima yanjye", "mes champs", "mon exploitation") and u["role"] == "farmer":
            r = Q("SELECT f.crop, SUM(f.size_ha) ha FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=? GROUP BY f.crop", (u["id"],))
            if not r: return P("No fields yet. Register your farm first.", "Nta mirima iraboneka. Banza wandike umurima wawe.", "Aucun champ. Enregistrez d'abord votre exploitation."), [{"l": P("My farms", "Imirima yanjye", "Mes exploitations"), "h": "/farms"}], chips2
            return P("Your fields: ", "Imirima yawe: ", "Vos champs : ") + ", ".join(f"{x['crop']} {x['ha']:g} ha" for x in r), [{"l": P("My farms", "Imirima yanjye", "Mes exploitations"), "h": "/farms"}], chips2
        if _has(m, "to verify", "waiting for me", "pending visit", "bitegereje", "kwemeza", "à vérifier", "a verifier", "en attente") and u["role"] in STAFF:
            n = _pv(u); return P(f"{n} harvest(s) are waiting for your visit and confirmation.", f"Imyaka {n} itegereje ko uyisura ukayemeza.", f"{n} récolte(s) attendent votre visite et confirmation."), [{"l": P("Open verification", "Fungura kwemeza", "Ouvrir la vérification"), "h": "/verify"}], chips2
        if _has(m, "notification", "ibimenyetso", "nouveau", "new messages"):
            n = Q1("SELECT COUNT(*) c FROM notifications WHERE user_id=? AND is_read=0", (u["id"],))["c"]; return P(f"You have {n} unread notification(s).", f"Ufite ibimenyetso {n} utarasoma.", f"Vous avez {n} notification(s) non lue(s)."), [{"l": P("Open notifications", "Fungura ibimenyetso", "Notifications"), "h": "/notifications"}], chips2
    return _assistant_base(msg, u, lang)

ASSIST_HITS = {}
@app.post("/api/assistant")
def assistant_api():
    """v10: open to everyone (anonymous, guest and every signed-in role). Claude + web search when ANTHROPIC_API_KEY is set, sourced offline answers otherwise."""
    from kiza8 import assistant as AS
    u_ = me(); lg = session.get("lang", "en"); who = f"u{u_['id']}" if u_ else (request.remote_addr or "anon")
    if _rate(ASSIST_HITS, who, 25 if u_ else 12):
        return jsonify(reply=tl("You are asking very fast. Please wait a minute.", "Urabaza vuba cyane. Tegereza umunota umwe.", "Vous allez trop vite. Patientez une minute."), links=[], chips=[])
    msg = (request.form.get("q") or "")[:400]
    if not msg.strip(): return jsonify(reply="…", links=[], chips=[])
    try: hist = json.loads(request.form.get("h") or "[]")[-6:]
    except Exception: hist = []
    try:
        out = AS.reply(msg, u_, lg, hist if isinstance(hist, list) else [], (Q, Q1, wx3, rules), lambda m, u, l: assistant_reply(m, u, l), who)
        out.setdefault("chips", [])
    except Exception as e:
        logging.exception(e)
        out = dict(reply=tl("Sorry, I could not answer that. Please try another question or contact support.", "Mbabarira, ntabashije kubisubiza. Ongera ubaze ukundi cyangwa uvugane n'ubufasha.", "Désolé, je n'ai pas pu répondre. Essayez autre chose ou contactez l'assistance."),
                   links=[{"l": tl("Contact support", "Vugana n'ubufasha", "Contacter l'assistance"), "h": "/contact"}], chips=[], ai=False)
    return jsonify(out)

REF_CACHE = {}
def ref_prices():
    p = os.path.join(app.root_path, "data", "reference_prices_kigali_2026.csv")
    if p not in REF_CACHE:
        import csv
        with open(p, encoding="utf-8") as f: REF_CACHE[p] = [dict(r, price_low_rwf=int(r["price_low_rwf"]), price_high_rwf=int(r["price_high_rwf"])) for r in csv.DictReader(f)]
    return REF_CACHE[p]

@app.get("/reference-prices")
def reference_prices():
    """Public food price reference (Kigali markets, Oct 2026) + MAGIC basket calculator. Indicative, team-compiled: not official NISR figures."""
    rows = ref_prices(); cats = list(dict.fromkeys(r["category"] for r in rows))
    return render_template("refprices.html", rows=rows, cats=cats, src=rows[0]["source"] if rows else "")

TICKETS = {}
@app.route("/contact", methods=["GET", "POST"])
def contact():
    u = me(); real = u and not u["email"].endswith("@guest.kiza")
    if request.method == "POST":
        ip = request.remote_addr; TICKETS[ip] = [t for t in TICKETS.get(ip, []) if time.time() - t < 3600]
        f = request.form; name = f.get("name", "").strip()[:80]; con = f.get("contact", "").strip()[:80]; msg = f.get("message", "").strip()[:2000]
        if len(TICKETS[ip]) >= 5: flash("Too many messages. Please try again later.", "err")
        elif not name or not con or len(msg) < 5: flash("Please enter your name, a phone or email, and a message.", "err")
        else:
            TICKETS[ip].append(time.time())
            tid = X("INSERT INTO tickets(user_id,name,contact,topic,message,ip) VALUES(?,?,?,?,?,?)", (u["id"] if real else None, name, con, f.get("topic", "General")[:40], msg, ip))
            for s in Q("SELECT id FROM users WHERE role IN ('admin','extension') AND status='active'"): notify(s["id"], "support", f"New support message #{tid} from {name}", "/support/inbox")
            flash("Thank you! Your message was sent. We will contact you soon.", "ok"); return redirect("/contact")
    return render_template("contact.html", prefill=(u if real else None), f=request.form)

@app.get("/support")
def support(): return render_template("support.html")
@app.get("/about")
def about(): return render_template("about.html")

@app.route("/support/inbox", methods=["GET", "POST"])
@need("admin")
def support_inbox():
    if request.method == "POST":
        X("UPDATE tickets SET status=? WHERE id=?", ("Resolved" if request.form.get("s") == "Resolved" else "Reviewing", request.form.get("id"))); return redirect("/support/inbox")
    return render_template("tickets.html", ts=Q("SELECT * FROM tickets ORDER BY (status='Resolved'), id DESC LIMIT 200"))

@app.get("/manifest.webmanifest")
def manifest():
    return Response(json.dumps({"name": "KIZA-AGRI", "short_name": "KIZA", "description": "Grow Smarter. Sell Better. Plan Together.", "start_url": "/", "scope": "/", "display": "standalone", "orientation": "portrait",
        "background_color": "#0b3d24", "theme_color": "#0b3d24", "icons": [{"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"}, {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]}), mimetype="application/manifest+json")
@app.get("/sw.js")
def sw():
    r = send_from_directory(os.path.join(app.root_path, "static"), "sw.js", mimetype="application/javascript"); r.headers["Service-Worker-Allowed"] = "/"; r.headers["Cache-Control"] = "no-cache"; return r
@app.get("/favicon.ico")
def favicon(): return redirect("/static/icon-192.png", 301)
@app.get("/offline")
def offline(): return render_template("msg.html", title="Offline", msg="No internet connection. Check your network and try again.")

@app.post("/market/<int:lid>/price")
@need("farmer")
def edit_price(lid):
    l = Q1("SELECT * FROM listings WHERE id=? AND seller_id=? AND status IN ('Available','Offer Received')", (lid, g.user["id"]))
    try: assert l; pr = num("price_kg", 1, 1e6)
    except Exception: flash("Enter a valid price.", "err"); return redirect("/market")
    X("UPDATE listings SET price_kg=? WHERE id=?", (pr, lid)); audit("listing.price", f"{lid} {pr}"); flash("Price updated.", "ok"); return redirect("/market")

@app.route("/admin/users", methods=["GET", "POST"])
@need("admin")
def admin_users():
    if request.method == "POST":
        t = Q1("SELECT * FROM users WHERE id=?", (request.form.get("id"),)); act = request.form.get("act")
        if not t or t["id"] == g.user["id"] or (t["role"] == "admin" and g.user["role"] != "admin"): abort(403)
        if act == "toggle":
            st = "blocked" if t["status"] == "active" else "active"; X("UPDATE users SET status=? WHERE id=?", (st, t["id"])); audit("user." + st, str(t["id"])); flash(f"{t['name']}: {st}.", "ok")
        elif act == "reset":
            pw = secrets.token_urlsafe(6).replace("-", "x").replace("_", "y") + "7"; X("UPDATE users SET pw_hash=? WHERE id=?", (generate_password_hash(pw), t["id"])); audit("user.reset", str(t["id"]))
            flash(f"Temporary password for {t['name']} ({t['phone'] or t['email']}): {pw} - shown once, ask the user to change it in Profile.", "ok")
        return redirect(request.referrer or "/admin/users")
    q = request.args.get("q", "").strip().lower(); role = request.args.get("role", ""); w, a = ["email NOT LIKE '%@guest.kiza'"], []
    if q: w.append("(lower(name) LIKE ? OR phone LIKE ? OR lower(email) LIKE ? OR lower(COALESCE(village,'')) LIKE ?)"); a += ["%" + q + "%"] * 4
    if role in ("farmer", "buyer", "extension", "government", "admin"): w.append("role=?"); a.append(role)
    return render_template("users.html", rows=Q("SELECT id,name,phone,email,role,district,sector,village,status,created_at FROM users WHERE " + " AND ".join(w) + " ORDER BY id DESC LIMIT 100", tuple(a)), f=request.args)

@app.get("/health")
def health(): return {"app": "ok", "ml_service": "up" if mlclient.call("/health") else "down (core features still work)"}

import kiza8
kiza8.init_app(app)

if __name__ == "__main__":
    if sync.start_background(): print("Live-data auto-refresh ON (weather 3 h, prices daily, soil monthly). Disable with KIZA_AUTO_SYNC=0.")
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)
