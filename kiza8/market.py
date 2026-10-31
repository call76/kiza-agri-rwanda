"""Buyer matching (multi-farmer aggregation), price intelligence pages/APIs, public overview."""
import datetime as dt
from flask import Blueprint, request, redirect, render_template, flash, g, abort, jsonify
from .core import Q, Q1, X, T, audit, need, notify, fnum, today, _c
from . import prices as P, inventory as inv

bp = Blueprint("market8", __name__)
STAFF = ("extension", "government", "admin")
UNITS = {"kg": 1.0, "tonne": 1000.0, "bag50": 50.0, "bag100": 100.0}

def listing_state(l, today_=None):
    """Derived lifecycle: Cancelled | Pending verification | Scheduled | Sold out | Partially reserved | Expired | Active."""
    t = today_ or today()
    if l["status"] == "Withdrawn": return "cancelled"
    if l.get("verify_status") != "Verified": return "pending_verification"
    if (l["available_kg"] or 0) <= 0 and (l.get("reserved_kg") or 0) <= 0: return "sold_out"
    if l.get("harvest_date") and l["harvest_date"] > t: return "scheduled"
    if (l.get("reserved_kg") or 0) > 0 and (l["available_kg"] or 0) > 0: return "partially_reserved"
    if l.get("harvest_date") and (dt.date.fromisoformat(t) - dt.date.fromisoformat(l["harvest_date"])).days > 60 and (l.get("reserved_kg") or 0) <= 0: return "expired"
    return "active"

def match(crop, qty_kg, district=None, max_price=None, include_future=False):
    """Greedy cheapest-first fill from verified, free stock; same-district supply wins ties. Aggregation is a PROPOSAL: nobody has agreed yet."""
    w = "l.verify_status='Verified' AND l.status IN ('Available','Offer Received','Reserved') AND l.available_kg>0 AND l.crop=?"; a = [crop]
    if not include_future: w += " AND (l.harvest_date IS NULL OR l.harvest_date<=?)"; a.append(today())
    if max_price: w += " AND l.price_kg<=?"; a.append(max_price)
    ls = Q("SELECT l.*, u.name seller FROM listings l JOIN users u ON u.id=l.seller_id WHERE " + w, tuple(a))
    ls.sort(key=lambda l: (l["price_kg"], 0 if (district and l["district"] == district) else 1, l["id"]))
    left = qty_kg; lines = []
    for l in ls:
        if left <= 0: break
        take = min(left, l["available_kg"]); left -= take
        lines.append(dict(listing_id=l["id"], seller=l["seller"], district=l["district"], village=l.get("village"), take_kg=take, price_kg=l["price_kg"], subtotal=take * l["price_kg"], same_district=bool(district and l["district"] == district),
                          future=bool(l.get("harvest_date") and l["harvest_date"] > today()), harvest_date=l.get("harvest_date"), quality=l.get("quality")))
    got = qty_kg - left; cost = sum(x["subtotal"] for x in lines)
    return dict(requested_kg=qty_kg, matched_kg=got, shortfall_kg=max(0.0, left), lines=lines, total_rwf=cost, avg_price=(cost / got if got else None), complete=left <= 0,
                total_available_kg=sum(l["available_kg"] for l in ls), delivery_cost="not estimated (no verified transport tariff data)")

def match_sector(crop, qty_kg, district=None, max_price=None, include_future=False):
    """Sector-first aggregation: farmers of ONE sector (same collection point) are combined to fill the buyer's order.
    Returns best group (primary) + alternatives; if no single sector can fill it, `mixed` shows how the rest could be completed from other sectors."""
    w = "l.verify_status='Verified' AND l.status IN ('Available','Offer Received','Reserved') AND l.available_kg>0 AND l.crop=?"; a = [crop]
    if not include_future: w += " AND (l.harvest_date IS NULL OR l.harvest_date<=?)"; a.append(today())
    if max_price: w += " AND l.price_kg<=?"; a.append(max_price)
    ls = Q("SELECT l.*, u.name seller FROM listings l JOIN users u ON u.id=l.seller_id WHERE " + w, tuple(a)); groups = {}
    for l in ls: groups.setdefault((l["district"], (l.get("sector") or "-").strip().title() or "-"), []).append(l)
    out = []
    for (dist, sec), items in groups.items():
        items.sort(key=lambda l: (l["price_kg"], l["id"])); left = qty_kg; lines = []
        for l in items:
            if left <= 0: break
            take = min(left, l["available_kg"]); left -= take
            lines.append(dict(listing_id=l["id"], seller=l["seller"], district=dist, village=l.get("village"), take_kg=take, price_kg=l["price_kg"], subtotal=take * l["price_kg"], auto=bool(l.get("auto_accept")),
                              future=bool(l.get("harvest_date") and l["harvest_date"] > today()), harvest_date=l.get("harvest_date"), quality=l.get("quality")))
        got = qty_kg - left; cost = sum(x["subtotal"] for x in lines)
        out.append(dict(sector=sec, district=dist, farmers=len({x["seller"] for x in lines}), lines=lines, matched_kg=got, shortfall_kg=max(0.0, left), total_rwf=cost, avg_price=(cost / got if got else None),
                        complete=left <= 0, supply_kg=sum(l["available_kg"] for l in items), same_district=bool(district and dist == district)))
    out.sort(key=lambda g_: (not g_["complete"], 0 if g_["same_district"] else 1, (g_["avg_price"] or 0) if g_["complete"] else -g_["matched_kg"]))
    best = out[0] if out else None; mixed = None
    if best and not best["complete"]:
        mixed = match(crop, qty_kg, district, max_price, include_future)
    return dict(requested_kg=qty_kg, best=best, others=out[1:5], mixed=mixed, total_available_kg=sum(l["available_kg"] for l in ls))

@bp.route("/market/match", methods=["GET", "POST"])
@need("buyer")
def match_page():
    f = request.values; res = None; crops = Q("SELECT name FROM crops ORDER BY name"); ds = Q("SELECT name FROM districts ORDER BY name"); lines = []
    if f.get("crop"):
        try:
            qty = float(f.get("qty", 0)) * UNITS.get(f.get("unit", "kg"), 1.0); assert 0 < qty <= 1e8; mp = float(f["max_price"]) if f.get("max_price") else None
            res = match_sector(f["crop"], qty, f.get("district") or None, mp, bool(f.get("future")))
            pick = f.get("sector_pick")   # "district|sector" chosen by the buyer, else the best group
            grp = next((g_ for g_ in ([res["best"]] + res["others"]) if g_ and f"{g_['district']}|{g_['sector']}" == pick), res["best"])
            if f.get("use") == "mixed" and res["mixed"]: lines = res["mixed"]["lines"]
            elif grp: lines = grp["lines"]
        except (ValueError, AssertionError): flash(T("mkt.bad_query"), "err")
    if request.method == "POST" and res and request.form.get("send") == "1":
        made = auto = 0
        for ln in lines:
            try:
                oid = inv.create_offer(ln["listing_id"], g.user["id"], ln["take_kg"], ln["price_kg"]); made += 1
                s = Q1("SELECT seller_id,crop,auto_accept,price_kg FROM listings WHERE id=?", (ln["listing_id"],))
                if s["auto_accept"] and ln["price_kg"] >= s["price_kg"]:   # farmer pre-approved: stock leaves the market immediately
                    try: inv.accept_offer(oid, s["seller_id"]); auto += 1; notify(s["seller_id"], "offer", f"Sold automatically: {ln['take_kg']:.0f} kg {s['crop']} at {ln['price_kg']:.0f} RWF/kg (auto-accept).", "/offers")
                    except inv.StockError: pass
                else: notify(s["seller_id"], "offer", T("mkt.notify_offer", kg=f"{ln['take_kg']:.0f}", crop=s["crop"]), "/offers")
            except inv.StockError: pass
        audit("match.offers", f"{made} offers {auto} auto"); flash(T("mkt.offers_sent", n=made) + (f" ({auto} accepted automatically - already reserved for you)" if auto else ""), "ok"); return redirect("/offers")
    return render_template("v8/match.html", res=res, f=f, crops=crops, ds=ds, units=list(UNITS), lines=lines)

# ---------------- price intelligence ----------------
def _intel(crop, district):
    c = _c(); fc = P.forecast_for(c, crop, district or None)
    return dict(latest=P.latest(c, crop, district or None), districts=P.by_district(c, crop), fc=fc, chart=P.chart(fc["history"], fc.get("forecast"), ) if fc["history"] else None)

@bp.get("/market/intelligence")
@need("farmer", "buyer", *STAFF)
def intelligence():
    crop = request.args.get("crop") or "Maize"; district = request.args.get("district", "")
    if not Q1("SELECT 1 x FROM crops WHERE name=?", (crop,)): abort(404)
    if district and not Q1("SELECT 1 x FROM districts WHERE name=?", (district,)): abort(404)
    return render_template("v8/intelligence.html", crop=crop, district=district, crops=Q("SELECT name FROM crops ORDER BY name"), ds=Q("SELECT name FROM districts ORDER BY name"), **_intel(crop, district))

@bp.get("/api/v8/prices")
@need("farmer", "buyer", *STAFF)
def api_prices():
    crop = request.args.get("crop", ""); district = request.args.get("district") or None
    if not Q1("SELECT 1 x FROM crops WHERE name=?", (crop,)): return jsonify(error="unknown crop"), 404
    c = _c(); l = P.latest(c, crop, district)
    return jsonify(crop=crop, district=district, latest=l, message=None if l and l["usable"] else "No recent verified price available", districts=P.by_district(c, crop))

@bp.get("/api/v8/price-forecast")
@need("farmer", "buyer", *STAFF)
def api_forecast():
    crop = request.args.get("crop", ""); district = request.args.get("district") or None
    if not Q1("SELECT 1 x FROM crops WHERE name=?", (crop,)): return jsonify(error="unknown crop"), 404
    f = P.forecast_for(_c(), crop, district); f.pop("history", None); return jsonify(f)

@bp.get("/public/prices")
def public_prices():
    """Guest-safe market overview: national latest price per crop with source/date/flags. No user, farm or admin data."""
    c = _c(); rows = []
    for cr in Q("SELECT name FROM crops ORDER BY name"):
        o = c.execute("SELECT AVG(price_rwf) p, MAX(observed_on) d, MAX(is_simulated) sim, GROUP_CONCAT(DISTINCT source) src FROM price_observations WHERE crop=? AND price_type='retail' AND observed_on=(SELECT MAX(observed_on) FROM price_observations WHERE crop=? AND price_type='retail')", (cr["name"], cr["name"])).fetchone()
        if o["p"] is None: rows.append(dict(crop=cr["name"], price=None)); continue
        age, fr = P.freshness(o["d"]); rows.append(dict(crop=cr["name"], price=round(o["p"]), day=o["d"], age=age, fr=fr, sim=bool(o["sim"]), src=o["src"]))
    return render_template("v8/public_prices.html", rows=rows)
