"""USSD menu engine + gateway endpoint + simulator, crop catalogue (100+), assistant matching fixes. All offline.  Run: python -m unittest discover tests"""
import os, sys, re, tempfile, sqlite3, unittest
os.environ.setdefault("KIZA_DB", os.path.join(tempfile.mkdtemp(), "t.db")); os.environ.setdefault("KIZA_ML_URL", "http://127.0.0.1:59999"); os.environ.setdefault("KIZA_AUTO_SYNC", "0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db, ussd, crops_data, disease

def C():
    c = sqlite3.connect(db.DB); c.row_factory = sqlite3.Row; return c
FARMER, BUYER, NOBODY = "0788000001", "0788000002", "0722999999"      # demo farmer (Musanze), demo buyer, unregistered

class Catalogue(unittest.TestCase):
    def test_100_plus_unique_valid_crops(self):
        names = [r[0] for r in db.CROPS + crops_data.EXTRA]; self.assertGreaterEqual(len(crops_data.EXTRA), 100); self.assertEqual(len(names), len(set(names)))
        for r in db.CROPS + crops_data.EXTRA:
            self.assertTrue(r[1] > 0 and r[2] > 0 and r[3] > 0 and r[4] < r[5] and r[6] < r[7] and r[8] < r[9] and r[11] in ("Low", "Medium", "High") and 0 <= r[12] <= 1 and r[13] > 0, r[0])
            self.assertTrue(set(r[10].split(",")) <= {"A", "B", "C"}, r[0])
        self.assertTrue({f[0] for f in crops_data.FERT_EXTRA} <= set(names))
    def test_demo_db_has_them_and_template_loads(self):
        c = C(); self.assertGreaterEqual(c.execute("SELECT COUNT(*) FROM crops").fetchone()[0], 106)
        import loaders; r = loaders.load("crops", crops_data.csv_text(db.CROPS), 1, c); self.assertEqual(r["bad"], 0); self.assertEqual(r["ok"], 109)    # the shipped CSV passes the upload validator
    def test_generic_scanner_advice_for_any_crop(self):
        self.assertTrue(disease.rank("Onion", ["spots"])); self.assertEqual(disease.rank("Potato", ["spots", "rot"])[0]["name"], "Late blight")

class Menu(unittest.TestCase):
    def setUp(self): self.c = C()
    def h(self, text, phone=FARMER, write=False): return ussd.handle(text, phone, self.c, write)
    def test_main_menu_and_language(self):
        r = self.h(""); self.assertTrue(r.startswith("CON KIZA-AGRI")); self.assertIn("Prices", r); self.assertIn("Ibiciro", self.h("", NOBODY))      # known phone: saved language (demo = English); unknown phone: Kinyarwanda
        self.assertIn("Ibiciro", self.h("9")); self.assertIn("Prices", self.h("9*9")); self.assertIn("Choose province", self.h("9*1", NOBODY)); self.assertIn("Hitamo intara", self.h("1", NOBODY))
    def test_prices_flow_known_phone_skips_location(self):
        r = self.h("1"); self.assertTrue(r.startswith("CON") and "Musanze" in r); end = self.h("1*1"); self.assertTrue(end.startswith("END") and "RWF/kg" in end and "Musanze" in end)
    def test_prices_flow_unknown_phone_asks_province_then_district(self):
        self.assertIn("Kigali", self.h("1", NOBODY)); self.assertIn("Gasabo", self.h("1*1", NOBODY)); self.assertIn("1 ", self.h("1*1*1", NOBODY)); end = self.h("1*1*1*1", NOBODY)
        self.assertTrue(end.startswith("END") and "Gasabo" in end)
    def test_weather_soil_croptip(self):
        w = self.h("2"); self.assertTrue(w.startswith("END") and "Musanze" in w and "%" in w); s = self.h("3"); self.assertTrue(s.startswith("END") and "pH" in s and "Musanze" in s)
        t = self.h("4"); self.assertTrue(t.startswith("END") and "1." in t and "3." in t)
    def test_back_and_main_menu(self):
        self.assertEqual(self.h("1*0"), self.h("")); self.assertEqual(self.h("1*1*00"), self.h("")); self.assertEqual(self.h("0"), self.h(""))
    def test_invalid_input_ends_cleanly(self):
        for t in ("7", "abc", "1*9", "1*0*0*x", "5*8"): self.assertTrue(self.h(t).startswith("END"), t)
        self.assertTrue(self.h("1*1*99", NOBODY).startswith("END"))
    def test_every_reply_is_short_ascii(self):
        paths = ["", "9", "1", "2", "3", "4", "5", "1*1", "5*1", "5*1*1", "5*1*1*500", "5*1*1*500*1", "5*1*1*500*2"] + [f"1*{p}*{d}" for p in range(1, 6) for d in range(1, 9)]
        for ph in (FARMER, NOBODY, BUYER):
            for lang in ("", "9*"):
                for p in paths:
                    r = self.h(lang + p, ph); self.assertRegex(r, r"^(CON|END) \S", (p, r)); self.assertLessEqual(len(r), 182, (p, len(r))); self.assertTrue(r.isascii(), (p, r))
    def test_report_needs_farmer_and_saves_only_with_gateway_token(self):
        self.assertIn("iyandikishe", self.h("5", NOBODY)); self.assertIn("Register as a farmer", self.h("5", BUYER)); self.assertTrue(self.h("5").startswith("CON"))
        n0 = self.c.execute("SELECT COUNT(*) FROM distress_reports").fetchone()[0]; flow = "5*1*1*500*"
        self.assertIn("off", self.h(flow + "1", write=False)); self.assertEqual(self.c.execute("SELECT COUNT(*) FROM distress_reports").fetchone()[0], n0)      # read-only mode
        self.assertIn("Report sent", self.h(flow + "1", write=True)); self.h(flow + "1", write=True)                                                             # gateway retry
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM distress_reports").fetchone()[0], n0 + 1)                                                               # saved once
        row = self.c.execute("SELECT * FROM distress_reports ORDER BY id DESC LIMIT 1").fetchone(); self.assertEqual((row["qty_kg"], row["district"], row["details"]), (500, "Musanze", "Sent by USSD"))
        self.assertTrue(self.c.execute("SELECT COUNT(*) FROM notifications WHERE message LIKE '%USSD%'").fetchone()[0] >= 1)
        self.assertIn("Cancelled", self.h(flow + "2", write=True)); self.assertEqual(self.c.execute("SELECT COUNT(*) FROM distress_reports").fetchone()[0], n0 + 1); self.assertTrue(self.h("5*1*1*abc", write=True).startswith("END")); self.assertTrue(self.h("5*1*1*0", write=True).startswith("CON"))   # cancel; bad kg ends; 0 = back

class Gateway(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global A; import app as A
    def post(self, token=None, **kw):
        c = A.app.test_client(); d = {"sessionId": "s1", "serviceCode": "*384#", "phoneNumber": "+250788000001", "text": ""}; d.update(kw)
        return c.post("/ussd" + (f"?token={token}" if token else ""), data=d)          # NO csrf token: gateways cannot send one
    def test_gateway_plain_text_and_phone_formats(self):
        r = self.post(); self.assertEqual((r.status_code, r.mimetype), (200, "text/plain")); self.assertTrue(r.data.decode().startswith("CON")); self.assertIn("Muraho" if False else "KIZA-AGRI", r.data.decode())
        self.assertIn("Musanze", self.post(text="1").data.decode()); self.assertIn("Choose province", self.post(phoneNumber="+250722999999", text="9*1").data.decode())
    def test_token_protection_and_write_gate(self):
        os.environ["KIZA_USSD_TOKEN"] = "s3cret"
        try:
            self.assertEqual(self.post().status_code, 403); self.assertEqual(self.post(token="nope").status_code, 403); ok = self.post(token="s3cret", text="5*1*1*20*1")
            self.assertEqual(ok.status_code, 200); self.assertIn("Report sent", ok.data.decode())
        finally: del os.environ["KIZA_USSD_TOKEN"]
        self.assertIn("switched off", self.post(text="5*1*1*20*1").data.decode())                                 # no token configured -> reports stay off
    def test_get_not_allowed_and_garbage_input(self):
        self.assertEqual(A.app.test_client().get("/ussd").status_code, 405); self.assertTrue(self.post(text="1*" * 90).data.decode().startswith("END")); self.assertEqual(self.post(phoneNumber="x", text="").status_code, 200)
    def test_simulator_page_and_api(self):
        c = A.app.test_client(); page = c.get("/ussd-sim").data.decode(); self.assertIn("USSD", page); tok = re.search(r"_csrf:'(\w+)'", page).group(1)
        j = c.post("/ussd-sim/send", data={"_csrf": tok, "text": "", "as_me": "0"}).get_json(); self.assertFalse(j["end"]); self.assertIn("KIZA-AGRI", j["reply"])
        self.assertTrue(c.post("/ussd-sim/send", data={"_csrf": tok, "text": "2", "as_me": "0"}).get_json()["end"] is False)   # unknown phone -> asks province
        self.assertEqual(c.post("/ussd-sim/send", data={"text": ""}).status_code, 302)                                       # CSRF still enforced on the simulator
    def test_nav_links_to_ussd(self): self.assertIn("/ussd-sim", A.app.test_client().get("/about").data.decode())

class AssistantFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global A; import app as A
    def ask(self, q, lang="en"):
        with A.app.test_request_context(): return A.assistant_reply(q, None, lang)[0]
    def test_price_is_not_rice(self): self.assertNotIn("Rice:", self.ask("what is the price in Gasabo")); self.assertIn("Potato", self.ask("potato price")); self.assertIn("Rice", self.ask("price of rice"))
    def test_short_keywords_are_whole_words(self):
        self.assertNotIn("pH", self.ask("send photo please")); self.assertNotIn("Hello", self.ask("which crop is best")); self.assertIn("Hello", self.ask("hi"))
        self.assertIn("soil", self.ask("what is my soil ph").lower())
    def test_new_catalogue_crops_found(self):
        with A.app.test_request_context(): self.assertEqual((A.find_crop("sweet potato price"), A.find_crop("how is wheat doing"), A.find_crop("igiciro cy'ibijumba"), A.find_crop("hello")), ("Sweet potato", "Wheat", "Sweet potato", None))

if __name__ == "__main__": unittest.main()
