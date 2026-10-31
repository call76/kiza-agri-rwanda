"""USSD menu engine for KIZA-AGRI (Kinyarwanda / English). Works with any gateway that POSTs  sessionId, phoneNumber, text  (Africa's Talking style):
`text` is everything the user typed so far joined by '*', and the reply starts with CON (keep the session open) or END (close it).
Stateless: the whole position in the menu is rebuilt from `text`, so no session table is needed. Navigation: 0 = back, 00 = main menu, 9 (main menu) = switch language.
Replies are pure ASCII and at most 182 characters (a safe USSD screen), data comes from the same tables as the web app (E-Soko prices, weather, soil, crop advisor).
Real USSD also needs a short code from a mobile operator and a gateway account - see README."""
import re, datetime as dt
import rules

MAXLEN = 182
PROV = (("Kigali", "Kigali"), ("Northern", "Amajyaruguru"), ("Southern", "Amajyepfo"), ("Eastern", "Iburasirazuba"), ("Western", "Iburengerazuba"))
KINDS = (("Glut / no buyers", "Nta baguzi"), ("Price manipulation by middlemen", "Abamamyi bahindura igiciro"), ("Spoilage / storage problem", "Umusaruro urangirika"), ("Other", "Ikindi"))
TREND = {"rising": ("rising", "izamuka"), "falling": ("falling", "iramanuka"), "stable": ("stable", "ihamye")}
ASCII = {"\u00b7": "/", "\u00b0": "", "\u2013": "-", "\u2014": "-", "\u2019": "'", "\u2018": "'", "\u2026": "...", "\u00a0": " "}

class _Bad(Exception): pass

def _t(lang, en, rw): return rw if lang == "rw" else en

def _fit(s):
    """ASCII-only and <= MAXLEN: drop non-GSM characters, then cut at the last whole line / word."""
    for k, v in ASCII.items(): s = s.replace(k, v)
    s = s.encode("ascii", "ignore").decode()
    if len(s) <= MAXLEN: return s
    cut = s[:MAXLEN]; k = cut.rfind("\n")
    if k > 25: return cut[:k].rstrip()
    k = cut.rfind(" "); return (cut[:k] if k > 25 else cut).rstrip()

def _parts(prefix, parts):
    """prefix + as many whole sentences as fit in MAXLEN (so a long soil note drops its last sentence instead of being cut mid-word)."""
    out = prefix
    for p in parts:
        if len(out) + len(p) + 1 <= MAXLEN: out += (" " if out != prefix else "") + p
    return out

def _user(c, phone):
    return c.execute("SELECT * FROM users WHERE phone=? AND status='active' AND email NOT LIKE '%@guest.kiza'", (phone,)).fetchone() if phone else None

def _menu(lang, user):
    who = (user["name"].split()[0][:12] + ", ") if user else ""
    return "CON " + _t(lang, f"KIZA-AGRI {who}\n1 Prices\n2 Weather\n3 Soil & fertilizer\n4 What to plant\n5 Report a problem\n9 Kinyarwanda", f"KIZA-AGRI {who}\n1 Ibiciro\n2 Ikirere\n3 Ubutaka n'ifumbire\n4 Igihingwa cyo guhinga\n5 Menyesha ikibazo\n9 English")

def _pick(tok, n):
    """tok '1'..'n' -> zero-based index, else _Bad."""
    if not re.fullmatch(r"[1-9]", tok or "") or int(tok) > n: raise _Bad
    return int(tok) - 1

def handle(text, phone, c, write=False):
    """One USSD request -> reply string ('CON ...' / 'END ...'). c = sqlite3 connection (row_factory=Row). write=True lets the report flow save to the database
    (only enable it for gateway-authenticated requests: the phone number is the identity)."""
    user = _user(c, phone); lang = user["lang"] if user and user["lang"] in ("rw", "en") else "rw"; st = []
    for tok in (text or "").split("*"):
        tok = tok.strip()
        if not tok: continue
        if not st and tok == "9": lang = "en" if lang == "rw" else "rw"
        elif tok == "00": st = []
        elif tok == "0": st and st.pop()
        else: st.append(tok)
    try: return _fit(_flow(st, lang, user, c, write))
    except _Bad: return "END " + _t(lang, "Invalid choice. Please dial again.", "Ntibyemewe. Ongera ukande nimero.")

def _flow(st, lang, user, c, write):
    if not st: return _menu(lang, user)
    a, rest = _pick(st[0], 5) + 1, st[1:]
    if a == 5: return _report(rest, lang, user, c, write)
    d, rest, ask = _district(rest, lang, user, c)
    if ask: return ask
    return (None, _prices, _weather, _soil, _croptip)[a](d, rest, lang, c)

def _district(rest, lang, user, c):
    """Known phone -> its district. Otherwise ask province then district (5 + <=8 options fit a screen)."""
    if user and user["district"] and c.execute("SELECT 1 FROM districts WHERE name=?", (user["district"],)).fetchone(): return user["district"], rest, None
    if not rest: return None, rest, "CON " + _t(lang, "Choose province:\n", "Hitamo intara:\n") + "\n".join(f"{i} {p[1] if lang == 'rw' else p[0]}" for i, p in enumerate(PROV, 1)) + "\n0 " + _t(lang, "Back", "Inyuma")
    prov = PROV[_pick(rest[0], len(PROV))][0]; ds = [r[0] for r in c.execute("SELECT name FROM districts WHERE province=? ORDER BY name", (prov,))]
    if len(rest) < 2: return None, rest, "CON " + _t(lang, "Choose district:\n", "Hitamo akarere:\n") + "\n".join(f"{i} {n}" for i, n in enumerate(ds, 1)) + "\n0 " + _t(lang, "Back", "Inyuma")
    return ds[_pick(rest[1], len(ds))], rest[2:], None

def _prices(d, rest, lang, c):
    rows = c.execute("SELECT * FROM esoko_prices WHERE district=? ORDER BY crop LIMIT 8", (d,)).fetchall()
    if not rows: return "END " + _t(lang, f"No price data for {d} yet.", f"Nta makuru y'ibiciro i {d} aracyaboneka.")
    if not rest: return "CON " + _t(lang, f"Prices in {d}:\n", f"Ibiciro i {d}:\n") + "\n".join(f"{i} {r['crop']}" for i, r in enumerate(rows, 1)) + "\n0 " + _t(lang, "Back", "Inyuma")
    r = rows[_pick(rest[0], len(rows))]; tr = TREND.get(r["predicted_trend"], ("", ""))
    return _parts("END ", [f"{r['crop']} {_t(lang, 'in', 'i')} {d}: {r['current_price_rwf']:.0f} RWF/kg", (f"({_t(lang, tr[0], tr[1])} {r['change_pct']:+.1f}%)" if tr[0] else ""), f"[{r['as_of']}]"])

def _wx(d, c): return c.execute("SELECT * FROM weather WHERE district=? ORDER BY day LIMIT 3", (d,)).fetchall()

def _rain_tip(lang, p):
    if p >= 70: return _t(lang, "Heavy rain: do not spray or spread fertilizer today.", "Imvura nyinshi: ntutere umuti cyangwa ifumbire uyu munsi.")
    if p >= 40: return _t(lang, "Rain possible: avoid spraying in the afternoon.", "Imvura ishobora kugwa: irinde gutera umuti nyuma ya saa sita.")
    return _t(lang, "No heavy rain: good day for field work.", "Nta mvura nyinshi: ni umunsi mwiza w'imirimo yo mu murima.")

def _weather(d, rest, lang, c):
    wx = _wx(d, c)
    if not wx: return "END " + _t(lang, f"No weather data for {d} yet.", f"Nta makuru y'ikirere i {d} aracyaboneka.")
    w0 = wx[0]; w1 = wx[1] if len(wx) > 1 else None
    return _parts("END ", [f"{d}: {_t(lang, 'today', 'uyu munsi')} {w0['temp']:.0f}C, {_t(lang, 'rain', 'imvura')} {w0['rain_prob']}%." + (f" {_t(lang, 'Tomorrow', 'Ejo')} {w1['rain_prob']}%." if w1 else ""), _rain_tip(lang, max(w0["rain_prob"], w1["rain_prob"] if w1 else 0))])

def _soil(d, rest, lang, c):
    p = c.execute("SELECT * FROM soil_profiles WHERE district=?", (d,)).fetchone()
    if not p: return "END " + _t(lang, f"No soil data for {d} yet.", f"Nta makuru y'ubutaka i {d} aracyaboneka.")
    wx = _wx(d, c); rainy = any((w["rain_prob"] or 0) >= 70 or (w["rain_mm"] or 0) >= 8 for w in wx[:2])
    ph = f"pH {p['ph_level']}" if p["ph_level"] is not None else ""
    return _parts("END ", [f"{d}: {_t(lang, 'soil', 'ubutaka')} {p['soil_type'] or '-'}, {ph}.", (_t(lang, "Heavy rain soon: do not spread fertilizer today.", "Imvura nyinshi iraza: ntushyiremo ifumbire uyu munsi.") if rainy else ""),
                         (_t(lang, "Likely needs", "Bukeneye") + f": {p['main_nutrient_deficit']}.") if p["main_nutrient_deficit"] else "", (_t(lang, "Suggested", "Ifumbire") + f": {p['recommended_fertilizer']}.") if p["recommended_fertilizer"] else ""])

def _croptip(d, rest, lang, c):
    crops = c.execute("SELECT * FROM crops").fetchall()
    if not crops: return "END " + _t(lang, "Crop data is not loaded yet.", "Amakuru y'ibihingwa ntarashyirwaho.")
    wx = _wx(d, c); p = c.execute("SELECT ph_level FROM soil_profiles WHERE district=?", (d,)).fetchone()
    top = rules.advise(crops, {"size_ha": 1, "soil_ph": p["ph_level"] if p else None, "irrigation": 0}, wx[0] if wx else None, {})[:3]
    return _parts("END ", [_t(lang, f"Best crops now in {d}:", f"Ibihingwa byiza ubu i {d}:"), " ".join(f"{i}.{x['crop']}({x['score']})" for i, x in enumerate(top, 1)), _t(lang, "See the app for reasons.", "Reba porogaramu ku mpamvu.")])

def _report(rest, lang, user, c, write):
    """Distress report for a registered farmer: kind -> crop -> kg -> confirm. Saves only when write=True (authenticated gateway)."""
    if not user or user["role"] != "farmer": return "END " + _t(lang, "Register as a farmer on KIZA-AGRI first to report a problem.", "Banza wiyandikishe nk'umuhinzi kuri KIZA-AGRI kugira ngo utange raporo.")
    if not rest: return "CON " + _t(lang, "Problem:\n", "Ikibazo:\n") + "\n".join(f"{i} {k[0] if lang == 'en' else k[1]}" for i, k in enumerate(KINDS, 1)) + "\n0 " + _t(lang, "Back", "Inyuma")
    kind = KINDS[_pick(rest[0], len(KINDS))][0]
    mine = [r[0] for r in c.execute("SELECT DISTINCT f.crop FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=? AND f.crop IS NOT NULL ORDER BY f.crop LIMIT 5", (user["id"],))]
    crops = mine or [r[0] for r in c.execute("SELECT name FROM crops WHERE name IN ('Maize','Beans','Potato','Cassava','Rice','Tomato') ORDER BY name")]
    if not crops: raise _Bad
    if len(rest) < 2: return "CON " + _t(lang, "Crop:\n", "Igihingwa:\n") + "\n".join(f"{i} {n}" for i, n in enumerate(crops, 1)) + "\n0 " + _t(lang, "Back", "Inyuma")
    crop = crops[_pick(rest[1], len(crops))]
    if len(rest) < 3: return "CON " + _t(lang, "How many kg? (number)", "Ibiro bingahe? (andika umubare)")
    if not re.fullmatch(r"\d{1,8}", rest[2]) or int(rest[2]) < 1: raise _Bad
    kg = int(rest[2])
    if len(rest) < 4: return "CON " + _t(lang, f"Send report?\n{kind}, {crop}, {kg}kg\n1 Yes\n2 No", f"Ohereza raporo?\n{crop}, {kg}kg\n1 Yego\n2 Oya")
    if _pick(rest[3], 2) == 1: return "END " + _t(lang, "Cancelled.", "Byahagaritswe.")
    if not write: return "END " + _t(lang, "Reports by USSD are switched off on this server (gateway not set up).", "Raporo ukoresheje USSD ntizemewe kuri iyi seriveri (gateway ntiyashyizweho).")
    since = (dt.datetime.now() - dt.timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    if not c.execute("SELECT 1 FROM distress_reports WHERE farmer_id=? AND kind=? AND crop=? AND qty_kg=? AND created_at>=?", (user["id"], kind, crop, kg, since)).fetchone():   # gateways retry: do not double-save
        c.execute("INSERT INTO distress_reports(farmer_id,district,crop,kind,qty_kg,details) VALUES(?,?,?,?,?,?)", (user["id"], user["district"], crop, kind, kg, "Sent by USSD"))
        for s in c.execute("SELECT id FROM users WHERE role IN ('extension','government','admin')").fetchall():
            c.execute("INSERT INTO notifications(user_id,kind,message,link) VALUES(?,?,?,?)", (s["id"], "distress", f"New distress report (USSD): {kind} - {crop} in {user['district']}.", "/distress/inbox"))
        c.execute("INSERT INTO audit_logs(user_id,action,detail,ip) VALUES(?,?,?,?)", (user["id"], "distress.create", "ussd", "ussd")); c.commit()
    return "END " + _t(lang, "Report sent to the government team. Thank you.", "Raporo yoherejwe. Murakoze.")
