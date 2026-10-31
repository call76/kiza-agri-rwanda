"""Farmer records (expenses, harvest, season economics) + general issue reporting with secure photos + advisor review."""
import os, io, secrets, datetime as dt
from flask import Blueprint, request, redirect, render_template, flash, g, abort, send_file
from .core import Q, Q1, X, T, audit, need, notify, fnum, today, ts, UPLOADS_PRIVATE

bp = Blueprint("farm8", __name__)
STAFF = ("extension", "government", "admin")
EXP_CATS = ("seed", "fertilizer", "pesticide", "labor", "transport", "other")
ISSUE_CATS = ("crop_disease", "pests", "soil", "water", "weather_damage", "fertilizer_seed", "livestock", "infrastructure", "other")
URGENCY = ("low", "normal", "high", "critical")
# allowed status transitions (advisor/staff). Farmers only move Info Requested -> Under Review by replying.
FLOW = {"Submitted": ("Assigned", "Rejected", "Info Requested"), "Assigned": ("Under Review", "Rejected", "Info Requested"),
        "Under Review": ("Action Recommended", "Rejected", "Info Requested"), "Info Requested": ("Under Review", "Rejected"),
        "Action Recommended": ("Resolved", "Under Review"), "Resolved": (), "Rejected": ()}
MAX_IMG = int(os.environ.get("KIZA_MAX_IMAGE_MB", "5")) * 1024 * 1024

def own_field(fid, uid):
    return Q1("SELECT f.*, fa.name farm, fa.user_id, fa.district FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE f.id=? AND fa.user_id=?", (fid, uid))   # resource-level authz: id in URL is never trusted

def _year(d): return int(str(d)[:4])

# ====================== season economics ======================
def season_summary(uid):
    """Per crop+year: production (verified vs estimated kept apart), area, yield/ha, costs, revenue from COMPLETED deals, recorded net margin."""
    fields = Q("SELECT f.id, f.crop, f.size_ha, f.name FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=?", (uid,)); fid = {f["id"]: f for f in fields}
    rows = {}
    def row(crop, y): return rows.setdefault((crop, y), dict(crop=crop, year=y, area_ha=0.0, verified_kg=0.0, unverified_kg=0.0, estimated_kg=0.0, cost=0.0, revenue=0.0, has_actual=False, area_seen=set()))
    for h in Q("SELECT h.* FROM harvest_records h JOIN fields f ON f.id=h.field_id JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=?", (uid,)):
        r = row(h["crop"] or fid[h["field_id"]]["crop"], h["season_year"])
        if h["field_id"] not in r["area_seen"]: r["area_seen"].add(h["field_id"]); r["area_ha"] += fid[h["field_id"]]["size_ha"]
        if h["actual_kg"] is not None:
            r["has_actual"] = True
            if h["verify_status"] == "Verified": r["verified_kg"] += h["actual_kg"]
            else: r["unverified_kg"] += h["actual_kg"]
        elif h["estimated_kg"] is not None: r["estimated_kg"] += h["estimated_kg"]
    for e in Q("SELECT e.*, f.crop FROM expenses e JOIN fields f ON f.id=e.field_id JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=?", (uid,)):
        row(e["crop"], _year(e["spent_on"]))["cost"] += e["total_rwf"]
    for o in Q("SELECT o.qty_kg*o.price_kg rev, l.crop, o.completed_at FROM offers o JOIN listings l ON l.id=o.listing_id WHERE l.seller_id=? AND o.status='Completed' AND o.completed_at IS NOT NULL", (uid,)):
        row(o["crop"], _year(o["completed_at"]))["revenue"] += o["rev"]
    out = []
    for (crop, y), r in sorted(rows.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        r.pop("area_seen"); prod = r["verified_kg"] + r["unverified_kg"]
        r["production_kg"] = prod if r["has_actual"] else None
        r["yield_kg_ha"] = round(prod / r["area_ha"]) if r["has_actual"] and r["area_ha"] > 0 else None     # None = not computable, never 0
        r["net_margin"] = r["revenue"] - r["cost"] if (r["revenue"] or r["cost"]) else None
        out.append(r)
    return out

def compare(rows):
    """Year-on-year per crop with the numbers behind the verdict."""
    res = []
    by = {}
    for r in rows: by.setdefault(r["crop"], {})[r["year"]] = r
    for crop, ys in by.items():
        yrs = sorted(ys)
        if len(yrs) < 2: continue
        a, b = ys[yrs[-2]], ys[yrs[-1]]; d = {"crop": crop, "prev": a, "cur": b}
        if a["yield_kg_ha"] and b["yield_kg_ha"]:
            ch = (b["yield_kg_ha"] / a["yield_kg_ha"] - 1) * 100; d["yield_change_pct"] = round(ch, 1); d["verdict"] = "improved" if ch > 2 else "declined" if ch < -2 else "stable"
        else: d["yield_change_pct"] = None; d["verdict"] = "insufficient"
        d["cost_change_pct"] = round((b["cost"] / a["cost"] - 1) * 100, 1) if a["cost"] and b["cost"] else None
        res.append(d)
    return res

@bp.get("/farmer/records")
@need("farmer")
def records():
    u = g.user
    fields = Q("SELECT f.*, fa.name farm FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=? ORDER BY fa.name, f.name", (u["id"],))
    exps = Q("SELECT e.*, f.name field, f.crop FROM expenses e JOIN fields f ON f.id=e.field_id JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=? ORDER BY e.spent_on DESC, e.id DESC LIMIT 50", (u["id"],))
    hv = Q("SELECT h.*, f.name field FROM harvest_records h JOIN fields f ON f.id=h.field_id JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=? ORDER BY h.season_year DESC, h.id DESC", (u["id"],))
    rows = season_summary(u["id"])
    return render_template("v8/records.html", fields=fields, exps=exps, hv=hv, rows=rows, cmp=compare(rows), cats=EXP_CATS, year=dt.date.today().year, today=today())

@bp.post("/farmer/records/expense")
@need("farmer")
def add_expense():
    f = own_field(request.form.get("field_id", type=int), g.user["id"])
    if not f: abort(403)
    try:
        cat = request.form["category"]; assert cat in EXP_CATS
        q = fnum("quantity", 0, 1e9, opt=True); uc = fnum("unit_cost", 0, 1e9, opt=True); tot = fnum("total", 0, 1e10, opt=True)
        total = round(q * uc, 2) if (q is not None and uc is not None) else tot
        assert total is not None
        on = request.form.get("spent_on") or today(); dt.date.fromisoformat(on)
        X("INSERT INTO expenses(field_id,category,item,quantity,unit,unit_cost_rwf,total_rwf,spent_on) VALUES(?,?,?,?,?,?,?,?)", (f["id"], cat, request.form.get("item", "")[:80], q, request.form.get("unit", "")[:12], uc, total, on))
        audit("expense.add", f"field {f['id']} {cat} {total:.0f}"); flash(T("rec.expense_saved"), "ok")
    except Exception: flash(T("rec.expense_invalid"), "err")
    return redirect("/farmer/records")

@bp.post("/farmer/records/harvest")
@need("farmer")
def add_harvest():
    f = own_field(request.form.get("field_id", type=int), g.user["id"])
    if not f: abort(403)
    try:
        y = int(request.form["season_year"]); assert 2000 <= y <= dt.date.today().year + 1; se = request.form.get("season", "A")[:6]
        est = fnum("estimated_kg", 0, 1e9, opt=True); act = fnum("actual_kg", 0, 1e9, opt=True); lost = fnum("lost_kg", 0, 1e9, opt=True) or 0
        assert est is not None or act is not None
        if act is not None: assert lost <= act
        ex = Q1("SELECT * FROM harvest_records WHERE field_id=? AND season_year=? AND season=?", (f["id"], y, se))
        if ex and ex["verify_status"] == "Verified" and act is not None and act != ex["actual_kg"]: flash(T("rec.locked"), "err"); return redirect("/farmer/records")
        st = "Submitted" if act is not None else "Estimated"
        X("INSERT INTO harvest_records(field_id,season_year,season,crop,estimated_kg,actual_kg,lost_kg,verify_status,harvested_on) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(field_id,season_year,season) DO UPDATE SET estimated_kg=COALESCE(excluded.estimated_kg,estimated_kg), actual_kg=COALESCE(excluded.actual_kg,actual_kg), lost_kg=excluded.lost_kg, "
          "verify_status=CASE WHEN harvest_records.verify_status='Verified' THEN 'Verified' ELSE excluded.verify_status END, harvested_on=COALESCE(excluded.harvested_on,harvested_on)", (f["id"], y, se, f["crop"], est, act, lost, st, today() if act is not None else None))
        audit("harvest.record", f"field {f['id']} {y}{se}"); flash(T("rec.harvest_saved"), "ok")
    except Exception: flash(T("rec.harvest_invalid"), "err")
    return redirect("/farmer/records")

@bp.route("/advisor/harvests", methods=["GET", "POST"])
@need(*STAFF)
def verify_harvests():
    u = g.user; sc, a = ("", ()) if u["role"] != "extension" else (" AND fa.district=?", (u["district"],))
    if request.method == "POST":
        h = Q1("SELECT h.*, fa.district, fa.user_id farmer FROM harvest_records h JOIN fields f ON f.id=h.field_id JOIN farms fa ON fa.id=f.farm_id WHERE h.id=?" + sc, (request.form.get("id", type=int),) + a)
        act = request.form.get("act"); note = request.form.get("note", "").strip()[:300]
        if not h or h["verify_status"] != "Submitted" or act not in ("verify", "reject"): abort(403)
        if act == "reject" and len(note) < 5: flash(T("rec.reason_required"), "err"); return redirect("/advisor/harvests")
        new = "Verified" if act == "verify" else "Rejected"
        X("UPDATE harvest_records SET verify_status=?, verified_by=?, verified_at=?, verify_note=? WHERE id=?", (new, u["id"], ts(), note, h["id"]))
        notify(h["farmer"], "harvest", T("rec.notify_" + act), "/farmer/records"); audit("harvest." + act, f"{h['id']} {note[:80]}"); flash(T("rec.harvest_" + act), "ok"); return redirect("/advisor/harvests")
    rows = Q("SELECT h.*, f.name field, fa.name farm, fa.district, u.name farmer FROM harvest_records h JOIN fields f ON f.id=h.field_id JOIN farms fa ON fa.id=f.farm_id JOIN users u ON u.id=fa.user_id WHERE h.verify_status='Submitted'" + sc + " ORDER BY h.id", a)
    return render_template("v8/harvest_verify.html", rows=rows)

# ====================== issue reports ======================
def save_image(file_storage):
    """Validate + sanitise an upload. Returns (stored_name, bytes, w, h). Raises ValueError(code). Re-encoding drops EXIF/GPS and any embedded payload."""
    from PIL import Image, ImageOps
    if not file_storage or not file_storage.filename: return None
    raw = file_storage.stream.read(MAX_IMG + 1)
    if len(raw) > MAX_IMG: raise ValueError("img_big")
    if len(raw) < 100: raise ValueError("img_bad")
    try:
        im = Image.open(io.BytesIO(raw)); fmt = im.format; im.verify(); im = Image.open(io.BytesIO(raw))
        if fmt not in ("JPEG", "PNG", "WEBP"): raise ValueError("img_type")
        if im.width * im.height > 40_000_000: raise ValueError("img_big")
        im = ImageOps.exif_transpose(im).convert("RGB"); im.thumbnail((1600, 1600))
    except ValueError: raise
    except Exception: raise ValueError("img_bad")
    os.makedirs(UPLOADS_PRIVATE, exist_ok=True); name = secrets.token_hex(16) + ".jpg"; path = os.path.join(UPLOADS_PRIVATE, name)
    im.save(path, "JPEG", quality=85); return name, os.path.getsize(path), im.width, im.height

def _can_see_issue(u, i):
    if u["role"] == "farmer": return i["farmer_id"] == u["id"]
    if u["role"] == "extension": return (Q1("SELECT district FROM users WHERE id=?", (i["farmer_id"],)) or {}).get("district") == u["district"]
    return u["role"] in ("government", "admin")

def _move(i, to, actor, note=""):
    if to not in FLOW.get(i["status"], ()): raise ValueError("bad_transition")
    X("UPDATE issue_reports SET status=?, updated_at=? WHERE id=?", (to, ts(), i["id"]))
    X("INSERT INTO issue_events(issue_id,actor_id,from_status,to_status,note) VALUES(?,?,?,?,?)", (i["id"], actor, i["status"], to, note[:500]))

@bp.route("/issues")
@need("farmer")
def issues():
    return render_template("v8/issues.html", rows=Q("SELECT * FROM issue_reports WHERE farmer_id=? ORDER BY id DESC", (g.user["id"],)))

@bp.route("/issues/new", methods=["GET", "POST"])
@need("farmer")
def issue_new():
    u = g.user; fields = Q("SELECT f.id, f.name, fa.name farm, fa.id farm_id, f.crop FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=?", (u["id"],)); farms = Q("SELECT id,name FROM farms WHERE user_id=?", (u["id"],))
    if request.method == "POST":
        try:
            cat = request.form.get("category", ""); assert cat in ISSUE_CATS
            desc = request.form.get("description", "").strip(); assert 10 <= len(desc) <= 2000
            urg = request.form.get("urgency", "normal"); assert urg in URGENCY
            fid = request.form.get("field_id", type=int); fm = request.form.get("farm_id", type=int)
            if fid: f = own_field(fid, u["id"]); assert f; fm = f["farm_id"]
            elif fm: assert Q1("SELECT 1 x FROM farms WHERE id=? AND user_id=?", (fm, u["id"]))
            on = request.form.get("observed_on") or today(); dt.date.fromisoformat(on)
            lat, lng = fnum("lat", -3, 0, opt=True), fnum("lng", 28, 31, opt=True)
            img = save_image(request.files.get("photo"))
            iid = X("INSERT INTO issue_reports(farmer_id,farm_id,field_id,category,description,lang,urgency,lat,lng,observed_on) VALUES(?,?,?,?,?,?,?,?,?,?)", (u["id"], fm, fid, cat, desc, u["lang"] or "en", urg, lat, lng, on))
            if img: X("INSERT INTO issue_attachments(issue_id,stored_name,bytes,width,height) VALUES(?,?,?,?,?)", (iid, *img))
            X("INSERT INTO issue_events(issue_id,actor_id,from_status,to_status,note) VALUES(?,?,?,?,?)", (iid, u["id"], None, "Submitted", ""))
            for s in Q("SELECT id FROM users WHERE role='extension' AND status='active' AND district=?", (u["district"],)): notify(s["id"], "issue", T("iss.notify_new"), "/issues/inbox")
            audit("issue.create", f"{iid} {cat}"); flash(T("iss.saved"), "ok"); return redirect(f"/issues/{iid}")
        except ValueError as e:
            code = str(e); flash(T("iss." + code) if code in ("img_big", "img_bad", "img_type") else T("iss.invalid"), "err")
        except Exception: flash(T("iss.invalid"), "err")
    return render_template("v8/issue_new.html", fields=fields, farms=farms, cats=ISSUE_CATS, urg=URGENCY, today=today(), f=request.form)

@bp.route("/issues/<int:iid>", methods=["GET", "POST"])
@need()
def issue(iid):
    u = g.user; i = Q1("SELECT r.*, usr.name farmer, usr.district farmer_district FROM issue_reports r JOIN users usr ON usr.id=r.farmer_id WHERE r.id=?", (iid,))
    if not i or not _can_see_issue(u, i): abort(404)            # 404 not 403: do not reveal that the id exists
    if request.method == "POST":
        act = request.form.get("act"); note = request.form.get("note", "").strip()[:1000]
        try:
            if u["role"] == "farmer":
                assert act == "reply" and i["status"] == "Info Requested" and len(note) >= 3; _move(i, "Under Review", u["id"], note)
            else:
                assert u["role"] in STAFF
                if act == "assign": assert i["status"] == "Submitted"; X("UPDATE issue_reports SET advisor_id=? WHERE id=?", (u["id"], iid)); _move(i, "Assigned", u["id"], note)
                elif act == "review": X("UPDATE issue_reports SET advisor_id=COALESCE(advisor_id,?) WHERE id=?", (u["id"], iid)); _move(i, "Under Review", u["id"], note)
                elif act == "recommend": assert len(note) >= 10; X("UPDATE issue_reports SET recommendation=? WHERE id=?", (note, iid)); _move(i, "Action Recommended", u["id"], note)
                elif act == "request_info": assert len(note) >= 5; _move(i, "Info Requested", u["id"], note)
                elif act == "reject": assert len(note) >= 5; _move(i, "Rejected", u["id"], note)
                elif act == "resolve": _move(i, "Resolved", u["id"], note)
                else: raise AssertionError
            notify(i["farmer_id"] if u["role"] != "farmer" else (i["advisor_id"] or u["id"]), "issue", T("iss.notify_update"), f"/issues/{iid}")
            audit("issue." + act, f"{iid} {act}"); flash(T("iss.updated"), "ok")
        except (AssertionError, ValueError): flash(T("iss.cannot"), "err")
        return redirect(f"/issues/{iid}")
    ev = Q("SELECT e.*, u.name actor, u.role arole FROM issue_events e LEFT JOIN users u ON u.id=e.actor_id WHERE e.issue_id=? ORDER BY e.id", (iid,))
    return render_template("v8/issue.html", i=i, ev=ev, att=Q("SELECT id FROM issue_attachments WHERE issue_id=?", (iid,)), next=FLOW[i["status"]], staff=u["role"] in STAFF)

@bp.get("/issues/photo/<int:aid>")
@need()
def issue_photo(aid):
    a = Q1("SELECT a.stored_name, r.farmer_id FROM issue_attachments a JOIN issue_reports r ON r.id=a.issue_id WHERE a.id=?", (aid,))
    if not a or not _can_see_issue(g.user, a): abort(404)
    r = send_file(os.path.join(UPLOADS_PRIVATE, a["stored_name"]), mimetype="image/jpeg"); r.headers["Cache-Control"] = "private, no-store"; r.headers["X-Content-Type-Options"] = "nosniff"; return r

@bp.get("/issues/inbox")
@need(*STAFF)
def issue_inbox():
    u = g.user; sc, a = ("", ()) if u["role"] != "extension" else (" AND usr.district=?", (u["district"],))
    st = request.args.get("status", ""); w = ""
    if st in FLOW: w = " AND r.status=?"; a = a + (st,)
    rows = Q("SELECT r.*, usr.name farmer, usr.district FROM issue_reports r JOIN users usr ON usr.id=r.farmer_id WHERE 1=1" + sc + w + " ORDER BY CASE r.urgency WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, r.id DESC LIMIT 200", a)
    return render_template("v8/issue_inbox.html", rows=rows, statuses=list(FLOW), cur=st)
