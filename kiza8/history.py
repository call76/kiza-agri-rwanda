"""v11 history: (1) Rwanda's agriculture story - only figures found in the cited public sources; (2) "My farm story" - a timeline built from the farmer's own records.
Nothing is invented: a farmer with no records sees an invitation, not a fake story."""
import datetime as dt
from flask import Blueprint, render_template, session
from .core import Q, Q1, need

bp = Blueprint("history", __name__)
TC = "https://www.trade.gov/country-commercial-guides/rwanda-agriculture-sector"
NT = "https://www.newtimes.co.rw/article/147606/News/rwandas-agric-transformation-journey-from-2007-to-2017/amp"

# (year, icon, en, rw, source key). Figures are quoted from the sources above.
RW = [
    ("2004", "📜", "National Agricultural Policy and reforms start Rwanda's agricultural turnaround.", "Politiki y'igihugu y'ubuhinzi n'amavugurura bitangiza impinduka mu buhinzi.", NT),
    ("2006", "🐄", "Girinka (One Cow per Poor Family) is launched. By end-Feb 2013, 144,385 cows had been distributed; milk output rose 221% to 503 million litres in 2012.", "Girinka itangira. Kugeza mu mpera za Gashyantare 2013, inka 144,385 zari zatanzwe; umukamo wiyongereyeho 221% ugera kuri litiro miliyoni 503 muri 2012.", NT),
    ("2007", "🤝", "CAADP compact signed. The sector grew about 5.4% a year from 2007 to 2012, mainly from higher yields.", "Hasinywe amasezerano ya CAADP. Ubuhinzi bwazamutse hafi 5.4% ku mwaka kuva 2007 kugeza 2012, ahanini biturutse ku musaruro wiyongereye.", NT),
    ("2005–2012", "📉", "Rural poverty fell from 61.9% to 48.7% (2005/06 to 2011/12); extreme rural poverty from 39.5% to 26.4%.", "Ubukene mu cyaro bwavuye kuri 61.9% bugera kuri 48.7% (2005/06 - 2011/12); ubukene bukabije bwavuye kuri 39.5% bugera kuri 26.4%.", NT),
    ("2012", "☂️", "A weather-based insurance scheme is set up for farmers hit by weather-related crop losses.", "Hashyirwaho ubwishingizi bushingiye ku kirere ku bahinzi bahuye n'igihombo giturutse ku kirere.", NT),
    ("2024–2029", "🎯", "PSTA5 plan: modernise crops and livestock, boost exports and post-harvest handling; targets sector growth above 6% a year and farm exports above USD 1.5 billion within the decade.", "Gahunda PSTA5: kuvugurura ibihingwa n'amatungo, kongera ibyoherezwa hanze no kwita ku musaruro nyuma yo gusarura; intego ni ukuzamuka kurenga 6% ku mwaka n'ibyoherezwa birenga miliyari 1.5 z'amadolari.", TC),
    ("2025", "👩🏾‍🌾", "Agriculture still employs 43.7% of Rwanda's workforce (Q1 2025, NISR Labour Force Survey) and accounts for about 25-27% of GDP.", "Ubuhinzi buracyaha akazi 43.7% by'abakozi b'u Rwanda (igihembwe 1 cya 2025, NISR) kandi bugize hafi 25-27% bya GDP.", TC),
    ("2050", "🚀", "Vision 2050 and NST2 aim to move from subsistence to commercial, mechanised, technology-driven farming and agro-processing. KIZA-AGRI is built for that shift.", "Icyerekezo 2050 na NST2 bigamije kuva ku buhinzi bwo kwirwanaho bukajya ku buhinzi bw'ubucuruzi, bukoresha ikoranabuhanga n'imashini. KIZA-AGRI yubakiwe iyo ntego.", TC),
]
SRC = [("US Commercial Service: Rwanda agriculture sector", TC), ("The New Times: Rwanda's agric transformation journey 2007-2017", NT)]


def _lg():
    return session.get("lang", "en") if session.get("lang") in ("rw", "fr", "en") else "en"


def story(u):
    """Chronological events from the farmer's own rows."""
    uid = u["id"]; ev = []
    for f in Q("SELECT created_at, name, size_ha, district FROM farms WHERE user_id=?", (uid,)):
        ev.append((f["created_at"][:10], "🏡", "farm", f["name"], f"{f['size_ha']:g} ha · {f['district']}"))
    for f in Q("SELECT f.name, f.crop, f.status, f.planting_date, f.expected_harvest, f.created_at FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=?", (uid,)):
        if f["planting_date"]: ev.append((f["planting_date"], "🌱", "plant", f"{f['crop'] or '-'} · {f['name']}", f["status"]))
        if f["status"] == "Harvested" and f["expected_harvest"]: ev.append((f["expected_harvest"], "🌾", "harvest", f"{f['crop'] or '-'} · {f['name']}", ""))
    for s in Q("SELECT applied_on, product, planned FROM spray_log WHERE user_id=? AND planned=0", (uid,)):
        ev.append((s["applied_on"], "🧴", "spray", s["product"], ""))
    for l in Q("SELECT created_at, crop, qty_kg, price_kg FROM listings WHERE seller_id=?", (uid,)):
        ev.append((l["created_at"][:10], "🛒", "list", f"{l['crop']} · {l['qty_kg']:g} kg", f"{l['price_kg']:g} RWF/kg"))
    for o in Q("SELECT o.created_at, o.qty_kg, o.price_kg, l.crop FROM offers o JOIN listings l ON l.id=o.listing_id WHERE l.seller_id=? AND o.status IN ('Accepted','Completed','Paid')", (uid,)):
        ev.append((o["created_at"][:10], "🤝", "sale", f"{o['crop']} · {o['qty_kg']:g} kg", f"{o['price_kg']:g} RWF/kg"))
    from .care import badge_state
    names = {b["code"]: (b["icon"], b["title"]) for b in badge_state(u)}
    for b in Q("SELECT earned_at, code FROM badges WHERE user_id=?", (uid,)):
        if b["code"] in names: ev.append((b["earned_at"][:10], names[b["code"]][0], "badge", names[b["code"]][1], ""))
    ev.sort(key=lambda e: e[0], reverse=True)
    return ev


@bp.get("/history")
@need("farmer", "buyer", "extension", "government", "admin")
def history_page():
    from flask import g
    u = g.user; ev = story(u) if u["role"] == "farmer" else []
    kinds = {k: sum(1 for e in ev if e[2] == k) for k in ("farm", "plant", "harvest", "spray", "list", "sale", "badge")}
    since = ev[-1][0] if ev else None
    days = (dt.date.today() - dt.date.fromisoformat(since)).days if since else 0
    return render_template("v11/history.html", rw=RW, src=SRC, ev=ev, kinds=kinds, days=days, since=since, lg=_lg())
