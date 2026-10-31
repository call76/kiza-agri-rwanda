"""Farm hub: storage, insurance, equipment rental, cooperatives, logistics, messages, smart irrigation, harvest estimate."""
import datetime as dt
from flask import Blueprint, render_template, request, redirect, flash, abort, jsonify, session
import db
from .core import Q, Q1, X, me, need, notify

bp = Blueprint("hub", __name__)
ALL = ("farmer", "buyer", "extension", "government", "admin")
STAFF = ("government", "admin")

def migrate():
    c = db.conn()
    c.executescript("""
CREATE TABLE IF NOT EXISTS inventory(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), crop TEXT NOT NULL, quantity_kg REAL NOT NULL, movement TEXT NOT NULL, expiry_date TEXT, note TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS insurance_policies(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), farm_name TEXT NOT NULL, crop TEXT, area_ha REAL, district TEXT, provider TEXT, status TEXT DEFAULT 'Pending', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS insurance_claims(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), policy_id INTEGER NOT NULL REFERENCES insurance_policies(id), cause TEXT, description TEXT, status TEXT DEFAULT 'Pending', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS equipment(id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id), name TEXT NOT NULL, kind TEXT, price_per_day REAL NOT NULL, district TEXT, phone TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS bookings(id INTEGER PRIMARY KEY, equipment_id INTEGER NOT NULL REFERENCES equipment(id), user_id INTEGER NOT NULL REFERENCES users(id), start_date TEXT, days INTEGER DEFAULT 1, status TEXT DEFAULT 'Pending', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS cooperatives(id INTEGER PRIMARY KEY, name TEXT NOT NULL, district TEXT, main_crop TEXT, created_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS coop_members(id INTEGER PRIMARY KEY, coop_id INTEGER NOT NULL REFERENCES cooperatives(id), user_id INTEGER NOT NULL REFERENCES users(id), shares REAL DEFAULT 0, contribution_rwf REAL DEFAULT 0, harvest_kg REAL DEFAULT 0, UNIQUE(coop_id,user_id));
CREATE TABLE IF NOT EXISTS transport_requests(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), crop TEXT, quantity_kg REAL, pickup TEXT, destination TEXT, offer_rwf REAL, status TEXT DEFAULT 'irategereje', driver_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), author_name TEXT, channel TEXT, body TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS ix_msg ON messages(channel,id);""")
    c.commit(); c.close()

def _f(k, d=0.0, lo=None, hi=None):
    try: v = float(request.form.get(k, d))
    except Exception: v = d
    if v != v: v = d
    if lo is not None: v = max(lo, v)
    if hi is not None: v = min(hi, v)
    return v
def _s(k, n=200): return (request.form.get(k) or "").strip()[:n]
def _opts(): return dict(crops=[r["name"] for r in Q("SELECT name FROM crops ORDER BY name")], districts=[r["name"] for r in Q("SELECT name FROM districts ORDER BY name")])
def _pick(v, allowed, d): return v if v in allowed else d
def R(page, **k): return render_template("v11/hub.html", page=page, u=me(), **_opts(), **k)

# ---- storage -------------------------------------------------------------
@bp.route("/storage", methods=["GET", "POST"])
@need("farmer", "buyer", "admin")
def storage():
    u = me()
    if request.method == "POST":
        if request.form.get("del"): X("DELETE FROM inventory WHERE id=? AND user_id=?", (int(request.form["del"]), u["id"]))
        else:
            mv = _pick(_s("movement"), ("in", "out", "loss"), "in"); q = _f("quantity_kg", 0, 0, 1e9)
            if q <= 0 or not _s("crop"): flash("Enter crop and quantity.", "err")
            else: X("INSERT INTO inventory(user_id,crop,quantity_kg,movement,expiry_date,note) VALUES(?,?,?,?,?,?)", (u["id"], _s("crop", 60), q, mv, _s("expiry_date", 10) or None, _s("note") or None)); flash("✅", "ok")
        return redirect("/storage")
    rows = Q("SELECT * FROM inventory WHERE user_id=? ORDER BY id DESC LIMIT 300", (u["id"],))
    s = lambda m: sum(r["quantity_kg"] for r in rows if r["movement"] == m)
    by = {}
    for r in rows: by[r["crop"]] = by.get(r["crop"], 0) + (1 if r["movement"] == "in" else -1) * r["quantity_kg"]
    soon = [r for r in rows if r["movement"] == "in" and r["expiry_date"] and r["expiry_date"] <= (dt.date.today() + dt.timedelta(days=7)).isoformat()]
    return R("storage", rows=rows, tin=s("in"), tout=s("out"), tloss=s("loss"), by=by, soon=soon)

# ---- insurance -----------------------------------------------------------
PROVIDERS = ["Radiant Insurance", "SONARWA General", "Prime Insurance", "Old Mutual Rwanda", "BK General Insurance"]
CAUSES = ["Drought", "Flood", "Hail", "Pests/Disease", "Fire"]
PREMIUM_HA = 45000   # illustrative; NAIS subsidy share (40%) must be confirmed with the insurer
@bp.route("/insurance", methods=["GET", "POST"])
@need(*ALL)
def insurance():
    u = me(); staff = u["role"] in STAFF
    if request.method == "POST":
        a = request.form.get("a")
        if a == "policy" and u["role"] in ("farmer", "admin"):
            ha = _f("area_ha", 0, 0, 10000)
            if ha > 0 and _s("farm_name"): X("INSERT INTO insurance_policies(user_id,farm_name,crop,area_ha,district,provider) VALUES(?,?,?,?,?,?)", (u["id"], _s("farm_name", 80), _s("crop", 60), ha, _s("district", 40), _pick(_s("provider"), PROVIDERS, PROVIDERS[0]))); flash("Request sent.", "ok")
        elif a == "claim":
            p = Q1("SELECT * FROM insurance_policies WHERE id=? AND user_id=?", (int(_f("policy_id")), u["id"]))
            if p and _s("description"): X("INSERT INTO insurance_claims(user_id,policy_id,cause,description) VALUES(?,?,?,?)", (u["id"], p["id"], _pick(_s("cause"), CAUSES, CAUSES[0]), _s("description", 1000))); flash("Claim sent.", "ok")
        elif a == "status" and staff:
            st = _pick(_s("status"), ("Pending", "Approved", "Rejected", "Paid"), "Pending"); c = Q1("SELECT * FROM insurance_claims WHERE id=?", (int(_f("id")),))
            if c: X("UPDATE insurance_claims SET status=? WHERE id=?", (st, c["id"])); notify(c["user_id"], "insurance", f"Insurance claim #{c['id']}: {st}", "/insurance")
        return redirect("/insurance")
    own = "" if staff else " WHERE user_id=%d" % u["id"]
    pol = Q("SELECT * FROM insurance_policies" + own + " ORDER BY id DESC LIMIT 200")
    cl = Q("SELECT c.*, p.farm_name FROM insurance_claims c JOIN insurance_policies p ON p.id=c.policy_id" + (" WHERE c.user_id=%d" % u["id"] if not staff else "") + " ORDER BY c.id DESC LIMIT 200")
    return R("insurance", pol=pol, cl=cl, providers=PROVIDERS, causes=CAUSES, ph=PREMIUM_HA, staff=staff)

# ---- equipment -----------------------------------------------------------
KINDS = ["Tractor", "Plough", "Water pump", "Harvester", "Sprayer"]
@bp.route("/equipment", methods=["GET", "POST"])
@need(*ALL)
def equipment():
    u = me()
    if request.method == "POST":
        a = request.form.get("a")
        if a == "add" and u["role"] != "government":
            pr = _f("price_per_day", 0, 0, 1e8)
            if pr > 0 and _s("name"): X("INSERT INTO equipment(owner_id,name,kind,price_per_day,district,phone) VALUES(?,?,?,?,?,?)", (u["id"], _s("name", 80), _pick(_s("kind"), KINDS, KINDS[0]), pr, _s("district", 40), _s("phone", 20)))
        elif a == "book":
            e = Q1("SELECT * FROM equipment WHERE id=?", (int(_f("equipment_id")),))
            if e and e["owner_id"] != u["id"] and _s("start_date", 10):
                X("INSERT INTO bookings(equipment_id,user_id,start_date,days) VALUES(?,?,?,?)", (e["id"], u["id"], _s("start_date", 10), int(_f("days", 1, 1, 90)))); notify(e["owner_id"], "booking", f"New booking request: {e['name']}", "/equipment")
        elif a == "status":
            b = Q1("SELECT b.*, e.owner_id, e.name FROM bookings b JOIN equipment e ON e.id=b.equipment_id WHERE b.id=?", (int(_f("id")),))
            if b and (b["owner_id"] == u["id"] or u["role"] == "admin"):
                st = _pick(_s("status"), ("Accepted", "Declined", "Completed"), "Declined"); X("UPDATE bookings SET status=? WHERE id=?", (st, b["id"])); notify(b["user_id"], "booking", f"{b['name']}: {st}", "/equipment")
        return redirect("/equipment")
    d = request.args.get("district", "")
    eq = Q("SELECT e.*, u.name owner FROM equipment e JOIN users u ON u.id=e.owner_id" + (" WHERE e.district=?" if d else "") + " ORDER BY e.id DESC LIMIT 200", (d,) if d else ())
    bk = Q("SELECT b.*, e.name ename, e.owner_id, e.price_per_day FROM bookings b JOIN equipment e ON e.id=b.equipment_id WHERE b.user_id=? OR e.owner_id=? ORDER BY b.id DESC LIMIT 100", (u["id"], u["id"]))
    return R("equipment", eq=eq, bk=bk, kinds=KINDS, dsel=d)

# ---- cooperatives --------------------------------------------------------
@bp.route("/cooperatives", methods=["GET", "POST"])
@need(*ALL)
def cooperatives():
    u = me()
    if request.method == "POST":
        a = request.form.get("a")
        if a == "create" and u["role"] in ("farmer", "admin") and _s("name"):
            cid = X("INSERT INTO cooperatives(name,district,main_crop,created_by) VALUES(?,?,?,?)", (_s("name", 80), _s("district", 40), _s("main_crop", 60), u["id"])); X("INSERT INTO coop_members(coop_id,user_id) VALUES(?,?)", (cid, u["id"]))
        elif a == "join" and u["role"] in ("farmer", "admin"): X("INSERT OR IGNORE INTO coop_members(coop_id,user_id) VALUES(?,?)", (int(_f("id")), u["id"]))
        elif a == "save": X("UPDATE coop_members SET shares=?,contribution_rwf=?,harvest_kg=? WHERE coop_id=? AND user_id=?", (_f("shares", 0, 0, 1e9), _f("contribution_rwf", 0, 0, 1e12), _f("harvest_kg", 0, 0, 1e12), int(_f("id")), u["id"]))
        return redirect("/cooperatives")
    cs = Q("SELECT * FROM cooperatives ORDER BY id DESC LIMIT 100")
    for c in cs:
        m = Q("SELECT * FROM coop_members WHERE coop_id=?", (c["id"],)); c["n"] = len(m); c["shares"] = sum(x["shares"] for x in m); c["money"] = sum(x["contribution_rwf"] for x in m); c["kg"] = sum(x["harvest_kg"] for x in m)
        c["me"] = next((x for x in m if x["user_id"] == u["id"]), None)
    return R("coops", cs=cs)

# ---- logistics -----------------------------------------------------------
STEPS = ["irategereje", "yakiriwe", "iri mu nzira", "yagezeyo"]
@bp.route("/logistics", methods=["GET", "POST"])
@need("farmer", "buyer", "admin")
def logistics():
    u = me()
    if request.method == "POST":
        a = request.form.get("a")
        if a == "new":
            q = _f("quantity_kg", 0, 0, 1e7)
            if q > 0: X("INSERT INTO transport_requests(user_id,crop,quantity_kg,pickup,destination,offer_rwf) VALUES(?,?,?,?,?,?)", (u["id"], _s("crop", 60), q, _s("pickup", 40), _s("destination", 40), _f("offer_rwf", q * 15 + 10000, 0, 1e9)))
        else:
            r = Q1("SELECT * FROM transport_requests WHERE id=?", (int(_f("id")),))
            if r and a == "take" and not r["driver_id"] and r["user_id"] != u["id"]: X("UPDATE transport_requests SET driver_id=?,status='yakiriwe' WHERE id=? AND driver_id IS NULL", (u["id"], r["id"])); notify(r["user_id"], "transport", "Your transport request was accepted", "/logistics")
            elif r and a == "next" and r["driver_id"] == u["id"] and r["status"] in STEPS[1:3]: X("UPDATE transport_requests SET status=? WHERE id=?", (STEPS[STEPS.index(r["status"]) + 1], r["id"]))
        return redirect("/logistics")
    rs = Q("SELECT t.*, u.name requester FROM transport_requests t JOIN users u ON u.id=t.user_id ORDER BY t.id DESC LIMIT 100")
    return R("logistics", rs=rs, steps=STEPS)

# ---- messages ------------------------------------------------------------
CHANNELS = [("rusange", "🌍 General / Rusange"), ("indwara", "🦠 Crop diseases"), ("isoko", "💰 Market & prices"), ("imashini", "🚜 Equipment"), ("ikirere", "🌦️ Weather")]
@bp.get("/messages")
@need(*ALL)
def messages():
    return R("messages", chans=CHANNELS, ch=_pick(request.args.get("c"), [c[0] for c in CHANNELS], "rusange"))
@bp.get("/api/hub/messages")
@need(*ALL)
def messages_feed():
    ch = _pick(request.args.get("c"), [c[0] for c in CHANNELS], "rusange"); u = me()
    rows = Q("SELECT id,user_id,author_name,body,created_at FROM messages WHERE channel=? ORDER BY id DESC LIMIT 100", (ch,))[::-1]
    return jsonify([dict(r, mine=r["user_id"] == u["id"]) for r in rows])
@bp.post("/api/hub/messages")
@need(*ALL)
def messages_post():
    u = me(); b = _s("body", 1000); ch = _pick(_s("c"), [c[0] for c in CHANNELS], "rusange")
    if b: X("INSERT INTO messages(user_id,author_name,channel,body) VALUES(?,?,?,?)", (u["id"], u["name"], ch, b))
    return jsonify(ok=True)

# ---- irrigation + harvest estimate (transparent formulas, no black box) ----
KC = {"Maize": 1.2, "Beans": 1.15, "Potato": 1.15, "Rice": 1.2, "Tomato": 1.15, "Cabbage": 1.05, "Banana": 1.1, "Coffee": 0.95, "Soybean": 1.15}
@bp.route("/irrigation")
@need("farmer", "extension", "admin")
def irrigation():
    u = me(); o = _opts(); d = request.args.get("district") or u.get("district") or "Bugesera"; crop = _pick(request.args.get("crop"), KC, "Maize")
    try: ha = max(0, min(10000, float(request.args.get("area", 0.5))))
    except Exception: ha = 0.5
    w = Q("SELECT * FROM weather WHERE district=? ORDER BY day LIMIT 7", (d,)); days = []
    for r in w:
        et0 = max(2.0, 0.12 * (r["temp"] or 20) + 1.5); etc = et0 * KC[crop]; rain = r["rain_mm"] or 0; need_mm = max(0.0, etc - rain * 0.8)
        days.append(dict(day=r["day"], etc=round(etc, 1), rain=round(rain, 1), need=round(need_mm, 1), litres=round(need_mm * ha * 10000)))
    return R("irrigation", days=days, kc=KC, crop=crop, ha=ha, d=d, total=sum(x["litres"] for x in days), demo=bool(w and w[0]["is_demo"]))
@bp.route("/harvest", methods=["GET", "POST"])
@need("farmer", "extension", "admin")
def harvest():
    res = None
    if request.method == "POST":
        c = Q1("SELECT * FROM crops WHERE name=?", (_s("crop", 60),)); ha = _f("area_ha", 0, 0, 10000)
        try: pd = dt.date.fromisoformat(_s("planting_date", 10))
        except Exception: pd = None
        if c and ha > 0 and pd:
            kg = c["yield_t_ha"] * 1000 * ha; hd = pd + dt.timedelta(days=int(c["cycle_days"] or 120))
            res = dict(crop=c["name"], kg=round(kg), low=round(kg * .7), high=round(kg * 1.1), date=hd.isoformat(), income=round(kg * (c["price_kg"] or 0)), price=c["price_kg"])
    return R("harvest", res=res)
