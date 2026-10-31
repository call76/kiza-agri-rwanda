"""v11 inputs coach: compares what the farmer RECORDED spending on seed and fertilizer per field (expenses table, kg) with a reference rate per hectare,
says whether they used too much / too little / about right, the amount to apply on the field's real size, and commonly used varieties.
Reference rates: fertilizer from the platform's fertilizer_subsidies table when present (otherwise none); seed rates are general agronomic
guidance, NOT an official RAB prescription - the UI says so and tells the farmer to confirm with the sector agronomist / agro-dealer."""
import datetime as dt
from flask import Blueprint, render_template, session, g
from .core import Q, need

bp = Blueprint("inputs", __name__)
# kg of seed per hectare (general guidance). Cassava/banana/etc. use cuttings or suckers, so no kg rate is given.
SEED = {"Maize": 25, "Sweet corn": 20, "Beans": 80, "Climbing beans": 45, "Soybean": 70, "Groundnut": 80, "Potato": 2000, "Wheat": 120, "Barley": 100,
        "Rice": 40, "Sorghum": 10, "Finger millet": 10, "Sunflower": 8, "Field peas": 100, "Cowpea": 25, "Onion": 4, "Tomato": 0.3, "Cabbage": 0.4, "Carrot": 4}
# commonly used improved varieties in Rwanda (confirm current availability with RAB / agro-dealer)
VAR = {"Maize": "ZM 607, ZM 623", "Beans": "RWR 2245 (bush)", "Climbing beans": "MAC 44, RWV 1129", "Potato": "Kinigi, Victoria, Cruza 148, Kirundo"}
TOL = (0.75, 1.25)


def _lg():
    return session.get("lang", "en") if session.get("lang") in ("rw", "fr", "en") else "en"


def P(en, rw, fr=None):
    lg = _lg(); return rw if lg == "rw" else ((fr or en) if lg == "fr" else en)


def _kg(q, unit):
    u = (unit or "kg").strip().lower()
    if q is None: return None
    if u in ("kg", "kgs", "kilo", "kilos", ""): return q
    if u in ("g", "gram", "grams"): return q / 1000
    if u in ("t", "tonne", "tonnes", "ton"): return q * 1000
    return None


def _verdict(used, rec):
    r = used / rec if rec else None
    if r is None: return "none"
    return "high" if r > TOL[1] else ("low" if r < TOL[0] else "ok")


def analyse(u, year=None):
    year = year or dt.date.today().year
    fields = Q("SELECT f.id, f.name, f.crop, f.size_ha, f.status FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=? AND f.status!='Failed' ORDER BY f.id", (u["id"],))
    out = []
    for f in fields:
        ha = f["size_ha"] or 0; crop = f["crop"]
        ex = Q("SELECT category, quantity, unit, unit_cost_rwf, total_rwf FROM expenses WHERE field_id=? AND category IN ('seed','fertilizer') AND substr(spent_on,1,4)=?", (f["id"], str(year)))
        res = {}
        for cat in ("seed", "fertilizer"):
            rows = [e for e in ex if e["category"] == cat]; kgs = [_kg(e["quantity"], e["unit"]) for e in rows]
            used = sum(k for k in kgs if k is not None) if any(k is not None for k in kgs) else None
            spent = sum(e["total_rwf"] or 0 for e in rows)
            if cat == "seed": rec_ha = SEED.get(crop); src = "general"
            else:
                fr = Q("SELECT kg_per_ha, approval, fertilizer_type FROM fertilizer_subsidies WHERE crop=?", (crop,))
                rec_ha = sum(r["kg_per_ha"] or 0 for r in fr) or None; src = "approved" if fr and all(r["approval"] == "approved" for r in fr) else "reference"
            rec = rec_ha * ha if rec_ha else None
            v = _verdict(used, rec) if used is not None and rec else "none"
            unit_cost = (spent / used) if used and spent else None
            diff = (used - rec) if (used is not None and rec) else None
            res[cat] = dict(used=used, rec=rec, rec_ha=rec_ha, spent=spent, verdict=v, diff=diff, src=src, waste=(diff * unit_cost if v == "high" and unit_cost else None), has_rows=bool(rows))
        out.append(dict(f=f, seed=res["seed"], fert=res["fertilizer"], variety=VAR.get(crop), parts=Q("SELECT fertilizer_type, kg_per_ha FROM fertilizer_subsidies WHERE crop=? ORDER BY id", (crop,))))
    return out


def advice(kind, r):
    """One sentence per input in the user's language."""
    nm = P("seed", "imbuto", "semences") if kind == "seed" else P("fertilizer", "ifumbire", "engrais")
    if r["verdict"] == "none":
        if r["rec"]:
            return P(f"Apply about {r['rec']:.0f} kg of {nm} on this field. Record what you buy so KIZA can check it.", f"Shyiramo hafi kg {r['rec']:.0f} z'{nm} muri uyu murima. Andika ibyo uguze KIZA ibigenzure.", f"Appliquez environ {r['rec']:.0f} kg. Notez vos achats.")
        return P("No reference rate for this crop yet. Ask your sector agronomist.", "Nta ngano yemejwe y'iki gihingwa ihari. Baza umukozi w'ubuhinzi w'umurenge.", "Pas de dose de référence. Demandez à l'agronome.")
    if r["verdict"] == "ok":
        return P(f"Good: you used {r['used']:.0f} kg, the field needs about {r['rec']:.0f} kg.", f"Wabikoze neza: wakoresheje kg {r['used']:.0f}, umurima ukeneye hafi kg {r['rec']:.0f}.", f"Bien: {r['used']:.0f} kg utilisés, {r['rec']:.0f} kg recommandés.")
    if r["verdict"] == "high":
        w = f" (≈ {r['waste']:,.0f} RWF" + P(" wasted)", " yapfuye)", " perdus)") if r["waste"] else ""
        return P(f"Too much: you used {r['used']:.0f} kg but about {r['rec']:.0f} kg is enough{w}. Next season use {r['rec']:.0f} kg.", f"Wakoresheje byinshi: kg {r['used']:.0f} kandi hakwiye hafi kg {r['rec']:.0f}{w}. Igihembwe gitaha koresha kg {r['rec']:.0f}.", f"Trop: {r['used']:.0f} kg, {r['rec']:.0f} kg suffisent{w}.")
    return P(f"Too little: you used {r['used']:.0f} kg but about {r['rec']:.0f} kg is needed. Add about {-r['diff']:.0f} kg more to protect your yield.", f"Wakoresheje bike: kg {r['used']:.0f} kandi hakenewe hafi kg {r['rec']:.0f}. Ongeraho hafi kg {-r['diff']:.0f} kurinda umusaruro.", f"Trop peu: {r['used']:.0f} kg, {r['rec']:.0f} kg nécessaires; ajoutez {-r['diff']:.0f} kg.")


@bp.get("/inputs")
@need("farmer")
def inputs_page():
    rows = analyse(g.user)
    for r in rows:
        r["seed_adv"] = advice("seed", r["seed"]); r["fert_adv"] = advice("fert", r["fert"])
    return render_template("v11/inputs.html", rows=rows, year=dt.date.today().year, tol=TOL)
