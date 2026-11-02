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

_DEMO = os.environ.get("KIZA_DEMO") == "1" or (bool(os.environ.get("RENDER")) and os.environ.get("KIZA_DEMO") != "0")
if not os.path.exists(db.DB) and not _DEMO: db.init_real()
else: db.init()

HOME = {"farmer": "/farmer", "buyer": "/buyer", "extension": "/advisor/home", "government": "/gov", "admin": "/admin"}
STAFF = ("extension", "government", "admin")
TODAY = lambda: str(dt.date.today())
UPLOADS = os.environ.get("KIZA_UPLOADS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads"))

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
    if request.method == "POST" and request.path in ("/ussd", "/api/assistant", "/api/v8/sms/dlr", "/login", "/register"): return None   
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
    
    farm = next((f for f in fs if str(f["id"]) == request.args.get("farm")), fs[0])
    season = request.args.get("season", "2026B")
    wx = wx3(farm["district"])
    crops = Q("SELECT * FROM crops")
    
    if not crops: return render_template("msg.html", title="Crop data not loaded yet", msg="An administrator must load the crops dataset first (Data page).")
    
    res = rules.advise(crops, farm, wx[0] if wx else None, avg_prices())
    for r in res: r["luc"], r["luc_crop"] = luc(farm["district"], farm["sector"], r["crop"])
    mand = next((r["luc_crop"] for r in res if r["luc_crop"]), None)
    
    return render_template("advisor.html", farms=fs, farm=farm, res=res, top=res[0] if res else None, mand=mand, wx=wx[0] if wx else None, season=season)

@app.get("/export-advisor-pdf")
@need("farmer")
def export_advisor_pdf():
    farm_id = request.args.get("farm", type=int)
    season = request.args.get("season", "2026B")
    farm = Q1("SELECT * FROM farms WHERE id=? AND user_id=?", (farm_id, g.user["id"]))
    if not farm: abort(404)
    
    output = io.BytesIO()
    report_text = f"KIZA-AGRI CROP ADVISOR REPORT\nFarm: {farm['name']} ({farm['district']}/{farm['sector']})\nSize: {farm['size_ha']} ha\nSeason: {season}\nGenerated for: {g.user['name']}"
    output.write(report_text.encode('utf-8'))
    output.seek(0)
    return Response(output, mimetype="text/plain", headers={"Content-Disposition": f"attachment;filename=kiza_advisor_{farm['name']}.txt"})

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
    if not request.args.get("future"): w += " AND (l.harvest_date IS NULL OR l.harvest_date<=date('now'))"
    if request.args.get("q"): w += " AND (lower(COALESCE(l.village,'')) LIKE ? OR lower(COALESCE(l.sector,'')) LIKE ?)"; a += ["%" + request.args["q"].lower().strip() + "%"] * 2
    if request.args.get("verified") or u["role"] == "buyer": w += " AND l.verify_status='Verified'"
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
        X("INSERT OR IGNORE INTO watches(user_id,crop,district) VALUES(?,?,?)", (g.user["id"], crop, dist)); flash("Alert saved.", "ok")
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
        for s in adv or Q("SELECT id FROM users WHERE role='extension' AND status='active' AND district=?", (g.user["district"],)): notify(s["id"], "verify", f"New harvest to confirm: {q:.0f} kg {crop} in {village}.", "/verify")
        audit("listing.create", f"{crop} {q}kg {village}")
        flash("Listed successfully!", "ok")
    except ValueError as e: flash(str(e), "err")
    except Exception: flash("Check your listing details.", "err")
    return redirect("/market")

@app.post("/market/<int:lid>/cancel")
@need("farmer")
def cancel_listing(lid):
    l = Q1("SELECT * FROM listings WHERE id=? AND seller_id=?", (lid, g.user["id"]))
    if not l: abort(403)
    X("UPDATE listings SET status='Withdrawn' WHERE id=?", (lid,)); flash("Listing withdrawn.", "ok"); return redirect("/market")

# ---------- harvest verification ----------
REJECT_REASONS = ["Crop not found at the farm", "Quantity far below what was claimed", "Different crop from the one listed", "Crop is not ready / not harvested", "Farmer could not be reached or refused the visit", "Other (explain in the note)"]
@app.route("/verify", methods=["GET", "POST"])
@need("extension", "admin")
def verify():
    u = g.user; sc, sa = scope(u, "l."); sc0, sa0 = scope(u)
    if request.method == "POST":
        l = Q1("SELECT * FROM listings l WHERE id=?" + sc.replace("l.", ""), (request.form.get("id"),) + sa); dec = request.form.get("decision")
        if not l or dec not in ("Verified", "Rejected", "Needs visit"): abort(403)
        f = request.form; note = f.get("note", "").strip()[:300]; reason = f.get("reason", "").strip()[:120]; back = request.referrer or "/verify"
        vq = num("verified_qty", 1, 1e8, opt=True); lat, lng = num("lat", -3, 0, opt=True), num("lng", 28, 31, opt=True)
        X("UPDATE listings SET verify_status=?, verified_by=?, verified_at=?, verify_note=?, visited=?, verified_qty=?, visit_lat=?, visit_lng=?, reject_reason=? WHERE id=?",
          (dec, u["id"], TODAY(), note, 1 if (dec == "Verified" and f.get("visited")) else 0, vq if dec == "Verified" else None, lat, lng, reason if dec == "Rejected" else None, l["id"]))
        flash(f"Listing #{l['id']}: {dec}.", "ok")
        return redirect(back)
    st = request.args.get("status", "Pending"); w, a = ["l.status!='Withdrawn'"], []
    if st != "All": w.append("l.verify_status=?"); a.append(st)
    rows = Q("SELECT l.*, u.name seller, u.photo seller_photo, u.phone seller_phone FROM listings l JOIN users u ON u.id=l.seller_id WHERE " + " AND ".join(w) + sc + " ORDER BY l.id DESC LIMIT 100", tuple(a) + sa)
    for l in rows: l["checks"] = plausibility(l)
    cnt = {r["verify_status"]: r["c"] for r in Q("SELECT verify_status, COUNT(*) c FROM listings WHERE status!='Withdrawn'" + sc0 + " GROUP BY verify_status", sa0)}
    kpi = Q1("SELECT COALESCE(SUM(verify_status='Pending'),0) pend, COALESCE(SUM(verify_status='Needs visit'),0) visit, COALESCE(SUM(verify_status='Verified'),0) ver, COALESCE(SUM(verify_status='Rejected'),0) rej, COALESCE(SUM(CASE WHEN verify_status='Verified' THEN COALESCE(verified_qty,qty_kg) END),0) kg FROM listings WHERE status!='Withdrawn'" + sc0, sa0)
    return render_template("verify.html", kpi=kpi, rows=rows, st=st, f=request.args, cnt=cnt, crops=Q("SELECT name FROM crops ORDER BY name"), ds=Q("SELECT name FROM districts ORDER BY name"), reasons=REJECT_REASONS)

# ---------- profile & other core pages ----------
@app.route("/profile", methods=["GET", "POST"])
@need()
def profile():
    u = g.user; ds = Q("SELECT name FROM districts ORDER BY name"); guest_ = u["email"].endswith("@guest.kiza")
    if request.method == "POST":
        f = request.form
        if guest_: flash("Guest accounts cannot be edited.", "err"); return redirect("/profile")
        name = f.get("name", "").strip()[:80]; phone = norm_phone(f.get("phone")); email = f.get("email", "").strip().lower(); err = None
        if not name: err = "Please enter your name."
        elif not phone: err = "Enter a valid Rwandan phone number."
        try: photo = image_ok("photo", 600) if not err else None
        except ValueError as e: err = str(e); photo = None
        if err: flash(err, "err")
        else:
            X("UPDATE users SET name=?, phone=?, email=?, district=?, sector=?, village=?, bio=?, lang=?, photo=COALESCE(?,photo) WHERE id=?",
              (name, phone, email or u["email"], u["district"] if u["role"] == "extension" else f["district"], u["sector"] if u["role"] == "extension" else f.get("sector", "").strip()[:60], u["village"] if u["role"] == "extension" else f.get("village", "").strip()[:60], f.get("bio", "").strip()[:300], f.get("lang") if f.get("lang") in LANGS else "en", photo, u["id"]))
            flash("Profile saved.", "ok"); return redirect("/profile")
    st = Q1("SELECT COUNT(*) n, SUM(verify_status='Verified') v FROM listings WHERE seller_id=?", (u["id"],)); sc = Q1("SELECT COUNT(*) n FROM scans WHERE user_id=?", (u["id"],))["n"]
    done = sum(bool(u.get(k)) for k in ("photo", "phone", "district", "sector", "village", "bio")); return render_template("profile.html", ds=ds, st=st, sc=sc, pct=round(100 * done / 6), guest_=guest_)

@app.route("/scan", methods=["GET", "POST"])
@need("farmer", "buyer", "extension", "admin")
def scan():
    u = g.user; crops = [c["name"] for c in Q("SELECT name FROM crops ORDER BY name")]; res = None
    if request.method == "POST":
        try:
            img = image_ok("photo")
            if not img: raise ValueError("Please choose or take a photo of the plant leaf.")
            crop = request.form.get("crop", ""); cs = disease.colour_screen(os.path.join(UPLOADS, img)); ai = disease.ai_diagnose(open(os.path.join(UPLOADS, img), "rb").read(), crop)
            res = {"img": img, "crop": crop, "cs": cs, "ai": ai}
            X("INSERT INTO scans(user_id,image,crop,mode,result) VALUES(?,?,?,?,?)", (u["id"], img, crop, "ai", json.dumps(res)))
            audit("scan", crop)
        except ValueError as e: flash(str(e), "err")
    return render_template("scan.html", crops=crops, res=res, hist=Q("SELECT * FROM scans WHERE user_id=? ORDER BY id DESC LIMIT 6", (u["id"],)))

@app.get("/prices")
@need("farmer", "buyer", *STAFF)
def prices():
    crops = Q("SELECT DISTINCT crop name FROM market_prices ORDER BY crop")
    if not crops: return render_template("msg.html", title="No price data yet", msg="Please load market prices first.")
    crop = request.args.get("crop") or crops[0]["name"]
    trends = Q("SELECT e.*, d.province FROM esoko_prices e JOIN districts d ON d.name=e.district WHERE e.crop=? ORDER BY e.current_price_rwf DESC", (crop,))
    return render_template("prices.html", crop=crop, crops=crops, trends=trends)

@app.get("/soil")
@need("farmer", "extension", "admin")
def soil():
    d = request.args.get("district") or g.user["district"]; p = Q1("SELECT * FROM soil_profiles WHERE district=?", (d,)); wx = wx3(d)
    return render_template("soil.html", d=d, p=p, tips=rules.field_advice(p, wx), wx=wx, ds=Q("SELECT name FROM districts ORDER BY name"), allp=Q("SELECT * FROM soil_profiles ORDER BY district"))

@app.post("/ussd")
def ussd_gateway():
    tok = os.environ.get("KIZA_USSD_TOKEN", "")
    if tok and not hmac.compare_digest(tok, request.values.get("token", "") or request.headers.get("X-Kiza-Token", "")): return Response("END Unauthorized", 403, mimetype="text/plain")
    ph = norm_phone(request.form.get("phoneNumber"))
    c = db.conn()
    try: out = ussd.handle((request.form.get("text") or "")[:200], ph, c, write=bool(tok))
    except Exception: out = "END Service error. Please try again."
    finally: c.close()
    return Response(out, mimetype="text/plain")

@app.get("/health")
def health(): return {"app": "ok", "ml_service": "up" if mlclient.call("/health") else "down"}

import kiza8
kiza8.init_app(app)

if __name__ == "__main__":
    if sync.start_background(): print("Live-data auto-refresh ON.")
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)
