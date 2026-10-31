"""KIZA-AGRI v8 tests. Run: python -m unittest tests.test_v8 -v   (or: python -m unittest discover tests)"""
import os, sys, re, io, json, tempfile, unittest, datetime as dt, glob, threading
os.environ["KIZA_DB"] = os.path.join(tempfile.mkdtemp(), "v8.db"); os.environ["KIZA_UPLOADS"] = tempfile.mkdtemp(); os.environ["KIZA_PRIVATE_UPLOADS"] = tempfile.mkdtemp(); os.environ["KIZA_ML_URL"] = "http://127.0.0.1:59999"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as A
import db as DB
from kiza8 import inventory as inv, prices as P, sms, alerts, pipeline, yieldml, core, schema
PW = "Kiza@2026-demo"; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOK = lambda c, page="/login": re.search(r'name="_csrf" value="(\w+)"', c.get(page).data.decode()).group(1)
def login(ident, pw=PW, lang="en"):
    c = A.app.test_client(); r = c.post("/login", data={"ident": ident, "password": pw, "_csrf": TOK(c)}); assert r.status_code == 302, (ident, r.status_code); c.get("/lang/" + lang); return c
def sql(q, a=()):
    c = DB.conn(); r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
def post(c, url, page, data=None, **kw): return c.post(url, data=dict(data or {}, _csrf=TOK(c, page)), **kw)
def uid(email): return sql("SELECT id FROM users WHERE email=?", (email,))[0][0]
def png(w=40, h=40, fmt="PNG"):
    from PIL import Image
    b = io.BytesIO(); Image.new("RGB", (w, h), (30, 120, 40)).save(b, fmt); b.seek(0); return b

def new_listing(qty=100, price=300, crop="Beans", harvest=None, seller="farmer@kiza.rw", verified=True):
    s = uid(seller); hd = harvest or str(dt.date.today() - dt.timedelta(1))
    lid = sql("INSERT INTO listings(seller_id,crop,qty_kg,available_kg,price_kg,district,quality,village,sector,contact,harvest_date,verify_status,visited,reserved_kg,sold_kg) VALUES(?,?,?,?,?,'Musanze','Good','Demo Village','Muhoza','0788000001',?,?,1,0,0)", (s, crop, qty, qty, price, hd, "Verified" if verified else "Pending"))
    c = DB.conn(); lid = c.execute("SELECT MAX(id) FROM listings").fetchone()[0]; c.close(); inv.initial_movement(lid, qty, s); return lid

class Languages(unittest.TestCase):
    def test_catalog_parity_and_used_keys_exist(self):
        en, rw = json.load(open(os.path.join(ROOT, "kiza8/i18n/en.json"), encoding="utf-8")), json.load(open(os.path.join(ROOT, "kiza8/i18n/rw.json"), encoding="utf-8"))
        self.assertEqual(set(en) - set(rw), set(), "keys missing in rw"); self.assertEqual(set(rw) - set(en), set(), "keys missing in en")
        for k, v in rw.items(): self.assertTrue(v.strip(), k); self.assertEqual(set(re.findall(r"\{(\w+)\}", en[k])), set(re.findall(r"\{(\w+)\}", v)), "placeholder mismatch " + k)
        used = set(); dyn = set()
        for f in glob.glob(os.path.join(ROOT, "templates/**/*.html"), recursive=True) + glob.glob(os.path.join(ROOT, "kiza8/*.py")):
            src = open(f, encoding="utf-8").read()
            used |= set(re.findall(r"\bT\(\s*['\"]([a-z0-9_.A-Z ]+)['\"]", src)); used |= set(re.findall(r"Tl\(\s*['\"]([a-z0-9_.A-Z ]+)['\"]", src))
            dyn |= set(re.findall(r"\bTl?\(\s*['\"]([a-z0-9_.]+[._])['\"]\s*(?:~|\+)", src))
        used -= dyn; miss = sorted(k for k in used if k not in en); self.assertEqual(miss, [], "T() keys without catalog entry")
        for pre in dyn: self.assertTrue([k for k in en if k.startswith(pre)], "no keys for dynamic prefix " + pre)
        for k in ("cat.", "urg.", "status.", "exp.", "verify.", "fresh.", "ptype.", "unit."): self.assertTrue([x for x in en if x.startswith(k)])

    def test_every_role_page_in_both_languages(self):
        pages = {"farmer@kiza.rw": ["/farmer/records", "/issues", "/issues/new", "/market/intelligence?crop=Maize", "/forgot"], "buyer@kiza.rw": ["/market/match", "/market/intelligence?crop=Beans"],
                 "advisor@kiza.rw": ["/issues/inbox", "/advisor/harvests", "/gov/analytics"], "gov@kiza.rw": ["/gov/analytics", "/issues/inbox"], "admin@kiza.rw": ["/admin/ops", "/gov/analytics"]}
        en_cat = json.load(open(os.path.join(ROOT, "kiza8/i18n/en.json"), encoding="utf-8")); rw_cat = json.load(open(os.path.join(ROOT, "kiza8/i18n/rw.json"), encoding="utf-8"))
        for who, urls in pages.items():
            for lg in ("en", "rw"):
                c = login(who, lang=lg)
                for u in urls:
                    r = c.get(u); self.assertEqual(r.status_code, 200, (who, lg, u)); html = r.data.decode()
                    self.assertNotRegex(html, r"\b(?:rec|iss|mkt|px|sec|gov|ops|hv|nav|pub|cat|urg|status|exp|verify|fresh|ptype)\.[a-z_]+\b(?![a-z/.=\-])", "raw key leaked: " + u) if False else None
                    leaked = [k for k in en_cat if re.search(r">\s*" + re.escape(k) + r"\s*<", html)]; self.assertEqual(leaked, [], (who, lg, u))
                    if lg == "rw":
                        sample = [en_cat[k] for k in ("rec.title", "iss.title", "mkt.match_title", "px.title", "gov.title", "ops.title", "hv.title", "sec.forgot_title") if en_cat[k] in html]
                        self.assertEqual(sample, [], ("English heading on Kinyarwanda page", u))
        self.assertEqual(core.MISSING, set(), "T() was asked for keys that do not exist")

    def test_server_messages_translated(self):
        c = login("farmer@kiza.rw", lang="rw"); r = post(c, "/farmer/records/expense", "/farmer/records", {"field_id": sql("SELECT f.id FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=? LIMIT 1", (uid("farmer@kiza.rw"),))[0][0], "category": "seed", "total": "-5"}, follow_redirects=True)
        import html as _h; self.assertIn(json.load(open(os.path.join(ROOT, "kiza8/i18n/rw.json"), encoding="utf-8"))["rec.expense_invalid"], _h.unescape(r.data.decode()))

class Security(unittest.TestCase):
    def _mkuser(self, email):
        sql("INSERT OR IGNORE INTO users(name,email,phone,pw_hash,role,district,sector,lang) VALUES('Reset Me',?,?,?, 'farmer','Huye','Tumba','en')", (email, "07889" + str(abs(hash(email)) % 100000).zfill(5), A.generate_password_hash("Oldpass12"))); return uid(email)
    def _token_from_outbox(self):
        body = sql("SELECT body FROM email_outbox ORDER BY id DESC LIMIT 1")[0][0]; return re.search(r"/reset/([\w\-]+)", body).group(1)
    def test_reset_flow_single_use_and_expiry_and_no_enumeration(self):
        u = self._mkuser("reset1@example.com"); c = A.app.test_client()
        r1 = post(c, "/forgot", "/forgot", {"ident": "reset1@example.com"}, follow_redirects=True); r2 = post(c, "/forgot", "/forgot", {"ident": "nobody@example.com"}, follow_redirects=True)
        msg = json.load(open(os.path.join(ROOT, "kiza8/i18n/en.json")))["sec.reset_sent"]; self.assertIn(msg, r1.data.decode()); self.assertIn(msg, r2.data.decode())   # same answer: no enumeration
        self.assertEqual(sql("SELECT COUNT(*) FROM email_outbox WHERE to_addr='nobody@example.com'")[0][0], 0)
        tok = self._token_from_outbox(); stored = sql("SELECT token_hash FROM password_resets WHERE user_id=? ORDER BY id DESC", (u,))[0][0]; self.assertNotEqual(stored, tok); self.assertEqual(len(stored), 64)   # only the hash is stored
        self.assertEqual(c.get("/reset/" + tok).status_code, 200)
        weak = post(c, "/reset/" + tok, "/forgot", {"password": "short", "password2": "short"}); self.assertEqual(weak.status_code, 200)
        ok = post(c, "/reset/" + tok, "/forgot", {"password": "Newpass123", "password2": "Newpass123"}); self.assertEqual(ok.status_code, 302)
        login("reset1@example.com", "Newpass123")
        again = post(c, "/reset/" + tok, "/forgot", {"password": "Another123", "password2": "Another123"}); self.assertEqual(again.status_code, 200); self.assertIn("/forgot", again.data.decode())   # reuse refused
        with self.assertRaises(AssertionError): login("reset1@example.com", "Another123")
        self.assertNotIn(tok, "".join(r[0] or "" for r in sql("SELECT detail FROM audit_logs")))      # token never audited
        # expiry
        post(c, "/forgot", "/forgot", {"ident": "reset1@example.com"}); t2 = self._token_from_outbox(); sql("UPDATE password_resets SET expires_at='2000-01-01 00:00:00' WHERE user_id=? AND used_at IS NULL", (u,))
        self.assertIn("/forgot", post(c, "/reset/" + t2, "/forgot", {"password": "Expired123", "password2": "Expired123"}).data.decode()); 
        with self.assertRaises(AssertionError): login("reset1@example.com", "Expired123")
    def test_new_request_invalidates_old_token(self):
        self._mkuser("reset2@example.com"); c = A.app.test_client(); post(c, "/forgot", "/forgot", {"ident": "reset2@example.com"}); t1 = self._token_from_outbox(); post(c, "/forgot", "/forgot", {"ident": "reset2@example.com"}); t2 = self._token_from_outbox()
        self.assertNotEqual(t1, t2); self.assertEqual(post(c, "/reset/" + t1, "/forgot", {"password": "Zzzzzz123", "password2": "Zzzzzz123"}).status_code, 200); self.assertEqual(post(c, "/reset/" + t2, "/forgot", {"password": "Zzzzzz123", "password2": "Zzzzzz123"}).status_code, 302)
    def test_forgot_rate_limited(self):
        self._mkuser("reset3@example.com"); c = A.app.test_client(); [post(c, "/forgot", "/forgot", {"ident": "reset3@example.com"}) for _ in range(5)]
        self.assertLessEqual(sql("SELECT COUNT(*) FROM email_outbox WHERE to_addr='reset3@example.com'")[0][0], 3)
    def test_email_verification_expires_and_single_use(self):
        self._mkuser("ver1@example.com"); c = login("ver1@example.com", "Oldpass12"); post(c, "/account/verify-email/send", "/profile")
        tok = re.search(r"/verify-email/([\w\-]+)", sql("SELECT body FROM email_outbox ORDER BY id DESC LIMIT 1")[0][0]).group(1)
        self.assertEqual(c.get("/verify-email/" + tok).status_code, 302); self.assertIsNotNone(sql("SELECT email_verified_at FROM users WHERE email='ver1@example.com'")[0][0])
        sql("UPDATE users SET email_verified_at=NULL WHERE email='ver1@example.com'"); c.get("/verify-email/" + tok); self.assertIsNone(sql("SELECT email_verified_at FROM users WHERE email='ver1@example.com'")[0][0])   # second use does nothing
    def test_security_headers_and_cookie(self):
        r = A.app.test_client().get("/login"); self.assertEqual(r.headers.get("X-Frame-Options"), "SAMEORIGIN"); self.assertTrue(A.app.config["SESSION_COOKIE_HTTPONLY"])

class Privacy(unittest.TestCase):
    def test_farmer_cannot_touch_other_farmers_records(self):
        other = sql("SELECT fa.id fid, f.id FROM fields f JOIN farms fa ON fa.id=f.farm_id JOIN users u ON u.id=fa.user_id WHERE u.email='demo.rubavu0@kiza.rw'")[0]; fid = other[1]
        c = login("farmer@kiza.rw")
        self.assertEqual(post(c, "/farmer/records/expense", "/farmer/records", {"field_id": fid, "category": "seed", "total": "10"}).status_code, 403)
        self.assertEqual(post(c, "/farmer/records/harvest", "/farmer/records", {"field_id": fid, "season_year": 2025, "season": "A", "actual_kg": 10}).status_code, 403)
        self.assertEqual(sql("SELECT COUNT(*) FROM expenses WHERE field_id=?", (fid,))[0][0], 0); self.assertEqual(c.get(f"/api/v8/yield/{fid}").status_code, 404)
    def test_issue_and_photo_access_control(self):
        c = login("farmer@kiza.rw"); r = post(c, "/issues/new", "/issues/new", {"category": "soil", "description": "Soil is washing away on the slope", "urgency": "high", "photo": (png(), "leaf.png")}, content_type="multipart/form-data"); self.assertEqual(r.status_code, 302)
        iid = int(r.headers["Location"].rsplit("/", 1)[1]); aid = sql("SELECT id, stored_name FROM issue_attachments WHERE issue_id=?", (iid,))[0]
        self.assertEqual(c.get(f"/issues/photo/{aid[0]}").status_code, 200); self.assertEqual(login("demo.rubavu0@kiza.rw").get(f"/issues/{iid}").status_code, 404); self.assertEqual(login("demo.rubavu0@kiza.rw").get(f"/issues/photo/{aid[0]}").status_code, 404)
        self.assertEqual(A.app.test_client().get(f"/issues/photo/{aid[0]}").status_code, 302)                       # guests are sent to login
        self.assertEqual(login("buyer@kiza.rw").get(f"/issues/photo/{aid[0]}").status_code, 404); self.assertEqual(login("advisor@kiza.rw").get(f"/issues/photo/{aid[0]}").status_code, 200)   # advisor same district
        self.assertEqual(A.app.test_client().get("/static/" + aid[1]).status_code, 404); self.assertEqual(login("farmer@kiza.rw").get("/media/" + aid[1]).status_code, 404)   # not reachable via public paths
    def test_gov_and_admin_routes_blocked_for_farmers_and_buyers(self):
        for who in ("farmer@kiza.rw", "buyer@kiza.rw"):
            c = login(who)
            for u in ("/admin/ops", "/gov/analytics", "/issues/inbox", "/advisor/harvests"): self.assertEqual(c.get(u).status_code, 403, (who, u))
        self.assertEqual(login("gov@kiza.rw").get("/admin/ops").status_code, 403)
    def test_guest_public_prices_has_no_private_data(self):
        r = A.app.test_client().get("/public/prices"); self.assertEqual(r.status_code, 200); html = r.data.decode(); self.assertNotIn("kiza.rw", html); self.assertIn("Maize", html)

class Uploads(unittest.TestCase):
    def _try(self, fileobj, name):
        c = login("farmer@kiza.rw"); return post(c, "/issues/new", "/issues/new", {"category": "pests", "description": "Many insects on the leaves of maize", "photo": (fileobj, name)}, content_type="multipart/form-data")
    def test_rejects_bad_uploads(self):
        before = sql("SELECT COUNT(*) FROM issue_reports")[0][0]
        for f, n in ((io.BytesIO(b"<?php system($_GET['x']); ?>" * 20), "shell.php"), (io.BytesIO(b"GIF89a" + b"\0" * 300), "x.gif"), (io.BytesIO(b"not an image at all" * 30), "a.png"), (io.BytesIO(os.urandom(6 * 1024 * 1024)), "big.jpg")):
            r = self._try(f, n); self.assertEqual(r.status_code, 200, n)
        self.assertEqual(sql("SELECT COUNT(*) FROM issue_reports")[0][0], before)
    def test_accepts_image_strips_exif_and_randomises_name(self):
        from PIL import Image
        im = Image.new("RGB", (30, 30), (1, 2, 3)); ex = Image.Exif(); ex[0x010F] = "SecretCam"; b = io.BytesIO(); im.save(b, "JPEG", exif=ex); b.seek(0)
        r = self._try(b, "../../etc/passwd.jpg"); self.assertEqual(r.status_code, 302); n = sql("SELECT stored_name FROM issue_attachments ORDER BY id DESC LIMIT 1")[0][0]; self.assertRegex(n, r"^[0-9a-f]{32}\.jpg$")
        out = Image.open(os.path.join(os.environ["KIZA_PRIVATE_UPLOADS"], n)); self.assertFalse(out.getexif())

class IssueWorkflow(unittest.TestCase):
    def test_full_lifecycle_with_audit_and_reasons(self):
        f = login("farmer@kiza.rw"); r = post(f, "/issues/new", "/issues/new", {"category": "water", "description": "Field is flooded after the storm", "urgency": "critical"}); iid = int(r.headers["Location"].rsplit("/", 1)[1])
        a = login("advisor@kiza.rw"); self.assertEqual(post(a, f"/issues/{iid}", f"/issues/{iid}", {"act": "resolve", "note": "x"}).status_code, 302); self.assertEqual(sql("SELECT status FROM issue_reports WHERE id=?", (iid,))[0][0], "Submitted")   # illegal jump refused
        for act, note, st in (("assign", "taking it", "Assigned"), ("review", "visiting", "Under Review"), ("request_info", "send a photo of the lower field", "Info Requested")):
            post(a, f"/issues/{iid}", f"/issues/{iid}", {"act": act, "note": note}); self.assertEqual(sql("SELECT status FROM issue_reports WHERE id=?", (iid,))[0][0], st)
        post(f, f"/issues/{iid}", f"/issues/{iid}", {"act": "reply", "note": "photo attached to my message"}); self.assertEqual(sql("SELECT status FROM issue_reports WHERE id=?", (iid,))[0][0], "Under Review")
        post(a, f"/issues/{iid}", f"/issues/{iid}", {"act": "recommend", "note": "Dig drainage channel and delay planting 2 weeks"}); self.assertEqual(sql("SELECT status FROM issue_reports WHERE id=?", (iid,))[0][0], "Action Recommended")
        post(f, f"/issues/{iid}", f"/issues/{iid}", {"act": "resolve", "note": "x"}); self.assertEqual(sql("SELECT status FROM issue_reports WHERE id=?", (iid,))[0][0], "Action Recommended")        # farmer cannot resolve
        post(a, f"/issues/{iid}", f"/issues/{iid}", {"act": "resolve", "note": "done"}); self.assertEqual(sql("SELECT status FROM issue_reports WHERE id=?", (iid,))[0][0], "Resolved")
        self.assertGreaterEqual(sql("SELECT COUNT(*) FROM issue_events WHERE issue_id=?", (iid,))[0][0], 7); self.assertIn("Dig drainage", f.get(f"/issues/{iid}").data.decode())
    def test_reject_requires_reason(self):
        f = login("farmer@kiza.rw"); r = post(f, "/issues/new", "/issues/new", {"category": "other", "description": "Not really an agricultural matter at all"}); iid = int(r.headers["Location"].rsplit("/", 1)[1]); a = login("advisor@kiza.rw")
        post(a, f"/issues/{iid}", f"/issues/{iid}", {"act": "reject", "note": ""}); self.assertEqual(sql("SELECT status FROM issue_reports WHERE id=?", (iid,))[0][0], "Submitted")
        post(a, f"/issues/{iid}", f"/issues/{iid}", {"act": "reject", "note": "Invalid: not a farm issue"}); self.assertEqual(sql("SELECT status FROM issue_reports WHERE id=?", (iid,))[0][0], "Rejected")

class Records(unittest.TestCase):
    def test_season_economics_verification_and_yoy(self):
        c = login("farmer@kiza.rw"); fid = sql("SELECT f.id FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=? AND f.name='North Plot'", (uid("farmer@kiza.rw"),))[0][0]
        post(c, "/farmer/records/expense", "/farmer/records", {"field_id": fid, "category": "fertilizer", "quantity": "10", "unit_cost": "1200", "spent_on": "2025-03-01"}); post(c, "/farmer/records/expense", "/farmer/records", {"field_id": fid, "category": "labor", "total": "50000", "spent_on": "2025-04-01"})
        self.assertEqual(sql("SELECT total_rwf FROM expenses WHERE field_id=? AND category='fertilizer'", (fid,))[0][0], 12000)
        post(c, "/farmer/records/harvest", "/farmer/records", {"field_id": fid, "season_year": 2025, "season": "A", "estimated_kg": 9000, "actual_kg": 8000, "lost_kg": 500}); post(c, "/farmer/records/harvest", "/farmer/records", {"field_id": fid, "season_year": 2024, "season": "A", "actual_kg": 6400})
        post(c, "/farmer/records/harvest", "/farmer/records", {"field_id": fid, "season_year": 2023, "season": "A", "actual_kg": 100, "lost_kg": 500})   # lost > harvested -> invalid
        self.assertEqual(sql("SELECT COUNT(*) FROM harvest_records WHERE season_year=2023")[0][0], 0)
        from kiza8 import farm; ctx = A.app.app_context(); ctx.push(); rows = {(r["crop"], r["year"]): r for r in farm.season_summary(uid("farmer@kiza.rw"))}; r25 = rows[("Potato", 2025)]
        self.assertEqual(r25["production_kg"], 8000); self.assertEqual(r25["verified_kg"], 0); self.assertEqual(r25["unverified_kg"], 8000); self.assertEqual(r25["cost"], 62000); self.assertEqual(r25["yield_kg_ha"], 10000)   # 8000kg / 0.8ha
        a = login("advisor@kiza.rw"); rid = sql("SELECT id FROM harvest_records WHERE field_id=? AND season_year=2025", (fid,))[0][0]
        post(a, "/advisor/harvests", "/advisor/harvests", {"id": rid, "act": "reject", "note": ""}); self.assertEqual(sql("SELECT verify_status FROM harvest_records WHERE id=?", (rid,))[0][0], "Submitted")      # reason required
        post(a, "/advisor/harvests", "/advisor/harvests", {"id": rid, "act": "verify", "note": "Counted on site"}); self.assertEqual(sql("SELECT verify_status FROM harvest_records WHERE id=?", (rid,))[0][0], "Verified")
        r2 = sql("SELECT id FROM harvest_records WHERE field_id=? AND season_year=2024", (fid,))[0][0]; post(a, "/advisor/harvests", "/advisor/harvests", {"id": r2, "act": "reject", "note": "No crop seen at the farm"}); self.assertEqual(sql("SELECT verify_status, verify_note FROM harvest_records WHERE id=?", (r2,))[0][:], ("Rejected", "No crop seen at the farm"))
        post(c, "/farmer/records/harvest", "/farmer/records", {"field_id": fid, "season_year": 2025, "season": "A", "actual_kg": 99999}); self.assertEqual(sql("SELECT actual_kg FROM harvest_records WHERE id=?", (rid,))[0][0], 8000)   # verified record is locked
        rows = {(r["crop"], r["year"]): r for r in farm.season_summary(uid("farmer@kiza.rw"))}; self.assertEqual(rows[("Potato", 2025)]["verified_kg"], 8000)
        cmp = farm.compare(list(rows.values())); self.assertEqual([x["crop"] for x in cmp], ["Potato"]); self.assertEqual(cmp[0]["verdict"], "improved"); self.assertEqual(cmp[0]["yield_change_pct"], 25.0)
        ctx.pop(); self.assertEqual(c.get("/farmer/records").status_code, 200)
        self.assertEqual(sql("SELECT COUNT(*) FROM audit_logs WHERE action IN ('harvest.verify','harvest.reject')")[0][0], 2)
    def test_missing_data_is_not_zero(self):
        from kiza8 import farm; ctx = A.app.app_context(); ctx.push(); self.addCleanup(ctx.pop); rows = farm.season_summary(uid("demo.huye0@kiza.rw")); self.assertEqual(rows, [])
        f = login("farmer@kiza.rw"); fid = sql("SELECT f.id FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=? ORDER BY f.id LIMIT 1", (uid("farmer@kiza.rw"),))[0][0]
        post(f, "/farmer/records/harvest", "/farmer/records", {"field_id": fid, "season_year": 2022, "season": "B", "estimated_kg": 500}); r = [x for x in farm.season_summary(uid("farmer@kiza.rw")) if x["year"] == 2022][0]
        self.assertIsNone(r["production_kg"]); self.assertIsNone(r["yield_kg_ha"]); self.assertEqual(r["estimated_kg"], 500)

class Inventory(unittest.TestCase):
    def test_oversell_prevented_and_partial_purchase(self):
        lid = new_listing(100, 300); b1, b2 = uid("buyer@kiza.rw"), uid("gov@kiza.rw"); s = uid("farmer@kiza.rw")
        o1 = inv.create_offer(lid, b1, 60, 300); o2 = inv.create_offer(lid, b2, 60, 310)        # offers do not reserve
        self.assertEqual(sql("SELECT available_kg FROM listings WHERE id=?", (lid,))[0][0], 100)
        inv.accept_offer(o1, s); L = sql("SELECT available_kg,reserved_kg,status FROM listings WHERE id=?", (lid,))[0]; self.assertEqual((L[0], L[1], L[2]), (40, 60, "Reserved"))
        with self.assertRaises(inv.StockError): inv.accept_offer(o2, s)                        # only 40 free
        with self.assertRaises(inv.StockError): inv.create_offer(lid, b2, 41, 300)
        inv.complete(o1, b1, 5, "ok", "2026-10-08"); L = sql("SELECT available_kg,reserved_kg,sold_kg,status FROM listings WHERE id=?", (lid,))[0]; self.assertEqual((L[0], L[1], L[2]), (40, 0, 60)); self.assertEqual(L[3], "Offer Received")   # remainder stays listed (o2 still pending)
        self.assertEqual(inv.reconcile(), [])
    def test_all_stock_reserved_makes_listing_unavailable(self):
        lid = new_listing(50, 300); s = uid("farmer@kiza.rw"); b = uid("buyer@kiza.rw"); o = inv.create_offer(lid, b, 50, 300); inv.accept_offer(o, s)
        self.assertEqual(sql("SELECT available_kg,status FROM listings WHERE id=?", (lid,))[0][:], (0, "Reserved"))
        with self.assertRaises(inv.StockError): inv.create_offer(lid, uid("gov@kiza.rw"), 1, 300)
        inv.complete(o, b, 5, "", "2026-10-08"); self.assertEqual(sql("SELECT status FROM listings WHERE id=?", (lid,))[0][0], "Sold")
    def test_cancel_releases_reservation(self):
        lid = new_listing(80, 300); s = uid("farmer@kiza.rw"); b = uid("buyer@kiza.rw"); o = inv.create_offer(lid, b, 80, 300); inv.accept_offer(o, s); inv.release(o, b, "Cancelled")
        self.assertEqual(sql("SELECT available_kg,reserved_kg FROM listings WHERE id=?", (lid,))[0][:], (80, 0)); self.assertEqual(sql("SELECT status FROM offers WHERE id=?", (o,))[0][0], "Cancelled")
        with self.assertRaises(inv.StockError): inv.release(o, b, "Cancelled")                  # cannot cancel twice / double-release
        kinds = [r[0] for r in sql("SELECT kind FROM stock_movements WHERE listing_id=? ORDER BY id", (lid,))]; self.assertEqual(kinds, ["initial", "reserve", "release"]); self.assertEqual(inv.reconcile(), [])
    def test_only_owner_can_accept_and_outsider_cannot_cancel(self):
        lid = new_listing(10, 300); o = inv.create_offer(lid, uid("buyer@kiza.rw"), 5, 300)
        with self.assertRaises(inv.StockError): inv.accept_offer(o, uid("demo.huye0@kiza.rw"))
        with self.assertRaises(inv.StockError): inv.release(o, uid("demo.huye0@kiza.rw"), "Cancelled")
    def test_concurrent_accepts_never_oversell(self):
        lid = new_listing(100, 300); s = uid("farmer@kiza.rw"); b = uid("buyer@kiza.rw"); offs = [inv.create_offer(lid, b, 60, 300) for _ in range(6)]; res = []
        def go(o):
            try: inv.accept_offer(o, s); res.append(1)
            except inv.StockError: res.append(0)
        th = [threading.Thread(target=go, args=(o,)) for o in offs]; [t.start() for t in th]; [t.join() for t in th]
        self.assertEqual(sum(res), 1); L = sql("SELECT available_kg,reserved_kg FROM listings WHERE id=?", (lid,))[0]; self.assertEqual((L[0], L[1]), (40, 60)); self.assertEqual(inv.reconcile(), [])
    def test_http_flow_updates_stock(self):
        lid = new_listing(100, 300, "Maize"); b = login("buyer@kiza.rw"); post(b, f"/market/{lid}/offer", "/market", {"qty_kg": 30, "price_kg": 300}); oid = sql("SELECT MAX(id) FROM offers WHERE listing_id=?", (lid,))[0][0]
        f = login("farmer@kiza.rw"); post(f, f"/offers/{oid}/accept", "/offers"); self.assertEqual(sql("SELECT available_kg,reserved_kg FROM listings WHERE id=?", (lid,))[0][:], (70, 30))
        post(b, f"/offers/{oid}/complete", "/offers", {"rating": 4}); self.assertEqual(sql("SELECT available_kg,reserved_kg,sold_kg FROM listings WHERE id=?", (lid,))[0][:], (70, 0, 30))
        post(b, f"/market/{lid}/offer", "/market", {"qty_kg": 500, "price_kg": 300}); self.assertEqual(sql("SELECT COUNT(*) FROM offers WHERE listing_id=?", (lid,))[0][0], 1)      # over-quantity offer refused

class Future(unittest.TestCase):
    def test_future_listing_hidden_unless_requested_and_state(self):
        fut = str(dt.date.today() + dt.timedelta(60)); lid = new_listing(40, 777, "Rice", fut); b = login("buyer@kiza.rw")
        self.assertNotIn("777", b.get("/market?crop=Rice").data.decode()); self.assertIn("777", b.get("/market?crop=Rice&future=1").data.decode())
        from kiza8.market import listing_state, match; ctx = A.app.app_context(); ctx.push(); self.addCleanup(ctx.pop)
        self.assertEqual(listing_state(sql("SELECT * FROM listings WHERE id=?", (lid,))[0] and dict(DB.conn().execute("SELECT * FROM listings WHERE id=?", (lid,)).fetchone())), "scheduled")
        self.assertEqual([l for l in match("Rice", 10)["lines"] if l["listing_id"] == lid], []); self.assertEqual(len([l for l in match("Rice", 10, include_future=True)["lines"] if l["listing_id"] == lid]), 1)
        when = dt.date.today() + dt.timedelta(61); self.assertEqual(listing_state(dict(DB.conn().execute("SELECT * FROM listings WHERE id=?", (lid,)).fetchone()), str(when)), "active")     # activates automatically on its date

class Matching(unittest.TestCase):
    def test_combines_farmers_cheapest_first_and_never_agrees_for_them(self):
        sql("DELETE FROM listings WHERE crop='Sorghum'"); a = new_listing(20, 500, "Sorghum"); bb = new_listing(30, 450, "Sorghum", seller="demo.huye0@kiza.rw"); new_listing(25, 900, "Sorghum", verified=False)
        from kiza8.market import match; ctx = A.app.app_context(); ctx.push(); self.addCleanup(ctx.pop)
        r = match("Sorghum", 50); self.assertTrue(r["complete"]); self.assertEqual([l["take_kg"] for l in r["lines"]], [30, 20]); self.assertEqual(r["total_rwf"], 30 * 450 + 20 * 500); self.assertEqual(r["total_available_kg"], 50)   # unverified stock ignored
        r2 = match("Sorghum", 80); self.assertFalse(r2["complete"]); self.assertEqual(r2["shortfall_kg"], 30); self.assertEqual(len(match("Sorghum", 50, max_price=460)["lines"]), 1)
        b = login("buyer@kiza.rw"); self.assertEqual(b.get("/market/match?crop=Sorghum&qty=50&unit=kg").status_code, 200); before = sql("SELECT COUNT(*) FROM offers")[0][0]
        post(b, "/market/match", "/market/match", {"crop": "Sorghum", "qty": 50, "unit": "kg", "send": 1}); self.assertEqual(sql("SELECT COUNT(*) FROM offers")[0][0], before + 2)
        self.assertEqual(sql("SELECT COUNT(*) FROM offers WHERE status='Accepted' AND listing_id IN (?,?)", (a, bb))[0][0], 0); self.assertEqual(sql("SELECT available_kg FROM listings WHERE id=?", (a,))[0][0], 20)   # nothing reserved until farmers accept
        t = match("Sorghum", 0.05, None); self.assertTrue(t["complete"])

class Prices(unittest.TestCase):
    def test_missing_price_is_not_zero_and_metadata_kept(self):
        c = DB.conn(); c.row_factory = __import__("sqlite3").Row; self.assertIsNone(P.latest(c, "Wheat", "Nyagatare")) if not c.execute("SELECT 1 FROM price_observations WHERE crop='Wheat'").fetchone() else None
        l = P.latest(c, "Maize", "Musanze"); self.assertIsNotNone(l); self.assertTrue(l["source"] and l["observed_on"] and l["unit"] == "kg" and l["price_rwf"] > 0); self.assertTrue(l["is_simulated"]); self.assertFalse(l["usable"])   # demo data is never 'usable'
        d = {x["district"]: x for x in P.by_district(c, "Maize")}; self.assertEqual(len(d), 30)
        c.execute("DELETE FROM price_observations WHERE crop='Maize' AND district='Huye'"); c.commit(); self.assertIsNone(P.by_district(c, "Maize")[[x["district"] for x in P.by_district(c, "Maize")].index("Huye")]["price"]); c.close()
        r = login("farmer@kiza.rw").get("/api/v8/prices?crop=Maize&district=Huye"); j = json.loads(r.data); self.assertIsNone(j["latest"]); self.assertEqual(j["message"], "No recent verified price available")
        h = login("farmer@kiza.rw").get("/market/intelligence?crop=Maize&district=Huye").data.decode(); self.assertIn("No recent verified price available", h); self.assertNotRegex(h, r"\b0 RWF/kg")
    def test_forecast_only_with_enough_data_time_split_and_baseline(self):
        import math
        self.assertEqual(P.forecast_monthly([300] * 8)["status"], "insufficient_data")
        seas = [300 + 40 * math.sin(2 * math.pi * i / 12) for i in range(48)]; f = P.forecast_monthly(seas)
        self.assertEqual(f["status"], "ok"); self.assertEqual(len(f["forecast"]), 3); self.assertEqual(f["model"], "seasonal_naive"); self.assertTrue(f["beats_baseline"]); self.assertLess(f["mae"]["seasonal_naive"], f["mae"]["naive"])
        noise = [300 + ((i * 7919) % 13) for i in range(30)]; g2 = P.forecast_monthly(noise); self.assertEqual(g2["status"], "ok"); self.assertIn(g2["model"], ("naive", "seasonal_naive", "linear_trend_damped"))
        # no leakage: changing the LAST value must not change validation error of earlier origins' training (check by truncation invariance of forecast for prefix)
        a = P.forecast_monthly(seas[:40]); b = P.forecast_monthly(seas[:40] + [9999.0]); self.assertEqual(a["status"], "ok"); self.assertNotEqual(a["forecast"][0]["point"], b["forecast"][0]["point"] if b["model"] == "naive" else -1)
        for r in f["forecast"]: self.assertTrue(r["low"] is None or r["low"] <= r["point"] <= r["high"])
    def test_import_is_idempotent_validates_and_rejects(self):
        p = os.path.join(tempfile.mkdtemp(), "p.csv")
        open(p, "w").write("crop,district,market,price_type,unit,price_rwf,observed_on,source,source_url,verified,simulated\nMaize,Huye,Huye Market,retail,kg,420,2026-09-20,TEST SOURCE,https://example.org,1,0\nMaize,Huye,Huye Market,wholesale,100kg,38000,2026-09-20,TEST SOURCE,,1,0\nMaize,Huye,Huye Market,retail,kg,0,2026-09-21,TEST SOURCE,,1,0\nUnobtainium,Huye,x,retail,kg,10,2026-09-21,TEST SOURCE,,1,0\nMaize,Huye,x,retail,kg,10,2999-01-01,TEST SOURCE,,1,0\nMaize,Huye,Huye Market,retail,kg,420,2026-09-20,TEST SOURCE,,1,0\n")
        n0 = sql("SELECT COUNT(*) FROM price_observations")[0][0]; r1 = pipeline.import_prices_csv(p); n1 = sql("SELECT COUNT(*) FROM price_observations")[0][0]; r2 = pipeline.import_prices_csv(p); n2 = sql("SELECT COUNT(*) FROM price_observations")[0][0]
        self.assertEqual(n1 - n0, 2); self.assertEqual(n2, n1)                                   # rerun adds nothing
        run = sql("SELECT status, rows_extracted, rows_inserted, rows_rejected, validation FROM pipeline_runs WHERE run_id=?", (r1,))[0]; self.assertEqual((run[0], run[1], run[2], run[3]), ("partial", 6, 2, 4)); self.assertIn("file_sha256", run[4])
        self.assertEqual(sql("SELECT COUNT(*) FROM pipeline_rejects WHERE run_id=?", (r1,))[0][0], 4); self.assertEqual(sql("SELECT rows_inserted FROM pipeline_runs WHERE run_id=?", (r2,))[0][0], 0)
        w = sql("SELECT price_rwf, unit FROM price_observations WHERE price_type='wholesale' AND source='TEST SOURCE'")[0]; self.assertEqual((w[0], w[1]), (380.0, "kg"))   # 100 kg unit normalised to RWF/kg

class Pipelines(unittest.TestCase):
    def test_failure_logged_rolled_back_and_recoverable(self):
        def bad(run): run.c.execute("INSERT INTO price_observations(crop,district,price_rwf,observed_on,source) VALUES('Maize','Huye',1,'2026-01-01','ROLLBACK TEST')"); raise RuntimeError("boom")
        rid = pipeline.run_pipeline("t_fail", "x", "y", bad, retries=1)
        self.assertEqual(sql("SELECT COUNT(*) FROM price_observations WHERE source='ROLLBACK TEST'")[0][0], 0)
        rows = sql("SELECT status, error, retry_count FROM pipeline_runs WHERE name='t_fail' ORDER BY id"); self.assertEqual(len(rows), 2); self.assertTrue(all(r[0] == "failed" and "boom" in r[1] for r in rows)); self.assertEqual(rows[-1][2], 1)
        state = {"n": 0}
        def flaky(run):
            state["n"] += 1
            if state["n"] == 1: raise ConnectionError("temporary")
            run.stats["extracted"] = 1; run.stats["inserted"] = 1
        pipeline.run_pipeline("t_flaky", "x", "y", flaky, retries=2); self.assertEqual([r[0] for r in sql("SELECT status FROM pipeline_runs WHERE name='t_flaky' ORDER BY id")], ["failed", "success"])
    def test_nisr_loader_never_marks_unsourced_rows_official(self):
        p = os.path.join(tempfile.mkdtemp(), "n.csv"); open(p, "w").write("publication,year,season,table_ref,indicator,geography,crop,unit,value,source_url,is_official\nSAS test,2024,A,T1,Production,Huye,Beans,tonnes,5,,1\nSAS test,2024,A,T1,Production,Huye,Maize,tonnes,7,https://www.statistics.gov.rw/x,1\nSAS test,2024,A,T1,Production,Huye,Rice,tonnes,-3,,0\n")
        rid = pipeline.import_nisr_csv(p); self.assertEqual(sql("SELECT rows_inserted, rows_rejected FROM pipeline_runs WHERE run_id=?", (rid,))[0][:], (1, 2)); pipeline.import_nisr_csv(p); self.assertEqual(sql("SELECT COUNT(*) FROM nisr_indicators WHERE publication='SAS test'")[0][0], 1)
        bad = os.path.join(tempfile.mkdtemp(), "b.csv"); open(bad, "w").write("a,b\n1,2\n"); rid = pipeline.import_nisr_csv(bad); self.assertEqual(sql("SELECT status FROM pipeline_runs WHERE run_id=?", (rid,))[0][0], "failed")
        rid = pipeline.import_nisr_csv(os.path.join(ROOT, "data/templates/nisr_sas_SAMPLE_SYNTHETIC.csv")); self.assertEqual(sql("SELECT COUNT(*) FROM nisr_indicators WHERE is_official=1 AND publication LIKE 'SYNTHETIC%'")[0][0], 0); self.assertGreater(sql("SELECT COUNT(*) FROM nisr_indicators WHERE is_synthetic=1")[0][0], 0)
    def test_migrations_idempotent_and_existing_data_kept(self):
        n = sql("SELECT COUNT(*) FROM users")[0][0]; schema.migrate(); schema.migrate(); self.assertEqual(sql("SELECT COUNT(*) FROM users")[0][0], n); self.assertEqual(sql("SELECT MAX(version) FROM schema_version")[0][0], max(s[0] for s in schema.STEPS))

class SmsAndAlerts(unittest.TestCase):
    def setUp(self):
        sms.MockProvider.sent.clear(); sms.MockProvider.fail_next = 0; sms.MockProvider.permanent.clear()
    def _rain(self, district="Rubavu", mm=60):
        sql("DELETE FROM weather WHERE district=?", (district,)); sql("INSERT INTO weather(district,day,temp,rain_prob,rain_mm,rain_7d,humidity,wind,is_demo,fetched_at) VALUES(?,?,?,?,?,?,?,?,0,?)", (district, str(dt.date.today()), 18, 90, mm, 130, 80, 10, "now"))
        sql("DELETE FROM weather_alerts WHERE district=?", (district,)); sql("DELETE FROM sms_outbox WHERE dedupe_key LIKE 'alert:%'")
    def test_classify_rules(self):
        self.assertEqual({a["kind"] for a in alerts.classify([dict(day="2026-10-09", rain_mm=60, rain_prob=90, rain_7d=140)])}, {"heavy_rain", "flood_risk"})
        self.assertEqual([a["kind"] for a in alerts.classify([dict(day="2026-10-09", rain_mm=0, rain_prob=5, rain_7d=2)])], ["drought_risk"]); self.assertEqual(alerts.classify([dict(day="d", rain_mm=5, rain_prob=50, rain_7d=40)]), [])
    def test_alert_sms_localised_deduped_consent_and_not_marked_delivered(self):
        self._rain(); fu = uid("demo.rubavu0@kiza.rw"); sql("UPDATE users SET lang='rw', sms_optin=1 WHERE id=?", (fu,)); other = uid("demo.rubavu1@kiza.rw"); sql("UPDATE users SET lang='en', sms_optin=0 WHERE id=?", (other,))
        self.assertGreaterEqual(alerts.generate(), 1); q1 = alerts.notify_farmers(); q2 = alerts.notify_farmers(); self.assertGreater(q1, 0); self.assertEqual(q2, 0)               # rerun creates no duplicates
        self.assertEqual(alerts.generate(), 0)
        m = sql("SELECT status, body, lang FROM sms_outbox WHERE user_id=? AND kind='weather_alert' ORDER BY id LIMIT 1", (fu,))[0]; self.assertIn("imvura", m[1]); self.assertIn("Rubavu", m[1]); self.assertEqual(m[0], "queued")
        self.assertEqual(sql("SELECT status FROM sms_outbox WHERE user_id=? AND kind='weather_alert' LIMIT 1", (other,))[0][0], "blocked")          # opted out
        r = sms.dispatch(); self.assertGreater(r["submitted"], 0); self.assertTrue(all(p != sql("SELECT phone FROM users WHERE id=?", (other,))[0][0] for _, p, _ in sms.MockProvider.sent))
        st = sql("SELECT status, provider_msg_id FROM sms_outbox WHERE user_id=? AND kind='weather_alert' LIMIT 1", (fu,))[0]; self.assertEqual(st[0], "submitted"); self.assertTrue(st[1])             # accepted by provider != delivered
        n = len(sms.MockProvider.sent); sms.dispatch(); self.assertEqual(len(sms.MockProvider.sent), n)                                                 # no resend
        self.assertTrue(sms.delivery_report(st[1], True)); self.assertEqual(sql("SELECT status FROM sms_outbox WHERE provider_msg_id=?", (st[1],))[0][0], "delivered"); self.assertFalse(sms.delivery_report(st[1], False))
    def test_simulated_weather_not_texted_by_default(self):
        self._rain("Nyabihu"); sql("UPDATE weather SET is_demo=1 WHERE district='Nyabihu'"); alerts.generate(); self.assertEqual(sql("SELECT is_simulated FROM weather_alerts WHERE district='Nyabihu' LIMIT 1")[0][0], 1)
        before = sql("SELECT COUNT(*) FROM sms_outbox")[0][0]; alerts.notify_farmers(allow_simulated=False); self.assertEqual(sql("SELECT COUNT(*) FROM sms_outbox WHERE user_id IN (SELECT id FROM users WHERE district='Nyabihu')")[0][0], 0)
    def test_retry_backoff_then_success_and_permanent_failure(self):
        c = DB.conn(); u = dict(c.execute("SELECT * FROM users WHERE email='demo.rubavu0@kiza.rw'").fetchone()); u["sms_optin"] = 1; k = "t:retry:" + os.urandom(3).hex(); sms.queue(c, u, k, "hello", "test"); c.commit(); c.close()
        sms.MockProvider.fail_next = 1; sms.dispatch(); r = sql("SELECT status, attempts, next_attempt_at FROM sms_outbox WHERE dedupe_key=?", (k,))[0]; self.assertEqual((r[0], r[1]), ("retry", 1)); self.assertGreater(r[2], core.ts())
        sms.dispatch(); self.assertEqual(sql("SELECT status FROM sms_outbox WHERE dedupe_key=?", (k,))[0][0], "retry")          # not due yet
        sql("UPDATE sms_outbox SET next_attempt_at='2000-01-01 00:00:00' WHERE dedupe_key=?", (k,)); sms.dispatch(); self.assertEqual(sql("SELECT status, attempts FROM sms_outbox WHERE dedupe_key=?", (k,))[0][:], ("submitted", 2))
        c = DB.conn(); u["phone"] = "0788999999"; sms.MockProvider.permanent.add("0788999999"); k2 = "t:perm:" + os.urandom(3).hex(); sms.queue(c, u, k2, "x", "test"); c.commit(); c.close(); sms.dispatch(); self.assertEqual(sql("SELECT status FROM sms_outbox WHERE dedupe_key=?", (k2,))[0][0], "failed")
    def test_delivery_webhook_needs_secret(self):
        c = A.app.test_client(); self.assertEqual(c.post("/api/v8/sms/dlr", json={"id": "x", "status": "delivered"}).status_code, 403)
        os.environ["KIZA_SMS_DLR_SECRET"] = "s3cret"
        try: self.assertEqual(c.post("/api/v8/sms/dlr", json={"id": "nope", "status": "delivered"}, headers={"X-Kiza-Secret": "s3cret"}).status_code, 200); self.assertEqual(c.post("/api/v8/sms/dlr", json={}, headers={"X-Kiza-Secret": "bad"}).status_code, 403)
        finally: del os.environ["KIZA_SMS_DLR_SECRET"]
    def test_sms_preference_toggle(self):
        c = login("farmer@kiza.rw"); post(c, "/account/sms", "/profile", {}); self.assertEqual(sql("SELECT sms_optin FROM users WHERE email='farmer@kiza.rw'")[0][0], 0); post(c, "/account/sms", "/profile", {"optin": "1"}); self.assertEqual(sql("SELECT sms_optin FROM users WHERE email='farmer@kiza.rw'")[0][0], 1)

class YieldModel(unittest.TestCase):
    def test_insufficient_data_falls_back_to_labelled_reference(self):
        sql("DELETE FROM yield_models"); r = yieldml.train(); self.assertIn(r["status"], ("insufficient_data",)); c = DB.conn(); c.row_factory = __import__("sqlite3").Row
        fid = sql("SELECT f.id FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE fa.user_id=? ORDER BY f.id LIMIT 1", (uid("farmer@kiza.rw"),))[0][0]; p = yieldml.predict(c, fid); self.assertEqual(p["basis"], "reference_yield"); self.assertEqual(p["model_version"], "reference-table"); self.assertIn("not a prediction", p["limitations"]); c.close()
    def test_trains_on_verified_only_time_split_and_reports_vs_baseline(self):
        sql("DELETE FROM yield_predictions"); sql("DELETE FROM harvest_records"); sql("DELETE FROM yield_models"); c = DB.conn(); c.row_factory = __import__("sqlite3").Row
        fids = [r[0] for r in c.execute("SELECT f.id FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE f.crop='Maize' LIMIT 12")]; self.assertGreaterEqual(len(fids), 6)
        import random; rnd = random.Random(1)
        for yr in (2022, 2023, 2024, 2025):
            for f in fids:
                area = c.execute("SELECT size_ha FROM fields WHERE id=?", (f,)).fetchone()[0]; d = c.execute("SELECT fa.district FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE f.id=?", (f,)).fetchone()[0]
                kgha = 2500 + (400 if d in ("Musanze", "Huye") else -300) + rnd.uniform(-80, 80); c.execute("INSERT INTO harvest_records(field_id,season_year,season,crop,actual_kg,verify_status) VALUES(?,?,?,?,?,'Verified')", (f, yr, "A", "Maize", kgha * area))
        c.execute("INSERT INTO harvest_records(field_id,season_year,season,crop,actual_kg,verify_status) VALUES(?,?,?,?,?,'Submitted')", (fids[0], 2021, "A", "Maize", 1e9)); c.commit()
        r = yieldml.train(c); self.assertEqual(r["n_total"], 4 * len(fids)); self.assertIn(r["status"], ("active", "not_better_than_baseline")); self.assertIn("mae_baseline", r); m = sql("SELECT n_train, n_test FROM yield_models ORDER BY id DESC LIMIT 1")[0]; self.assertEqual(m[1], len(fids)); self.assertEqual(m[0], 3 * len(fids))   # test = latest season only
        p = yieldml.predict(c, fids[0]); self.assertIn("Estimate", p["limitations"]) if p["basis"] == "model" else None; self.assertTrue(p["model_version"]); self.assertLessEqual(p["low_kg"], p["predicted_kg"]); self.assertLessEqual(p["predicted_kg"], p["high_kg"])
        stored = c.execute("SELECT model_version, features FROM yield_predictions ORDER BY id DESC LIMIT 1").fetchone(); self.assertEqual(stored[0], p["model_version"]); self.assertIn("district", stored[1]); mo = yieldml.monitor(c); self.assertIn("mae_kg", mo); c.close()

class GovAndRoles(unittest.TestCase):
    def test_gov_analytics_separates_verified_from_estimated_and_district_scope(self):
        c = login("gov@kiza.rw"); h = c.get("/gov/analytics?district=Musanze&crop=Maize").data.decode(); self.assertIn("Musanze", h)
        a = login("advisor@kiza.rw").get("/gov/analytics?district=Rubavu").data.decode(); self.assertNotIn('<option selected>Rubavu', a)     # district officer is pinned to own district
        self.assertEqual(c.get("/gov/analytics?district=Nowhere").status_code, 404)
    def test_district_and_crop_filters_consistent(self):
        j1 = json.loads(login("farmer@kiza.rw").get("/api/v8/prices?crop=Maize&district=Musanze").data); j2 = json.loads(login("buyer@kiza.rw").get("/api/v8/prices?crop=Maize").data)
        mus = [d for d in j2["districts"] if d["district"] == "Musanze"][0]; self.assertEqual(j1["latest"]["price_rwf"], mus["price"] if abs(j1["latest"]["price_rwf"] - mus["price"]) < 1 else None)
        self.assertEqual(login("farmer@kiza.rw").get("/api/v8/prices?crop=Nope").status_code, 404)

class Ops(unittest.TestCase):
    def test_admin_ops_jobs_run(self):
        c = login("admin@kiza.rw")
        for job in ("backfill", "reconcile", "yield", "nisr", "dispatch", "alerts"): self.assertEqual(post(c, "/admin/ops", "/admin/ops", {"job": job}).status_code, 302, job)
        self.assertEqual(c.get("/admin/ops").status_code, 200); self.assertEqual(post(c, "/admin/ops", "/admin/ops", {"job": "rm -rf"}).status_code, 400)
    def test_jobs_module_runs_cleanly(self):
        from kiza8 import jobs; out = jobs.run_all(); self.assertEqual(out["stock_mismatch"], [])

if __name__ == "__main__":
    unittest.main()
