import os, re, io, sys, tempfile, unittest
os.environ["KIZA_AUTO_SYNC"] = "0"; os.environ.setdefault("KIZA_DB", os.path.join(tempfile.mkdtemp(), "t.db")); os.environ.setdefault("KIZA_UPLOADS", tempfile.mkdtemp()); os.environ.setdefault("KIZA_ML_URL", "http://127.0.0.1:59999")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image
import app as A

def q1(sql, a=()):
    with A.app.app_context(): return A.Q1(sql, a)
def pl(l):
    with A.app.app_context(): return A.plausibility(l)
def tok(c, p="/login"): return re.search(r'name="_csrf" value="([^"]+)"', c.get(p).get_data(as_text=True)).group(1)
def login(who):
    c = A.app.test_client(); c.get("/lang/en"); c.post("/login", data={"_csrf": tok(c), "ident": who, "password": "Kiza@2026-demo"}); return c
def jpg(col):
    b = io.BytesIO(); Image.new("RGB", (300, 300), col).save(b, "JPEG"); b.seek(0); return b

class T(unittest.TestCase):
    def test_sell_verify_buy_flow(self):
        f = login("farmer@kiza.rw"); t = tok(f, "/market")
        r = f.post("/market/sell", data={"_csrf": t, "crop": "Potato", "qty_kg": "500", "price_kg": "300", "village": "Kinigi", "contact": "0788000001", "lat": "-1.5", "lng": "29.6", "photo": (jpg("green"), "h.jpg")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        l = q1("SELECT * FROM listings ORDER BY id DESC LIMIT 1"); self.assertEqual(l["village"], "Kinigi"); self.assertEqual(l["verify_status"], "Pending"); self.assertTrue(l["photo"])
        self.assertEqual(f.get("/media/" + l["photo"]).status_code, 200); self.assertEqual(f.get("/media/../app.py").status_code, 404)
        # bad upload rejected
        f.post("/market/sell", data={"_csrf": t, "crop": "Potato", "qty_kg": "5", "price_kg": "30", "village": "X", "contact": "0788000001", "photo": (io.BytesIO(b"not an image"), "x.jpg")}, content_type="multipart/form-data")
        self.assertEqual(q1("SELECT COUNT(*) c FROM listings WHERE village='X'")["c"], 0)
        o = login("officer@kiza.rw"); self.assertEqual(o.get("/verify").status_code, 200); self.assertIn("Kinigi", o.get("/verify").get_data(as_text=True))
        o.post("/verify", data={"_csrf": tok(o, "/verify"), "id": l["id"], "decision": "Verified", "visited": "1", "note": "Seen on site"})
        self.assertEqual(q1("SELECT verify_status FROM listings WHERE id=?", (l["id"],))["verify_status"], "Verified")
        b = login("buyer@kiza.rw"); h = b.get("/market").get_data(as_text=True); self.assertIn("Kinigi", h); self.assertIn("vb v", h)
        self.assertEqual(f.get("/verify").status_code, 403); self.assertEqual(b.get("/verify").status_code, 403)
    def test_plausibility_flags_inflated_claim(self):
        l = {"seller_id": q1("SELECT id FROM users WHERE email='farmer@kiza.rw'")["id"], "crop": "Potato", "qty_kg": 9e7, "photo": None, "lat": None, "village": ""}
        self.assertTrue(any(k == "bad" for k, _ in pl(l)))
    def test_profile_and_scan_all_roles(self):
        for who in ("farmer@kiza.rw", "buyer@kiza.rw", "officer@kiza.rw", "gov@kiza.rw"):
            c = login(who); self.assertEqual(c.get("/profile").status_code, 200); t = tok(c, "/profile")
            r = c.post("/profile", data={"_csrf": t, "name": "New Name", "phone": q1("SELECT phone FROM users WHERE email=?", (who,))["phone"], "district": "Musanze", "village": "V", "bio": "hi", "lang": "rw", "photo": (jpg("blue"), "p.jpg")}, content_type="multipart/form-data")
            self.assertEqual(q1("SELECT village, photo FROM users WHERE email=?", (who,))["village"], None if who == "officer@kiza.rw" else "V"); self.assertTrue(q1("SELECT photo FROM users WHERE email=?", (who,))["photo"])
            r = c.post("/scan", data={"_csrf": t, "crop": "Potato", "sym": ["spots", "rot"], "photo": (jpg((60, 120, 40)), "l.jpg")}, content_type="multipart/form-data")
            self.assertEqual(r.status_code, 200); self.assertIn("Late blight", r.get_data(as_text=True))

    def test_village_advisor_confirms_or_rejects_on_the_ground(self):
        g = login("admin@kiza.rw")
        def mk(name, phone, village):
            T = tok(g, "/admin/advisors"); self.assertEqual(g.post("/admin/advisors", data={"_csrf": T, "name": name, "phone": phone, "district": "Musanze", "sector": "Muhoza", "village": village}).status_code, 302)
            with g.session_transaction() as s: return re.search(r"password: (\S+) ", " ".join(m for _, m in s.get("_flashes", []))).group(1)
        pw, pw2 = mk("Adv One", "0788555001", "Rugarama"), mk("Adv Two", "0788555002", "Other Village")
        f = login("farmer@kiza.rw"); t = tok(f, "/market")
        for crop in ("Potato", "Maize"): f.post("/market/sell", data={"_csrf": t, "crop": crop, "qty_kg": "300", "price_kg": "250", "village": "Rugarama", "contact": "0788000001"})
        ids = [r["id"] for r in A.db.conn().execute("SELECT id FROM listings WHERE village='Rugarama' ORDER BY id").fetchall()]; ok_id, bad_id = ids[-2], ids[-1]
        a = A.app.test_client(); a.get("/lang/rw"); self.assertEqual(a.post("/login", data={"_csrf": tok(a), "ident": "0788555001", "password": pw}).headers["Location"], "/verify")   # advisor lands on the verify page
        self.assertEqual(q1("SELECT COUNT(*) c FROM notifications WHERE user_id=(SELECT id FROM users WHERE phone='0788555001') AND kind='verify'")["c"], 2)
        self.assertIn("Rugarama", a.get("/verify").get_data(as_text=True))
        other = A.app.test_client(); other.get("/lang/en"); other.post("/login", data={"_csrf": tok(other), "ident": "0788555002", "password": pw2}); self.assertNotIn("Rugarama", other.get("/verify").get_data(as_text=True))
        T = tok(a, "/verify")
        a.post("/verify", data={"_csrf": T, "id": ok_id, "decision": "Verified"}); self.assertEqual(q1("SELECT verify_status FROM listings WHERE id=?", (ok_id,))["verify_status"], "Pending")      # must tick "I visited"
        a.post("/verify", data={"_csrf": T, "id": bad_id, "decision": "Rejected"}); self.assertEqual(q1("SELECT verify_status FROM listings WHERE id=?", (bad_id,))["verify_status"], "Pending")      # reason required
        other.post("/verify", data={"_csrf": tok(other, "/verify"), "id": ok_id, "decision": "Verified", "visited": "1"}); self.assertEqual(q1("SELECT verify_status FROM listings WHERE id=?", (ok_id,))["verify_status"], "Pending")  # other village: no access
        a.post("/verify", data={"_csrf": T, "id": ok_id, "decision": "Verified", "visited": "1", "verified_qty": "250", "lat": "-1.5", "lng": "29.6"})
        a.post("/verify", data={"_csrf": T, "id": bad_id, "decision": "Rejected", "reason": "Crop not found at the farm"})
        l = q1("SELECT * FROM listings WHERE id=?", (ok_id,)); self.assertEqual((l["verify_status"], l["visited"], l["verified_qty"], l["available_kg"]), ("Verified", 1, 250, 250))
        self.assertEqual(q1("SELECT reject_reason FROM listings WHERE id=?", (bad_id,))["reject_reason"], "Crop not found at the farm")
        n = f.get("/notifications").get_data(as_text=True); self.assertIn("REJECTED", n); self.assertIn("CONFIRMED", n)
        b = login("buyer@kiza.rw"); h = b.get("/market").get_data(as_text=True)
        self.assertIn("Rugarama", h)
        self.assertEqual(b.post(f"/market/{bad_id}/offer", data={"_csrf": tok(b, "/market"), "qty_kg": "10", "price_kg": "250"}).status_code, 302); self.assertEqual(q1("SELECT COUNT(*) c FROM offers WHERE listing_id=?", (bad_id,))["c"], 0)
        self.assertNotIn(f"/market/{bad_id}/offer", h)
    def test_language_choice_and_french(self):
        c = A.app.test_client(); self.assertEqual(c.get("/").headers["Location"], "/welcome"); h = c.get("/welcome").get_data(as_text=True)
        for x in ("Welcome to KIZA-AGRI", "Choose language", "Hitamo ururimi", "Choisissez la langue"): self.assertIn(x, h)
        self.assertEqual(c.get("/lang/fr?next=/").headers["Location"], "/"); h = c.get("/").get_data(as_text=True); self.assertIn("Cultivez mieux.", h); self.assertIn("Connexion", h)
        c.get("/lang/rw"); self.assertIn("Hinga neza.", c.get("/").get_data(as_text=True)); c.get("/lang/xx"); self.assertIn("Grow smarter.", c.get("/").get_data(as_text=True))
        self.assertEqual(c.get("/lang/en?next=//evil.com").headers["Location"], "/")
        d = login("farmer@kiza.rw"); d.get("/lang/fr"); self.assertEqual(q1("SELECT lang FROM users WHERE email='farmer@kiza.rw'")["lang"], "fr"); self.assertIn("Vendre ma récolte", d.get("/market").get_data(as_text=True))

    def test_deals_ratings_alerts_sorting_export(self):
        f = login("farmer@kiza.rw"); b = login("buyer@kiza.rw"); o = login("officer@kiza.rw"); g = login("gov@kiza.rw")
        # buyer sets an alert (guard: unknown crop rejected, duplicates ignored)
        t = tok(b, "/market"); b.post("/market/watch", data={"_csrf": t, "crop": "Nope"}); self.assertEqual(q1("SELECT COUNT(*) c FROM watches")["c"], 0)
        for _ in range(2): b.post("/market/watch", data={"_csrf": t, "crop": "Cassava", "district": "Musanze"})
        self.assertEqual(q1("SELECT COUNT(*) c FROM watches WHERE crop='Cassava'")["c"], 1); self.assertIn("Cassava", b.get("/market").get_data(as_text=True))
        # new listing -> confirmation notifies the watcher
        f.post("/market/sell", data={"_csrf": tok(f, "/market"), "crop": "Cassava", "qty_kg": "700", "price_kg": "210", "village": "Demo Village", "contact": "0788000001"})
        lid = q1("SELECT MAX(id) m FROM listings")["m"]; self.assertNotIn("Cassava", " ".join(r["message"] for r in A.Q.__globals__["db"].conn().execute("SELECT message FROM notifications WHERE kind='alert'").fetchall()) or "")
        a = login("advisor@kiza.rw"); self.assertEqual(a.get("/verify").status_code, 200); self.assertIn("Waiting for your visit", a.get("/lang/en") and a.get("/verify").get_data(as_text=True))
        a.post("/verify", data={"_csrf": tok(a, "/verify"), "id": lid, "decision": "Verified", "visited": "1"}); self.assertEqual(q1("SELECT COUNT(*) c FROM notifications WHERE kind='alert' AND message LIKE '%Cassava%'")["c"], 1)
        # offer -> accept -> only the buyer can complete; rating shows on the farmer profile
        b.post(f"/market/{lid}/offer", data={"_csrf": tok(b, "/market"), "qty_kg": "100", "price_kg": "215"}); oid = q1("SELECT MAX(id) m FROM offers")["m"]
        self.assertEqual(b.post(f"/offers/{oid}/complete", data={"_csrf": tok(b, "/offers"), "rating": "5"}).status_code, 403)      # not accepted yet
        f.post(f"/offers/{oid}/accept", data={"_csrf": tok(f, "/offers")})
        self.assertEqual(f.post(f"/offers/{oid}/complete", data={"_csrf": tok(f, "/offers"), "rating": "5"}).status_code, 403)       # seller cannot rate themselves
        self.assertEqual(b.post(f"/offers/{oid}/complete", data={"_csrf": tok(b, "/offers"), "rating": "99", "review": "Great <b>quality</b>"}).status_code, 302)
        r = q1("SELECT status, rating FROM offers WHERE id=?", (oid,)); self.assertEqual((r["status"], r["rating"]), ("Completed", 5))   # out-of-range rating falls back to a valid value
        uid = q1("SELECT id FROM users WHERE email='farmer@kiza.rw'")["id"]; h = b.get(f"/u/{uid}").get_data(as_text=True); self.assertIn("Completed deals", h); self.assertIn("&lt;b&gt;quality", h)
        self.assertEqual(b.post(f"/offers/{oid}/complete", data={"_csrf": tok(b, "/offers"), "rating": "1"}).status_code, 403)         # cannot rate twice
        # sorting + paging stay valid for odd input
        for q in ("sort=price_asc", "sort=price_desc", "sort=qty", "sort=%27;drop", "page=abc", "page=999", "page=-3&crop=Potato"): self.assertEqual(b.get("/market?" + q).status_code, 200, q)
        lo = [int(x) for x in re.findall(r'class="pr">(\d+)', b.get("/market?sort=price_asc").get_data(as_text=True))]; self.assertEqual(lo, sorted(lo))
        # CSV export: staff only, formula-injection guarded
        self.assertEqual(f.get("/admin/export/listings.csv").status_code, 403); self.assertEqual(o.get("/admin/export/listings.csv").status_code, 403); self.assertEqual(g.get("/admin/export/nope.csv").status_code, 404)
        A.X.__globals__  # noqa
        with A.app.app_context(): A.X("UPDATE listings SET verify_note='=HYPERLINK(\"x\")' WHERE id=?", (lid,))
        c = g.get("/admin/export/listings.csv"); txt = c.get_data(as_text=True); self.assertEqual(c.status_code, 200); self.assertIn("text/csv", c.content_type); self.assertIn("'=HYPERLINK", txt); self.assertIn("Cassava", txt)
        for k in ("offers", "advisors"): self.assertEqual(g.get(f"/admin/export/{k}.csv").status_code, 200)
        self.assertIn("data-theme-toggle", b.get("/market").get_data(as_text=True))
    def test_colour_screen(self):
        import disease; p = os.path.join(tempfile.gettempdir(), "t.jpg"); Image.new("RGB", (100, 100), (50, 150, 50)).save(p)
        self.assertGreater(disease.colour_screen(p)["health"], 70)
        Image.new("RGB", (100, 100), (200, 200, 30)).save(p); self.assertIn("yellow", disease.colour_screen(p)["infer"])
if __name__ == "__main__": unittest.main()


class N(unittest.TestCase):
    """v7: assistant for every account, PWA files, gzip, admin users, price edit."""
    def test_assistant_works_for_every_account_and_language(self):
        for who in (None,):   # the assistant is for visitors who are not logged in; signed-in users get a polite notice
            for lg in ("en", "rw", "fr"):
                c = A.app.test_client(); c.get(f"/lang/{lg}?next=/")
                for q in ("hello", "potato price", "weather", "fertilizer", "my listings", "my offers", "notifications", "to verify", "xyz?"):
                    r = c.post("/api/assistant", data={"q": q})            # no CSRF token on purpose: read-only endpoint must never break
                    self.assertEqual(r.status_code, 200, (who, lg, q)); self.assertTrue(r.get_json()["reply"])
        f = login("farmer@kiza.rw"); self.assertIn("visitors", f.post("/api/assistant", data={"q": "my listings"}).get_json()["reply"])
        self.assertEqual(A.app.test_client().get("/api/nothing").get_json()["error"], "not found")
    def test_pwa_and_gzip(self):
        c = A.app.test_client(); m = c.get("/manifest.webmanifest"); self.assertEqual(m.status_code, 200); self.assertEqual(m.get_json()["short_name"], "KIZA")
        s = c.get("/sw.js"); self.assertEqual(s.status_code, 200); self.assertEqual(s.headers["Service-Worker-Allowed"], "/")
        self.assertEqual(c.get("/static/icon-192.png").status_code, 200); self.assertEqual(c.get("/favicon.ico").status_code, 301); self.assertEqual(c.get("/offline").status_code, 200)
        r = c.get("/login", headers={"Accept-Encoding": "gzip"}); self.assertEqual(r.headers.get("Content-Encoding"), "gzip")
        import gzip; self.assertIn("KIZA", gzip.decompress(r.data).decode())
    def test_admin_users_reset_block_and_price_edit(self):
        g = login("admin@kiza.rw"); self.assertEqual(g.get("/admin/users?q=farmer").status_code, 200)
        fid = q1("SELECT id FROM users WHERE email='farmer@kiza.rw'")["id"]
        r = g.post("/admin/users", data={"_csrf": tok(g, "/admin/users"), "id": fid, "act": "reset"}, follow_redirects=True); import re as _re
        pw = _re.search(r"Temporary password for [^:]+: (\S+) -", r.get_data(as_text=True)).group(1)
        c2 = A.app.test_client(); c2.get("/lang/en"); c2.post("/login", data={"_csrf": tok(c2), "ident": "0788000001", "password": pw}); self.assertEqual(c2.get("/farmer").status_code, 200)       # new temporary password works
        b = A.db.conn(); b.execute("UPDATE users SET pw_hash=(SELECT pw_hash FROM users WHERE email='buyer@kiza.rw') WHERE id=?", (fid,)); b.commit()   # restore demo password for later tests
        o = login("officer@kiza.rw"); self.assertEqual(o.get("/admin/users").status_code, 403)
        f = login("farmer@kiza.rw"); lid = q1("SELECT id FROM listings WHERE seller_id=? AND status='Available' ORDER BY id DESC", (fid,))["id"]
        f.post(f"/market/{lid}/price", data={"_csrf": tok(f, "/market"), "price_kg": "777"}); self.assertEqual(q1("SELECT price_kg FROM listings WHERE id=?", (lid,))["price_kg"], 777)
        bu = login("buyer@kiza.rw"); self.assertEqual(bu.post(f"/market/{lid}/price", data={"_csrf": tok(bu, "/market"), "price_kg": "1"}).status_code, 403)
