"""Government analytics, admin operations console, farmer SMS consent, provider delivery webhook."""
import os, hmac
from flask import Blueprint, request, redirect, render_template, flash, g, abort, jsonify
from .core import Q, Q1, X, T, audit, need, today, _c, catalog, reload_catalogs, ts
from . import prices as P, inventory as inv, sms, alerts, pipeline, yieldml

bp = Blueprint("ops8", __name__)
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@bp.get("/gov/analytics")
@need("government", "admin", "extension")
def gov_analytics():
    u = g.user; district = request.args.get("district", "")
    if u["role"] == "extension": district = u["district"]          # district officers are limited to their own district
    if district and not Q1("SELECT 1 x FROM districts WHERE name=?", (district,)): abort(404)
    w, a = ("AND fa.district=?", (district,)) if district else ("", ())
    prod = Q("""SELECT fa.district, f.crop, h.season_year yr, SUM(CASE WHEN h.verify_status='Verified' THEN h.actual_kg END) verified_kg, SUM(CASE WHEN h.verify_status IN ('Submitted','Rejected') THEN h.actual_kg END) unverified_kg,
        SUM(CASE WHEN h.actual_kg IS NULL THEN h.estimated_kg END) estimated_kg, SUM(CASE WHEN h.verify_status='Verified' THEN f.size_ha END) ver_area, COUNT(*) records
        FROM harvest_records h JOIN fields f ON f.id=h.field_id JOIN farms fa ON fa.id=f.farm_id WHERE 1=1 """ + w + " GROUP BY fa.district, f.crop, h.season_year ORDER BY h.season_year DESC, fa.district, f.crop", a)
    for r in prod: r["yield_kg_ha"] = round(r["verified_kg"] / r["ver_area"]) if r["verified_kg"] and r["ver_area"] else None
    crop = request.args.get("crop") or "Maize"; c = _c()
    prices = P.by_district(c, crop) if Q1("SELECT 1 x FROM crops WHERE name=?", (crop,)) else []
    if district: prices = [p for p in prices if p["district"] == district]
    comp = Q1("""SELECT COUNT(*) total, SUM(CASE WHEN observed_on>=date('now','-45 day') THEN 1 ELSE 0 END) recent, SUM(is_simulated) simulated, MAX(observed_on) newest FROM price_observations""")
    nisr = Q("SELECT * FROM nisr_indicators ORDER BY year DESC, indicator LIMIT 50")
    return render_template("v8/gov_analytics.html", prod=prod, prices=prices, crop=crop, district=district, ds=Q("SELECT name FROM districts ORDER BY name"), crops=Q("SELECT name FROM crops ORDER BY name"), comp=comp, nisr=nisr, locked=u["role"] == "extension")

@bp.route("/admin/ops", methods=["GET", "POST"])
@need("admin")
def admin_ops():
    if request.method == "POST":
        job = request.form.get("job"); msg = ""
        if job == "alerts": n = alerts.generate(); q = alerts.notify_farmers(); d = sms.dispatch(); msg = f"alerts+{n}, sms queued {q}, dispatch {d}"
        elif job == "backfill": msg = f"price rows added: {P.backfill(_c())}"
        elif job == "yield": msg = str(yieldml.train())
        elif job == "nisr": rid = pipeline.import_nisr_csv(os.path.join(BASE, "data", "templates", "nisr_sas_SAMPLE_SYNTHETIC.csv")); msg = "NISR sample run " + rid
        elif job == "reconcile": bad = inv.reconcile(); msg = "stock OK" if not bad else f"stock mismatch on listings {bad}"
        elif job == "dispatch": msg = str(sms.dispatch())
        else: abort(400)
        audit("ops." + job, msg[:200]); flash(msg, "ok"); return redirect("/admin/ops")
    en, rw = set(catalog("en")), set(catalog("rw"))
    s = lambda q, a=(): Q1(q, a)
    return render_template("v8/admin_ops.html", runs=Q("SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT 20"), sms=Q("SELECT status, COUNT(*) n FROM sms_outbox GROUP BY status"), sms_recent=Q("SELECT * FROM sms_outbox ORDER BY id DESC LIMIT 15"),
        mails=Q("SELECT id,to_addr,subject,status,created_at FROM email_outbox ORDER BY id DESC LIMIT 10"), missing_rw=sorted(en - rw), missing_en=sorted(rw - en), n_keys=len(en), models=Q("SELECT * FROM yield_models ORDER BY id DESC LIMIT 3"),
        alerts=Q("SELECT * FROM weather_alerts ORDER BY id DESC LIMIT 10"), bad_stock=inv.reconcile(), sec=Q("SELECT action, COUNT(*) n FROM audit_logs WHERE action LIKE 'password.%' OR action LIKE 'email.%' GROUP BY action"),
        schema=Q("SELECT * FROM schema_version ORDER BY version"))

@bp.post("/account/sms")
@need("farmer", "buyer")
def sms_pref():
    X("UPDATE users SET sms_optin=? WHERE id=?", (1 if request.form.get("optin") == "1" else 0, g.user["id"])); audit("sms.pref", request.form.get("optin")); flash(T("ops.sms_pref_saved"), "ok"); return redirect(request.referrer or "/profile")

@bp.post("/api/v8/sms/dlr")
def sms_dlr():
    """Provider delivery report webhook. Requires KIZA_SMS_DLR_SECRET (header X-Kiza-Secret); disabled when unset."""
    sec = os.environ.get("KIZA_SMS_DLR_SECRET")
    if not sec or not hmac.compare_digest(request.headers.get("X-Kiza-Secret", ""), sec): abort(403)
    d = request.get_json(silent=True) or {}
    return jsonify(updated=sms.delivery_report(str(d.get("id", "")), d.get("status") == "delivered"))

@bp.get("/api/v8/yield/<int:field_id>")
@need("farmer")
def api_yield(field_id):
    if not Q1("SELECT 1 x FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE f.id=? AND fa.user_id=?", (field_id, g.user["id"])): abort(404)
    r = yieldml.predict(_c(), field_id)
    return jsonify(r) if r else (jsonify(error="no estimate available for this field"), 404)
