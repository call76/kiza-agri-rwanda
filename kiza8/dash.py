"""v9: one dashboard per role (farmer is in app.py), government poverty + annual production analysis (30 districts),
admin full-control console, advisor (umujyanama) workspace, buyer dashboard, sold-outside + scheduled listings, site settings."""
import csv, io, math, random, re, secrets, datetime as dt
from flask import Blueprint, request, redirect, render_template, flash, g, abort, Response
from markupsafe import Markup
from werkzeug.security import generate_password_hash
from .core import Q, Q1, X, T, audit, need, notify, fnum, today, _c
from . import inventory as inv

bp = Blueprint("dash9", __name__)
THIS_YEAR = lambda: dt.date.today().year

# ------------------------------------------------------------------ data seeds
# NISR EICV7 2023/24: share of population living in poverty by district (national 27.4%).
# The source page lists names and values in parallel order; the pairing is inferred -> is_official=0 until an admin confirms/uploads the table.
EICV7 = [("Nyarugenge", 6.8), ("Kicukiro", 6.9), ("Gasabo", 11.1), ("Gicumbi", 13.3), ("Kirehe", 14.2), ("Muhanga", 15.0), ("Ruhango", 15.0), ("Gatsibo", 18.4),
         ("Nyabihu", 20.2), ("Musanze", 21.0), ("Rulindo", 21.6), ("Burera", 22.0), ("Bugesera", 23.7), ("Rwamagana", 23.8), ("Huye", 24.2), ("Gakenke", 24.5),
         ("Ngororero", 30.2), ("Ngoma", 30.9), ("Nyagatare", 36.4), ("Kayonza", 36.6), ("Karongi", 38.2), ("Rubavu", 38.8), ("Kamonyi", 39.7), ("Nyaruguru", 39.7),
         ("Rutsiro", 40.8), ("Nyamasheke", 42.8), ("Nyanza", 43.3), ("Rusizi", 44.2), ("Gisagara", 45.6), ("Nyamagabe", 51.4)]
POV_SRC = "NISR EICV7 2023/24 (district poverty map) - name/value pairing to be confirmed against the full report"
NATIONAL_POVERTY = 27.4
YEAR_F = {2022: .02, 2023: -.03, 2024: .04, 2025: .03}   # DEMO: shared weather/price effect per year
DEMO_CROPS = {"Maize": 5200, "Beans": 3100, "Potato": 9000, "Cassava": 4200, "Rice": 1800, "Tomato": 900}

def seed():
    """Idempotent: poverty rows for every district; DEMO production history only if the table is empty."""
    import db
    c = db.conn()
    try:
        have = {r[0] for r in c.execute("SELECT name FROM districts")}
        for d, v in EICV7:
            if d in have: c.execute("INSERT OR IGNORE INTO poverty_index(district,poverty_rate,year,source,is_official) VALUES(?,?,?,?,0)", (d, v, "2023/24", POV_SRC))
        if not c.execute("SELECT 1 FROM production_history LIMIT 1").fetchone():
            crops = {r[0] for r in c.execute("SELECT name FROM crops")}; rnd = random.Random(909)
            pov = dict(EICV7)
            for d in sorted(have):
                size = rnd.uniform(.6, 1.5); poor = pov.get(d, 25) / 50.0
                trend = rnd.uniform(-.10, .14) - poor * .06          # poorer districts drift lower in the demo series
                for cr, base in DEMO_CROPS.items():
                    if cr not in crops: continue
                    v = base * size * rnd.uniform(.7, 1.3) * (1.1 - poor * .35)
                    for y in range(2021, THIS_YEAR()):
                        v *= 1 + trend + YEAR_F.get(y, 0) + rnd.uniform(-.08, .08)
                        c.execute("INSERT OR IGNORE INTO production_history(district,year,crop,tonnes,source,is_demo) VALUES(?,?,?,?,?,1)", (d, y, cr, round(max(v, 5), 1), "DEMO series - replace with NISR / RAB seasonal agriculture survey"))
        c.commit()
    finally: c.close()

# ------------------------------------------------------------------ small SVG helpers
def spark(vals, w=120, h=34, up=None):
    vals = [v for v in vals if v is not None]
    if len(vals) < 2: return Markup("")
    lo, hi = min(vals), max(vals); rg = (hi - lo) or 1; col = "#2e9e5b" if (up if up is not None else vals[-1] >= vals[-2]) else "#d64545"
    pts = [(round(4 + i * (w - 8) / (len(vals) - 1), 1), round(h - 5 - (v - lo) / rg * (h - 10), 1)) for i, v in enumerate(vals)]
    return Markup(f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-hidden="true"><polyline fill="none" stroke="{col}" stroke-width="2.4" stroke-linejoin="round" points="{" ".join(f"{x},{y}" for x, y in pts)}"/><circle cx="{pts[-1][0]}" cy="{pts[-1][1]}" r="3.4" fill="{col}"/></svg>')

def need_color(v):
    """0..100 need index -> colour (green low need ... red high need)."""
    return "#d64545" if v >= 60 else "#e8782a" if v >= 45 else "#e6a118" if v >= 30 else "#7cc576" if v >= 18 else "#2e9e5b"

def rwanda_map(rows, key="need", w=560, h=500):
    """Dot cartogram from district centroids. rows: dicts with name, lat, lng, <key>, label."""
    lat0, lat1, lng0, lng1 = -1.25, -2.80, 28.85, 30.80
    out = [f'<svg viewBox="0 0 {w} {h}" class="rmap" role="img" aria-label="Rwanda districts">']
    for r in rows:
        x = 40 + (r["lng"] - lng0) / (lng1 - lng0) * (w - 80); y = 26 + (lat0 - r["lat"]) / (lat0 - lat1) * (h - 70)
        out.append(f'<g><title>{r["name"]}: {r["label"]}</title><circle cx="{x:.0f}" cy="{y:.0f}" r="10" fill="{need_color(r[key])}" stroke="#fff" stroke-width="2"/>'
                   f'<text x="{x:.0f}" y="{y+22:.0f}" font-size="9" font-weight="700" text-anchor="middle" fill="#1d2b24" stroke="#eef6f0" stroke-width="3" paint-order="stroke">{r["name"]}</text></g>')
    out.append("</svg>"); return Markup("".join(out))

def bar_svg(items, w=680, bar_h=22, color="#1a8f50", fmt="{:,.0f}"):
    """Horizontal bars. items: (label, value, colour|None)."""
    if not items: return Markup("")
    mx = max(abs(v) for _, v, *_ in items) or 1; h = len(items) * (bar_h + 6) + 6; lab = 112
    out = [f'<svg viewBox="0 0 {w} {h}" class="bars" role="img">']
    for i, it in enumerate(items):
        n, v = it[0], it[1]; col = it[2] if len(it) > 2 and it[2] else color; y = 4 + i * (bar_h + 6); bw = max(2, abs(v) / mx * (w - lab - 90))
        txt = it[3] if len(it) > 3 else fmt.format(v)
        out.append(f'<text x="0" y="{y+bar_h-6}" font-size="12.5" fill="currentColor">{n}</text><rect x="{lab}" y="{y}" width="{bw:.0f}" height="{bar_h}" rx="6" fill="{col}"/><text x="{lab+bw+6:.0f}" y="{y+bar_h-6}" font-size="12.5" font-weight="700" fill="currentColor">{txt}</text>')
    out.append("</svg>"); return Markup("".join(out))

# ------------------------------------------------------------------ production analysis (government)
def production_table(crop=None):
    """{district: {year: tonnes}} = DEMO/imported history + verified farmer harvest records (live). Returns (table, years, has_demo)."""
    w, a = ("WHERE crop=?", (crop,)) if crop else ("", ())
    t = {}; demo = False
    for r in Q("SELECT district, year, SUM(tonnes) t, MAX(is_demo) d FROM production_history " + w + " GROUP BY district, year", a):
        t.setdefault(r["district"], {})[r["year"]] = r["t"]; demo = demo or bool(r["d"])
    lw, la = ("AND f.crop=?", (crop,)) if crop else ("", ())
    for r in Q("SELECT fa.district, h.season_year year, SUM(h.actual_kg)/1000.0 t FROM harvest_records h JOIN fields f ON f.id=h.field_id JOIN farms fa ON fa.id=f.farm_id WHERE h.verify_status='Verified' AND h.actual_kg IS NOT NULL " + lw + " GROUP BY fa.district, h.season_year", la):
        d = t.setdefault(r["district"], {}); d[r["year"]] = d.get(r["year"], 0) + r["t"]
    years = sorted({y for d in t.values() for y in d})
    return t, years, demo

def verdict(pct):
    return "flat" if pct is None or abs(pct) < 1 else ("rise" if pct > 0 else "fall")

def gov_model(year=None, crop=None):
    ds = Q("SELECT d.name, d.province, d.lat, d.lng, p.poverty_rate, p.is_official FROM districts d LEFT JOIN poverty_index p ON p.district=d.name ORDER BY d.name")
    t, years, demo = production_table(crop)
    full = [y for y in years if y < THIS_YEAR()] or years
    year = year if year in years else (full[-1] if full else None); prev = year - 1 if year else None
    dist = {r["district"]: r["c"] for r in Q("SELECT district, COUNT(*) c FROM distress_reports WHERE status!='Resolved' GROUP BY district")}
    farmers = {r["district"]: r["c"] for r in Q("SELECT district, COUNT(*) c FROM users WHERE role='farmer' AND email NOT LIKE '%@guest.kiza' GROUP BY district")}
    maxd = max(dist.values(), default=0) or 1; maxp = max([d["poverty_rate"] or 0 for d in ds], default=0) or 1
    rows = []
    for d in ds:
        s = t.get(d["name"], {}); cur, pv = s.get(year), s.get(prev)
        pct = round((cur - pv) / pv * 100, 1) if cur is not None and pv else None
        pov = d["poverty_rate"]; decl = min(1, max(0, -(pct or 0)) / 20)
        need_i = round(100 * (.65 * ((pov or 0) / maxp) + .25 * decl + .10 * (dist.get(d["name"], 0) / maxd)), 1)
        rows.append(dict(d, poverty=pov, official=bool(d["is_official"]), cur=cur, prev=pv, pct=pct, verdict=verdict(pct), series=[s.get(y) for y in years if y >= (years[-1] - 5)], dist=dist.get(d["name"], 0),
                         farmers=farmers.get(d["name"], 0), need=need_i, color=need_color(need_i), label=f"{pov if pov is not None else '?'}% poverty · need {need_i}"))
    tot = lambda y: sum(s.get(y, 0) for s in t.values()) if y else None
    ntl_cur, ntl_prev = tot(year), tot(prev); npct = round((ntl_cur - ntl_prev) / ntl_prev * 100, 1) if ntl_cur is not None and ntl_prev else None
    nat = dict(year=year, prev=prev, cur=ntl_cur, prev_t=ntl_prev, pct=npct, verdict=verdict(npct), rise=sum(r["verdict"] == "rise" for r in rows), fall=sum(r["verdict"] == "fall" for r in rows),
               series=[(y, round(tot(y))) for y in years], demo=demo, above_nat=sum((r["poverty"] or 0) > NATIONAL_POVERTY for r in rows), national_poverty=NATIONAL_POVERTY)
    return dict(rows=rows, nat=nat, years=years, crop=crop, demo=demo)

@bp.get("/gov")
@need("government", "admin")
def gov_home():
    m = gov_model(request.args.get("year", type=int)); rows = m["rows"]; top = sorted(rows, key=lambda r: -r["need"])[:10]
    risers = sorted([r for r in rows if r["pct"] is not None], key=lambda r: -r["pct"])
    k = Q1("SELECT (SELECT COUNT(*) FROM users WHERE role='farmer' AND email NOT LIKE '%@guest.kiza') farmers,(SELECT COUNT(*) FROM distress_reports WHERE status!='Resolved') distress,"
           "(SELECT COUNT(*) FROM listings WHERE verify_status='Verified' AND status IN ('Available','Offer Received','Reserved')) listings,(SELECT COALESCE(SUM(size_ha),0) FROM fields WHERE status NOT IN ('Planned','Prepared','Failed')) ha")
    return render_template("v9/gov_home.html", m=m, top=top, rmap=rwanda_map(rows), up=risers[:5], down=risers[::-1][:5] if risers else [], k=k,
                           bars=bar_svg([(r["name"], r["poverty"] or 0, r["color"]) for r in top], fmt="{:.1f}%"))

@bp.get("/gov/poverty")
@need("government", "admin")
def gov_poverty():
    m = gov_model(); rows = sorted(m["rows"], key=lambda r: -(r["poverty"] or 0)); prov = request.args.get("province", "")
    if prov: rows = [r for r in rows if r["province"] == prov]
    if request.args.get("csv"):
        return _csv("poverty-ranking", [dict(rank=i + 1, district=r["name"], province=r["province"], poverty_rate_pct=r["poverty"], need_index=r["need"], production_change_pct=r["pct"], open_distress=r["dist"], farmers=r["farmers"]) for i, r in enumerate(rows)])
    pi = Q1("SELECT MAX(source) s, MIN(is_official) o FROM poverty_index")
    return render_template("v9/gov_poverty.html", m=m, rows=rows, prov=prov, provinces=sorted({r["province"] for r in m["rows"]}), src=pi, bars=bar_svg([(r["name"], r["poverty"] or 0, r["color"]) for r in rows], fmt="{:.1f}%"))

@bp.get("/gov/production")
@need("government", "admin")
def gov_production():
    crop = request.args.get("crop") or None
    if crop and not Q1("SELECT 1 x FROM crops WHERE name=?", (crop,)): abort(404)
    m = gov_model(request.args.get("year", type=int), crop); rows = m["rows"]; sort = request.args.get("sort", "name")
    rows = sorted(rows, key={"pct": lambda r: (r["pct"] is None, r["pct"] or 0), "down": lambda r: (r["pct"] is None, -(r["pct"] or 0)), "name": lambda r: r["name"], "tonnes": lambda r: -(r["cur"] or 0)}.get(sort, lambda r: r["name"]))
    for r in rows: r["spark"] = spark(r["series"], up=(r["pct"] or 0) >= 0)
    if request.args.get("csv"):
        return _csv("production-" + str(m["nat"]["year"]), [dict(district=r["name"], province=r["province"], year=m["nat"]["year"], tonnes=None if r["cur"] is None else round(r["cur"], 1), previous_year_tonnes=None if r["prev"] is None else round(r["prev"], 1), change_pct=r["pct"], verdict=r["verdict"]) for r in rows])
    ser = m["nat"]["series"]
    return render_template("v9/gov_production.html", m=m, rows=rows, sort=sort, crops=[x["name"] for x in Q("SELECT DISTINCT crop name FROM production_history ORDER BY crop")], nat_spark=spark([v for _, v in ser], 360, 90),
                           chart=bar_svg([(str(y), abs(pc), "#2e9e5b" if pc >= 0 else "#d64545", f"{v:,.0f} t  ({pc:+.1f}%)") for (y0, v0), (y, v) in zip(ser, ser[1:]) for pc in [round((v - v0) / v0 * 100, 1) if v0 else 0]][-8:]))

def _csv(name, rows):
    out = io.StringIO(); out.write("﻿"); safe = lambda v: ("'" + v) if isinstance(v, str) and v and v[0] in "=+-@\t\r" else ("" if v is None else v)
    if rows:
        wr = csv.writer(out); wr.writerow(rows[0].keys()); [wr.writerow([safe(v) for v in r.values()]) for r in rows]
    return Response(out.getvalue(), mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment; filename=kiza-{name}.csv"})

# ------------------------------------------------------------------ buyer dashboard
@bp.get("/buyer")
@need("buyer")
def buyer_home():
    u = g.user
    o = Q1("SELECT COALESCE(SUM(status='Pending'),0) pend, COALESCE(SUM(status='Accepted'),0) acc, COALESCE(SUM(status='Completed'),0) done, COALESCE(SUM(CASE WHEN status='Completed' THEN qty_kg END),0) kg, COALESCE(SUM(CASE WHEN status='Completed' THEN qty_kg*price_kg END),0) rwf FROM offers WHERE buyer_id=?", (u["id"],))
    live = Q("SELECT l.*, us.name seller FROM listings l JOIN users us ON us.id=l.seller_id WHERE l.verify_status='Verified' AND l.status IN ('Available','Offer Received','Reserved') AND l.available_kg>0 AND (l.harvest_date IS NULL OR l.harvest_date<=date('now')) ORDER BY l.id DESC LIMIT 6")
    sched = Q("SELECT l.*, us.name seller FROM listings l JOIN users us ON us.id=l.seller_id WHERE l.verify_status='Verified' AND l.status IN ('Available','Offer Received','Reserved') AND l.harvest_date>date('now') ORDER BY l.harvest_date LIMIT 6")
    watches = Q("SELECT w.*, (SELECT COALESCE(SUM(l.available_kg),0) FROM listings l WHERE l.crop=w.crop AND (w.district='' OR l.district=w.district) AND l.verify_status='Verified' AND l.status IN ('Available','Offer Received','Reserved') AND (l.harvest_date IS NULL OR l.harvest_date<=date('now'))) kg FROM watches w WHERE w.user_id=?", (u["id"],))
    movers = Q("SELECT * FROM esoko_prices WHERE change_pct IS NOT NULL ORDER BY ABS(change_pct) DESC LIMIT 5")
    sectors = Q("SELECT crop, district, COALESCE(NULLIF(sector,''),'-') sector, SUM(available_kg) kg, COUNT(*) n FROM listings WHERE verify_status='Verified' AND status IN ('Available','Offer Received','Reserved') AND available_kg>0 AND (harvest_date IS NULL OR harvest_date<=date('now')) GROUP BY crop, district, sector ORDER BY kg DESC LIMIT 6")
    return render_template("v9/buyer_home.html", o=o, live=live, sched=sched, watches=watches, movers=movers, sectors=sectors, crops=Q("SELECT name FROM crops ORDER BY name"),
                           notes=Q("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 4", (u["id"],)))

# ------------------------------------------------------------------ advisor (umujyanama) workspace
def a_scope(u, pfx="", col="district", vcol="village"):
    """Village advisor -> own village; district officer -> own district; admin -> everything."""
    if u["role"] == "admin": return "", ()
    v = (u.get("village") or "").strip().lower()
    if v: return f" AND {pfx}{col}=? AND lower(trim(COALESCE({pfx}{vcol},'')))=?", (u["district"], v)
    return f" AND {pfx}{col}=?", (u["district"],)

@bp.get("/advisor/home")
@need("extension", "admin")
def advisor_home():
    u = g.user; sc, a = a_scope(u); lsc, la = a_scope(u, "l."); usc, ua = a_scope(u, "us.")
    k = Q1("SELECT COALESCE(SUM(verify_status='Pending'),0) pend, COALESCE(SUM(verify_status='Needs visit'),0) visit, COALESCE(SUM(verify_status='Verified' AND verified_at>=date('now','start of month')),0) month, COALESCE(SUM(verify_status='Verified'),0) ver FROM listings l WHERE status!='Withdrawn'" + lsc, la)
    k["farmers"] = Q1("SELECT COUNT(*) c FROM users WHERE role='farmer' AND status='active' AND email NOT LIKE '%@guest.kiza'" + sc, a)["c"]
    k["harvests"] = Q1("SELECT COUNT(*) c FROM harvest_records h JOIN fields f ON f.id=h.field_id JOIN farms fa ON fa.id=f.farm_id WHERE h.verify_status='Submitted'" + (" AND fa.district=?" if u["role"] != "admin" else ""), (u["district"],) if u["role"] != "admin" else ())["c"]
    k["issues"] = Q1("SELECT COUNT(*) c FROM issue_reports r JOIN users us ON us.id=r.farmer_id WHERE r.status IN ('Submitted','Assigned','Under Review','Info Requested')" + usc, ua)["c"]
    pend = Q("SELECT l.*, us.name seller, us.phone seller_phone FROM listings l JOIN users us ON us.id=l.seller_id WHERE l.verify_status IN ('Pending','Needs visit') AND l.status!='Withdrawn'" + lsc + " ORDER BY l.id LIMIT 8", la)
    sched = Q("SELECT l.*, us.name seller FROM listings l JOIN users us ON us.id=l.seller_id WHERE l.status!='Withdrawn' AND l.harvest_date>date('now')" + lsc + " ORDER BY l.harvest_date LIMIT 6", la)
    issues = Q("SELECT r.*, us.name farmer FROM issue_reports r JOIN users us ON us.id=r.farmer_id WHERE r.status IN ('Submitted','Assigned','Under Review','Info Requested')" + usc + " ORDER BY CASE r.urgency WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END, r.id DESC LIMIT 5", ua)
    crops = Q("SELECT f.crop, ROUND(SUM(f.size_ha),1) ha, COUNT(DISTINCT fa.user_id) n FROM fields f JOIN farms fa ON fa.id=f.farm_id JOIN users us ON us.id=fa.user_id WHERE f.status NOT IN ('Harvested','Failed')" + usc + " GROUP BY f.crop ORDER BY ha DESC LIMIT 6", ua)
    return render_template("v9/advisor_home.html", k=k, pend=pend, sched=sched, issues=issues, crops=crops, area=(u.get("village") or u["district"]) if u["role"] != "admin" else "Rwanda")

@bp.route("/advisor/farmers", methods=["GET", "POST"])
@need("extension", "admin")
def advisor_farmers():
    u = g.user; sc, a = a_scope(u)
    if request.method == "POST":
        f = request.form; name = f.get("name", "").strip()[:80]; ph = norm_phone(f.get("phone")); sector = f.get("sector", "").strip()[:60]
        dist = u["district"] if u["role"] != "admin" else f.get("district", u["district"]); village = (u.get("village") or f.get("village", "")).strip()[:60]
        if not name or not ph or not sector or not village or not Q1("SELECT 1 x FROM districts WHERE name=?", (dist,)): flash("Enter the farmer's name, a valid phone, sector and village.", "err")
        elif Q1("SELECT 1 x FROM users WHERE phone=?", (ph,)): flash("This phone number is already registered.", "err")
        else:
            pw = secrets.token_urlsafe(6).replace("-", "x").replace("_", "y") + "7"
            X("INSERT INTO users(name,email,phone,pw_hash,role,district,sector,village,lang) VALUES(?,?,?,?,'farmer',?,?,?,'rw')", (name, f"p{ph}@phone.kiza", ph, generate_password_hash(pw), dist, sector, village))
            audit("advisor.register_farmer", f"{name} {dist}/{village}"); flash(f"Farmer registered. Login: {ph} - password: {pw} (shown once; give it to the farmer).", "ok")
        return redirect("/advisor/farmers")
    q = request.args.get("q", "").strip().lower(); w = ""; qa = ()
    if q: w = " AND (lower(us.name) LIKE ? OR us.phone LIKE ?)"; qa = ("%" + q + "%",) * 2
    rows = Q("SELECT us.id, us.name, us.phone, us.district, us.sector, us.village, (SELECT COUNT(*) FROM farms fa WHERE fa.user_id=us.id) farms, (SELECT COALESCE(ROUND(SUM(f.size_ha),1),0) FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=us.id AND f.status NOT IN ('Harvested','Failed')) ha, "
             "(SELECT GROUP_CONCAT(DISTINCT f.crop) FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=us.id AND f.status NOT IN ('Harvested','Failed')) crops, "
             "(SELECT COUNT(*) FROM listings l WHERE l.seller_id=us.id AND l.status!='Withdrawn') listings FROM users us WHERE us.role='farmer' AND us.status='active' AND us.email NOT LIKE '%@guest.kiza'" + w + a_scope(u, "us.")[0] + " ORDER BY us.name LIMIT 300", qa + a_scope(u, "us.")[1])
    return render_template("v9/advisor_farmers.html", rows=rows, f=request.args, ds=Q("SELECT name FROM districts ORDER BY name"))

# ------------------------------------------------------------------ admin: full control
@bp.get("/admin")
@need("admin")
def admin_home():
    roles = {r["role"]: r["c"] for r in Q("SELECT role, COUNT(*) c FROM users WHERE email NOT LIKE '%@guest.kiza' GROUP BY role")}
    k = Q1("SELECT (SELECT COUNT(*) FROM farms) farms,(SELECT COALESCE(SUM(size_ha),0) FROM fields WHERE status NOT IN ('Planned','Prepared','Failed')) ha,"
           "(SELECT COUNT(*) FROM listings WHERE status IN ('Available','Offer Received','Reserved')) live,(SELECT COUNT(*) FROM listings WHERE verify_status='Pending' AND status!='Withdrawn') pending,"
           "(SELECT COUNT(*) FROM listings WHERE harvest_date>date('now') AND status!='Withdrawn') sched,(SELECT COUNT(*) FROM offers WHERE status='Pending') offers,"
           "(SELECT COALESCE(SUM(qty_kg*price_kg),0) FROM offers WHERE status='Completed') gmv,(SELECT COUNT(*) FROM offers WHERE status='Completed') deals,"
           "(SELECT COUNT(*) FROM distress_reports WHERE status!='Resolved') distress,(SELECT COUNT(*) FROM tickets WHERE status='New') tickets,(SELECT COUNT(*) FROM users WHERE email LIKE '%@guest.kiza') guests,"
           "(SELECT COUNT(*) FROM users WHERE status!='active') blocked,(SELECT COUNT(*) FROM issue_reports WHERE status IN ('Submitted','Assigned','Under Review')) issues")
    logs = Q("SELECT a.*, u.name uname FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 8")
    stale = inv.reconcile()
    return render_template("v9/admin_home.html", roles=roles, k=k, logs=logs, stale=stale, news=Q("SELECT * FROM users WHERE email NOT LIKE '%@guest.kiza' ORDER BY id DESC LIMIT 6"))

@bp.route("/admin/create-user", methods=["POST"])
@need("admin")
def admin_create_user():
    f = request.form; role = f.get("role"); name = f.get("name", "").strip()[:80]; ph = norm_phone(f.get("phone")); dist = f.get("district"); email = f.get("email", "").strip().lower()
    if role not in ("farmer", "buyer", "extension", "government", "admin") or not name or not ph or not Q1("SELECT 1 x FROM districts WHERE name=?", (dist,)): flash("Enter name, valid phone, role and district.", "err")
    elif role == "extension" and not f.get("village", "").strip() and f.get("level") != "district": flash("A village advisor needs a village (or choose district officer).", "err")
    elif Q1("SELECT 1 x FROM users WHERE phone=?", (ph,)) or (email and Q1("SELECT 1 x FROM users WHERE email=?", (email,))): flash("This phone or email is already registered.", "err")
    else:
        pw = secrets.token_urlsafe(6).replace("-", "x").replace("_", "y") + "7"
        X("INSERT INTO users(name,email,phone,pw_hash,role,district,sector,village,lang) VALUES(?,?,?,?,?,?,?,?,?)", (name, email or f"p{ph}@phone.kiza", ph, generate_password_hash(pw), role, dist, f.get("sector", "").strip()[:60], f.get("village", "").strip()[:60] if role in ("extension", "farmer") else "", f.get("lang", "rw")))
        audit("admin.create_user", f"{role} {name}"); flash(f"Account created. Login: {ph} - password: {pw} (shown once; give it to the user).", "ok")
    return redirect("/admin/users")

@bp.route("/admin/listings", methods=["GET", "POST"])
@need("admin")
def admin_listings():
    if request.method == "POST":
        l = Q1("SELECT * FROM listings WHERE id=?", (request.form.get("id"),)); act = request.form.get("act")
        if not l or act not in ("withdraw", "restore"): abort(400)
        if act == "withdraw":
            X("UPDATE listings SET status='Withdrawn' WHERE id=?", (l["id"],)); notify(l["seller_id"], "system", f"Your {l['crop']} listing was removed by the administrator.", "/market")
        elif l["status"] == "Withdrawn": X("UPDATE listings SET status=? WHERE id=?", ("Available" if l["available_kg"] > 0 else "Sold", l["id"]))
        audit("admin.listing." + act, str(l["id"])); flash("Done.", "ok"); return redirect("/admin/listings")
    st = request.args.get("st", "")
    w = {"live": "l.status IN ('Available','Offer Received','Reserved')", "pending": "l.verify_status='Pending' AND l.status!='Withdrawn'", "scheduled": "l.harvest_date>date('now') AND l.status!='Withdrawn'", "withdrawn": "l.status='Withdrawn'"}.get(st, "1=1")
    rows = Q("SELECT l.*, u.name seller, u.phone sphone FROM listings l JOIN users u ON u.id=l.seller_id WHERE " + w + " ORDER BY l.id DESC LIMIT 150")
    return render_template("v9/admin_listings.html", rows=rows, st=st)

@bp.route("/admin/broadcast", methods=["GET", "POST"])
@need("admin")
def admin_broadcast():
    if request.method == "POST":
        msg = request.form.get("message", "").strip()[:300]; role = request.form.get("role", ""); dist = request.form.get("district", "")
        if len(msg) < 5: flash("Write the message (at least 5 characters).", "err"); return redirect("/admin/broadcast")
        w, a = ["status='active'", "email NOT LIKE '%@guest.kiza'"], []
        if role in ("farmer", "buyer", "extension", "government"): w.append("role=?"); a.append(role)
        if dist and Q1("SELECT 1 x FROM districts WHERE name=?", (dist,)): w.append("district=?"); a.append(dist)
        us = Q("SELECT id FROM users WHERE " + " AND ".join(w), tuple(a))
        for x in us: notify(x["id"], "announcement", "📣 " + msg, "/notifications")
        audit("admin.broadcast", f"{len(us)} users"); flash(f"Message sent to {len(us)} user(s).", "ok"); return redirect("/admin/broadcast")
    return render_template("v9/admin_broadcast.html", ds=Q("SELECT name FROM districts ORDER BY name"))

@bp.route("/admin/govdata", methods=["GET", "POST"])
@need("admin")
def admin_govdata():
    """Poverty rates and production history that feed the government dashboard (edit a rate, or upload CSV)."""
    if request.method == "POST":
        kind = request.form.get("kind"); up = request.files.get("file")
        try:
            if kind == "poverty_one":
                d = request.form["district"]; v = fnum("rate", 0, 100); assert Q1("SELECT 1 x FROM districts WHERE name=?", (d,))
                X("INSERT INTO poverty_index(district,poverty_rate,year,source,is_official) VALUES(?,?,?,?,1) ON CONFLICT(district) DO UPDATE SET poverty_rate=excluded.poverty_rate, year=excluded.year, source=excluded.source, is_official=1, updated_at=CURRENT_TIMESTAMP",
                  (d, v, request.form.get("year", "")[:9], request.form.get("source", "").strip()[:200] or "Admin entry"))
                audit("govdata.poverty", d); flash("Poverty rate saved.", "ok")
            elif kind in ("poverty_csv", "production_csv") and up and up.filename:
                rows = list(csv.DictReader(io.StringIO(up.read().decode("utf-8-sig")))); n = bad = 0; ds = {r["name"] for r in Q("SELECT name FROM districts")}
                for r in rows:
                    try:
                        d = (r.get("district") or "").strip(); assert d in ds
                        if kind == "poverty_csv":
                            X("INSERT INTO poverty_index(district,poverty_rate,extreme_rate,year,source,is_official) VALUES(?,?,?,?,?,1) ON CONFLICT(district) DO UPDATE SET poverty_rate=excluded.poverty_rate, extreme_rate=excluded.extreme_rate, year=excluded.year, source=excluded.source, is_official=1, updated_at=CURRENT_TIMESTAMP",
                              (d, float(r["poverty_rate"]), float(r["extreme_rate"]) if r.get("extreme_rate") else None, (r.get("year") or "")[:9], (r.get("source") or "CSV upload")[:200]))
                        else:
                            assert Q1("SELECT 1 x FROM crops WHERE name=?", (r["crop"].strip(),)); y = int(r["year"]); assert 1990 < y <= THIS_YEAR()
                            X("INSERT INTO production_history(district,year,crop,tonnes,source,is_demo) VALUES(?,?,?,?,?,0) ON CONFLICT(district,year,crop) DO UPDATE SET tonnes=excluded.tonnes, source=excluded.source, is_demo=0", (d, y, r["crop"].strip(), float(r["tonnes"]), (r.get("source") or "CSV upload")[:200]))
                        n += 1
                    except Exception: bad += 1
                audit("govdata." + kind, f"{n} ok {bad} rejected"); flash(f"{n} row(s) saved, {bad} rejected (unknown district/crop or bad number).", "ok" if n else "err")
            elif kind == "clear_demo":
                X("DELETE FROM production_history WHERE is_demo=1"); audit("govdata.clear_demo"); flash("Demo production series removed.", "ok")
        except Exception: flash("Please check the values.", "err")
        return redirect("/admin/govdata")
    return render_template("v9/admin_govdata.html", pov=Q("SELECT d.name, p.* FROM districts d LEFT JOIN poverty_index p ON p.district=d.name ORDER BY p.poverty_rate DESC"),
                           hist=Q1("SELECT COUNT(*) n, COALESCE(SUM(is_demo),0) demo, MIN(year) y0, MAX(year) y1 FROM production_history"))

SETTING_KEYS = ["contact_email", "contact_phone", "contact_whatsapp", "contact_address", "facebook", "x", "instagram", "youtube", "linkedin"]
SETTING_DEFAULTS = {"contact_email": "info@kiza-agri.rw", "contact_phone": "+250 788 000 000", "contact_whatsapp": "250788000000", "contact_address": "Kigali, Rwanda",
                    "facebook": "https://www.facebook.com/", "x": "https://x.com/", "instagram": "https://www.instagram.com/", "youtube": "https://www.youtube.com/", "linkedin": "https://www.linkedin.com/"}
def site_settings():
    try: s = {r["k"]: r["v"] for r in Q("SELECT k,v FROM site_settings")}
    except Exception: s = {}
    return {k: (s.get(k) or SETTING_DEFAULTS[k]) for k in SETTING_KEYS}

@bp.app_context_processor
def _inject():
    return {"site": site_settings()}

@bp.route("/admin/settings", methods=["GET", "POST"])
@need("admin")
def admin_settings():
    if request.method == "POST":
        for k in SETTING_KEYS:
            v = request.form.get(k, "").strip()[:200]
            if k in ("facebook", "x", "instagram", "youtube", "linkedin") and v and not v.startswith(("https://", "http://")): continue
            X("INSERT INTO site_settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
        audit("admin.settings"); flash("Settings saved.", "ok"); return redirect("/admin/settings")
    return render_template("v9/admin_settings.html", s=site_settings(), keys=SETTING_KEYS)

# ------------------------------------------------------------------ farmer: sold elsewhere / still available
@bp.post("/market/<int:lid>/sold-outside")
@need("farmer")
def sold_outside(lid):
    """The farmer found a buyer outside KIZA-AGRI: take those kilograms off the market (all, or part)."""
    l = Q1("SELECT * FROM listings WHERE id=? AND seller_id=?", (lid, g.user["id"]))
    if not l or l["status"] == "Withdrawn": abort(403)
    try: q = fnum("qty_kg", .1, 1e8, opt=True) or l["available_kg"]; assert q <= l["available_kg"] + 1e-6
    except Exception: flash("The quantity must be within what is still available.", "err"); return redirect("/market")
    note = request.form.get("note", "").strip()[:200]; c = _c()
    c.execute("UPDATE listings SET available_kg=MAX(available_kg-?,0), sold_kg=COALESCE(sold_kg,0)+?, sold_outside_kg=COALESCE(sold_outside_kg,0)+?, outside_note=? WHERE id=?", (q, q, q, note, lid))
    left = c.execute("SELECT available_kg, COALESCE(reserved_kg,0) FROM listings WHERE id=?", (lid,)).fetchone()
    c.execute("INSERT INTO stock_movements(listing_id,kind,qty_kg,available_after,reserved_after,actor_id) VALUES(?,?,?,?,?,?)", (lid, "adjust", q, left[0], left[1], g.user["id"]))
    for o in Q("SELECT * FROM offers WHERE listing_id=? AND status='Pending' AND qty_kg>?", (lid, left[0])):
        c.execute("UPDATE offers SET status='Cancelled' WHERE id=?", (o["id"],)); notify(o["buyer_id"], "offer", f"Your {l['crop']} offer ({o['qty_kg']:.0f} kg) was cancelled: the farmer sold this stock elsewhere.", "/offers")
    c.execute("UPDATE listings SET status=CASE WHEN available_kg<=0 AND COALESCE(reserved_kg,0)<=0 THEN 'Sold' ELSE status END WHERE id=? AND status!='Withdrawn'", (lid,)); c.commit()
    audit("listing.sold_outside", f"{lid} {q}kg"); flash(f"{q:.0f} kg removed from the market. Thank you for keeping stock accurate.", "ok"); return redirect("/market")

@bp.post("/market/<int:lid>/still-available")
@need("farmer")
def still_available(lid):
    if not Q1("SELECT 1 x FROM listings WHERE id=? AND seller_id=?", (lid, g.user["id"])): abort(403)
    X("UPDATE listings SET last_confirmed=? WHERE id=?", (today(), lid)); flash("Thank you - your listing stays on the market.", "ok"); return redirect(request.referrer or "/market")

def norm_phone(p):
    d = re.sub(r"\D", "", p or "")
    if d.startswith("250"): d = "0" + d[3:]
    if len(d) == 9 and d[0] == "7": d = "0" + d
    return d if re.fullmatch(r"07[2389]\d{7}", d) else None

def init(app):
    seed()
