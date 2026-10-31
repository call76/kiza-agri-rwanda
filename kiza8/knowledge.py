"""KIZA-AGRI v10 - REAL, SOURCED reference facts (no demo numbers).
Every block carries its source + date so the UI can show it. Facts here were collected from public
reporting on 9 Oct 2026; they change, so the admin should review them each season (edit this file or
override with an uploaded table). Anything not sourced is marked 'general guidance'."""
import datetime as dt

# ---- Seasons (NISR Seasonal Agricultural Survey definitions; RAB / Meteo Rwanda naming) ----
SEASONS = [
    dict(code="A", rw="Umuhindo", months=(9, 2), en="Season A (short rains) - Sep to Feb. Main crops: maize, beans, soybean, wheat, rice.",
         rwd="Igihembwe A (Umuhindo) - Nzeri kugeza Gashyantare. Ibihingwa: ibigori, ibishyimbo, soya, ingano, umuceri.",
         frd="Saison A (petites pluies) - sept. à fév. Maïs, haricot, soja, blé, riz."),
    dict(code="B", rw="Itumba", months=(3, 6), en="Season B (long rains) - Mar to Jun. Beans, maize, potato, cassava.",
         rwd="Igihembwe B (Itumba) - Werurwe kugeza Kamena. Ibishyimbo, ibigori, ibirayi, imyumbati.",
         frd="Saison B (grandes pluies) - mars à juin. Haricot, maïs, pomme de terre, manioc."),
    dict(code="C", rw="Impeshyi", months=(7, 9), en="Season C (dry season) - Jul to Sep, marshland and irrigated land only.",
         rwd="Igihembwe C (Impeshyi) - Nyakanga kugeza Nzeri, mu bishanga no ku butaka bwuhirwa gusa.",
         frd="Saison C (saison sèche) - juil. à sept., marais et terres irriguées seulement."),
]
SEASON_SRC = ("NISR Seasonal Agricultural Survey; New Times 11 Aug 2025 (RAB: bimodal rainfall, seasons A, B and C in marshland/irrigated zones)",
              "https://www.newtimes.co.rw/")

def current_season(today=None):
    """Return (main_season_dict, label). Rwanda's agricultural year label follows the NEXT calendar year for A: Sep-Dec 2026 = 2027A."""
    t = today or dt.date.today(); m = t.month
    if m >= 9: s, y = SEASONS[0], t.year + 1
    elif m <= 2: s, y = SEASONS[0], t.year
    elif m <= 6: s, y = SEASONS[1], t.year
    else: s, y = SEASONS[2], t.year
    if m in (7, 8): s = SEASONS[2]   # dry months: season C (marshland) only, upland is land preparation for A
    return s, f"{y}{s['code']}"

# ---- Nkunganire subsidy: announced 2 Jul 2026 for the 2027A season (MINAGRI, via New Times / KT Press) ----
SUBSIDY = dict(
    announced="2026-07-02", season="2027A",
    rows=[  # product, retail RWF/kg, government pays RWF/kg, subsidy %  (None = not published in the sources I found)
        dict(name="Urea", retail=1980, govt=890, pct=45),
        dict(name="NPK 17-17-17 (Tweze)", retail=1861, govt=807, pct=43),
        dict(name="DAP", retail=None, govt=None, pct=46),
    ],
    other_blends_pct=(18, 46), farmer_range_rwf=(755, 1215),
    plan_tonnes=60000, local_tonnes=25000, farmers=2_000_000,
    register=dict(
        en="Register the quantity you need in the Smart Nkunganire System (dial *774) using your national ID and land parcel (UPI) number, then collect from your agro-dealer.",
        rw="Andikisha ingano y'ifumbire ukeneye muri Smart Nkunganire (kanda *774) ukoresheje indangamuntu n'inomero y'ubutaka (UPI), hanyuma uyifatire ku mucuruzi w'ifumbire.",
        fr="Enregistrez la quantité voulue dans Smart Nkunganire (composez *774) avec votre carte d'identité et le numéro de parcelle (UPI), puis retirez chez l'agro-dealer."),
    sources=[("New Times - Govt increases fertiliser subsidies amid global price shocks (3 Jul 2026)", "https://allafrica.com/stories/202607030438.html"),
             ("New Times - How Rwanda's fertiliser subsidy scheme works", "https://www.newtimes.co.rw/article/37366/news/agriculture/how-rwandas-fertiliser-subsidy-scheme-works"),
             ("KT Press - Rwanda nearly doubles fertilizer subsidy (11 Jun 2026)", "https://www.ktpress.rw/2026/06/rwanda-nearly-doubles-fertilizer-subsidy-amid-global-supply-fears/")],
)
for _r in SUBSIDY["rows"]:
    _r["farmer"] = (_r["retail"] - _r["govt"]) if _r["retail"] else None
APPLICATION_NOTE = dict(  # PM statement in Parliament, reported by New Times
    kg_ha_2024=73, kg_ha_2026=80, kg_ha_target_2029=94.6)

# ---- Meteo Rwanda seasonal outlook, issued 21 Aug 2026 (reported by Umunota) ----
OUTLOOK = dict(
    period="Sep-Dec 2026 (Umuhindo)", mm=(300, 1000), south_east_kigali_mm=(300, 450),
    en="Meteo Rwanda expects ABOVE-average rain (300-1,000 mm) for Sep-Dec 2026. September is relatively dry; the heaviest rain comes later in the season. Southern, Eastern and Kigali get less (300-450 mm).",
    rw="Meteo Rwanda iteganya imvura ISHOBORA KURENGA isanzwe (mm 300-1,000) mu Nzeri-Ukuboza 2026. Nzeri izaba ifite imvura nke; imvura nyinshi izaba mu mpera z'igihembwe. Amajyepfo, Iburasirazuba na Kigali bizagira nke (mm 300-450).",
    fr="Meteo Rwanda prévoit des pluies SUPÉRIEURES à la normale (300-1 000 mm) pour sept.-déc. 2026. Septembre est assez sec; les plus fortes pluies viennent plus tard. Sud, Est et Kigali: 300-450 mm.",
    source=("Umunota / Meteo Rwanda, 21 Aug 2026", "https://umunota.com/?p=84756"),
)

# ---- General agronomy (GENERAL GUIDANCE, not RAB-certified numbers; confirm with your sector agronomist) ----
TIPS = {
    "Potato": ("Use clean/certified seed tubers; earth-up at 3-4 weeks. In wet weather watch for late blight (dark patches on leaves, white mould underneath) and ask your agronomist about spraying.",
               "Koresha imbuto isukuye/yemewe; ushyire ubutaka ku mutumba nyuma y'ibyumweru 3-4. Mu mvura nyinshi reba indwara y'ibibabi (ibibara by'umukara); baza umukozi w'ubuhinzi ku miti.",
               "Semences saines/certifiées; buttage à 3-4 semaines. Par temps humide surveillez le mildiou."),
    "Maize": ("Plant with the first reliable rains, in rows. Top-dress with urea when plants are about knee-high, and not just before heavy rain. Watch for fall armyworm in the funnel.",
              "Hinga imvura ya mbere yizewe, mu mirongo. Ongeramo urea igihingwa kigeze ku ivi, ntibikorwe imvura nyinshi igiye kugwa. Reba inyo y'ibigori (fall armyworm).",
              "Semez avec les premières pluies fiables, en lignes. Urée en couverture au stade genou; surveillez la chenille légionnaire."),
    "Beans": ("Use improved varieties, space plants properly, weed early. Waterlogging causes root rot, so drain heavy soils.",
              "Koresha imbuto zitoranyijwe, ushyire intera ikwiye, ukore isarura ry'ibyatsi hakiri kare. Amazi menshi atera kubora imizi: tunganya amazi.",
              "Variétés améliorées, bon écartement, sarclage précoce. L'excès d'eau pourrit les racines: drainez."),
    "Cassava": ("Use disease-free cuttings; mosaic and brown streak spread through infected cuttings, so never replant from sick plants.",
                "Koresha imishito itarwaye; indwara ya mosaic na brown streak ikwirakwizwa n'imishito irwaye: ntuyihinge.",
                "Boutures saines; la mosaïque et la striure brune se transmettent par boutures infectées."),
    "Rice": ("Level fields, transplant healthy seedlings and keep a steady water layer; avoid applying fertilizer into flowing water.",
             "Tunganya umurima, utere uduti dufite ubuzima, ugumane amazi angana; wirinde gushyira ifumbire mu mazi atemba.",
             "Planches nivelées, repiquage de plants sains, lame d'eau stable; pas d'engrais dans l'eau courante."),
    "Tomato": ("Stake plants, mulch, and water at the base. Rain splashes spread blight, so use drip or furrow irrigation and rotate crops.",
               "Shyiraho inkingi, upfundikire ubutaka, kandi uvomerere ku gishyitsi. Imvura ikwirakwiza indwara: koresha uburyo bwo kuhira buto kandi uhinduranye ibihingwa.",
               "Tuteurez, paillez, arrosez au pied; rotation des cultures pour limiter le mildiou."),
}
GENERAL = ("General rules: test or estimate soil pH before liming; never spread fertilizer just before heavy rain; rotate cereals with legumes; "
           "store grain dry (below ~13% moisture) to avoid aflatoxin; for pesticides always follow the label and ask your sector agronomist.")

def facts_text(lang="en", today=None):
    """Compact fact sheet injected into the AI system prompt."""
    s, label = current_season(today); sub = SUBSIDY
    lines = [f"TODAY: {(today or dt.date.today()).isoformat()}. Current agricultural season: {label} ({s['en']})."]
    lines.append("NKUNGANIRE SUBSIDY (announced 2 Jul 2026, for 2027A): " + "; ".join(
        f"{r['name']}: retail {r['retail']} RWF/kg, government pays {r['govt']}, farmer pays {r['farmer']} ({r['pct']}%)" if r["retail"] else f"{r['name']}: {r['pct']}% subsidy (price not found)" for r in sub["rows"]) +
        f". Other blends {sub['other_blends_pct'][0]}-{sub['other_blends_pct'][1]}% subsidy; farmers pay {sub['farmer_range_rwf'][0]}-{sub['farmer_range_rwf'][1]} RWF/kg depending on product. "
        f"Plan: ~{sub['plan_tonnes']:,} t, of which {sub['local_tonnes']:,} t made locally. " + sub["register"]["en"])
    lines.append("RAINFALL OUTLOOK: " + OUTLOOK["en"] + " (" + OUTLOOK["source"][0] + ")")
    lines.append("FERTILIZER USE: national average rose from 73 kg/ha (2024) to 80 kg/ha (2026), target 94.6 kg/ha by 2029.")
    lines.append(GENERAL)
    return "\n".join(lines)

def season_label(today=None): return current_season(today)[1]
