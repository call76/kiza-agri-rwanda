"""v11: auth pages, farm-health, plan, profit/calendar/live pages, search API, data.gov.rw connector (mocked HTTP)."""
import os, sys, json, re, unittest, tempfile
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["KIZA_DB"] = tempfile.mktemp(suffix=".db"); os.environ["KIZA_AUTO_SYNC"] = "0"; os.environ["KIZA_JOBS"] = "0"
os.environ["KIZA_DATAGOV_KEY"] = "dsp_pub_test0000000000000000"
import db; db.init(force=True)
import app as A
from kiza8 import datagov as DG, care as CR
import datetime as dt

def login(c, ident):
    t = c.get("/login"); csrf = re.search(r'name="_csrf" value="([^"]+)"', t.get_data(True)).group(1)
    return c.post("/login", data={"_csrf": csrf, "ident": ident, "password": db.DEMO_PASSWORD})

class R:
    def __init__(s, code, text, ct="application/json"): s.status_code, s.text, s.headers = code, text, {"content-type": ct}

class T(unittest.TestCase):
    def test_public_pages(self):
        c = A.app.test_client()
        for u in ("/welcome", "/login", "/register"):
            self.assertEqual(c.get(u).status_code, 200)
        self.assertIn("av-sheet", c.get("/login").get_data(True)); self.assertIn("id=\"rf\"", c.get("/register").get_data(True))

    def test_new_pages_every_role_and_language(self):
        for ident in ("farmer@kiza.rw", "buyer@kiza.rw", "advisor@kiza.rw", "gov@kiza.rw", "admin@kiza.rw"):
            for lg in ("en", "rw", "fr"):
                c = A.app.test_client(); login(c, ident); c.get("/lang/" + lg)
                for u in ("/profit", "/calendar", "/live", "/api/v11/plan", "/api/v11/search?q=ma"):
                    self.assertEqual(c.get(u).status_code, 200, (ident, lg, u))

    def test_farmer_dashboard_health_and_plan(self):
        c = A.app.test_client(); login(c, "farmer@kiza.rw")
        h = c.get("/api/v11/health").get_json()["health"]
        self.assertTrue(0 <= h["score"] <= 100); self.assertTrue(h["comps"])
        self.assertIn("kh-health", c.get("/farmer").get_data(True))
        self.assertTrue(c.get("/api/v11/plan").get_json()["items"])
        self.assertEqual(login(A.app.test_client(), "buyer@kiza.rw").status_code, 302)
        b = A.app.test_client(); login(b, "buyer@kiza.rw"); self.assertEqual(b.get("/api/v11/health").status_code, 403)

    def test_search(self):
        c = A.app.test_client(); login(c, "farmer@kiza.rw")
        j = c.get("/api/v11/search?q=maiz").get_json(); self.assertTrue(any(x["name"] == "Maize" for x in j["crops"]))
        self.assertEqual(c.get("/api/v11/search?q=m").get_json()["crops"], [])

    def test_datagov_parse_and_map(self):
        rows, how = DG.parse('{"data":[{"District":"Musanze","Commodity":"Maize","Retail_Price":"512","Date":"2026-10-20"}]}')
        self.assertEqual(how, "json"); cols = DG.resolve(list(rows[0].keys()))
        self.assertEqual((cols["price"], cols["day"], cols["crop"]), ("Retail_Price", "Date", "Commodity"))
        r = DG.import_rows("market_prices", rows, None, "t"); self.assertEqual(r["ok"], 1)
        r = DG.import_rows("production", [{"district": "Musanze", "crop": "Maize", "year": "2024", "production_tonnes": "1200"}], None, "t"); self.assertEqual(r["ok"], 1)
        r = DG.import_rows("production", [{"district": "Nowhere", "crop": "Maize", "year": "2024", "tonnes": "5"}], None, "t"); self.assertEqual(r["ok"], 0)

    def test_datagov_errors_and_key_never_leaks(self):
        with mock.patch("requests.get", return_value=R(401, "")):
            with self.assertRaises(DG.DGError) as e: DG.fetch("abc")
            self.assertIn("rejected", str(e.exception))
        with mock.patch("requests.get", return_value=R(404, "")):
            with self.assertRaises(DG.DGError): DG.fetch("abc")
        with self.assertRaises(DG.DGError): DG.fetch("bad id!")
        with mock.patch("requests.get", return_value=R(200, "[]")) as g:
            DG.fetch("abc"); self.assertEqual(g.call_args.kwargs["headers"]["X-API-Key"], "dsp_pub_test0000000000000000")
            self.assertIn("/assets/public/abc/download", g.call_args.args[0])
        c = A.app.test_client(); login(c, "admin@kiza.rw"); html = c.get("/admin/datagov").get_data(True)
        self.assertNotIn("dsp_pub_test0000000000000000", html); self.assertIn("0000", html)
        f = A.app.test_client(); login(f, "farmer@kiza.rw"); self.assertEqual(f.get("/admin/datagov").status_code, 403)

    # ---- care: spray planner, tasks, badges
    def _csrf(self, c, path="/care"):
        return re.search(r'name="_csrf" value="([^"]+)"', c.get(path).get_data(True)).group(1)

    def test_care_pages_roles_languages(self):
        for lg in ("en", "rw", "fr"):
            c = A.app.test_client(); login(c, "farmer@kiza.rw"); c.get("/lang/" + lg)
            for u in ("/care", "/badges", "/api/v11/care/summary", "/api/v11/badges"):
                self.assertEqual(c.get(u).status_code, 200, (lg, u))
        b = A.app.test_client(); login(b, "buyer@kiza.rw")
        self.assertEqual(b.get("/care").status_code, 403); self.assertEqual(b.get("/badges").status_code, 200)
        self.assertNotEqual(A.app.test_client().get("/care").status_code, 200)

    def test_spray_plan_phi_warning_and_reminder(self):
        c = A.app.test_client(); login(c, "farmer@kiza.rw")
        fid = db.conn().execute("SELECT f.id FROM fields f JOIN farms fa ON fa.id=f.farm_id JOIN users u ON u.id=fa.user_id WHERE u.email='farmer@kiza.rw' LIMIT 1").fetchone()[0]
        day = str(dt.date.today() + dt.timedelta(1))
        r = c.post("/care/spray", data={"_csrf": self._csrf(c), "product": "TestProd", "purpose": "fungus", "applied_on": day, "phi_days": "14", "field_id": fid, "mode": "plan"}, follow_redirects=True)
        self.assertEqual(r.status_code, 200); self.assertIn("TestProd", r.get_data(True))
        row = db.conn().execute("SELECT * FROM spray_log WHERE product='TestProd'").fetchone()
        self.assertTrue(row["planned"]); self.assertEqual(row["safe_harvest"], str(dt.date.today() + dt.timedelta(15)))
        # invalid input is rejected
        c.post("/care/spray", data={"_csrf": self._csrf(c), "product": "", "applied_on": day, "phi_days": "14", "field_id": fid})
        self.assertEqual(db.conn().execute("SELECT COUNT(*) FROM spray_log WHERE product=''").fetchone()[0], 0)
        CR.send_reminders()  # the /care page already sent it lazily
        self.assertEqual(db.conn().execute("SELECT reminded FROM spray_log WHERE product='TestProd'").fetchone()[0], 1)
        self.assertEqual(CR.send_reminders(), 0)  # idempotent
        self.assertTrue(db.conn().execute("SELECT 1 FROM notifications WHERE kind='spray'").fetchone())

    def test_spray_other_user_cannot_touch(self):
        c = A.app.test_client(); login(c, "farmer@kiza.rw")
        other = db.conn().execute("SELECT id FROM users WHERE role='farmer' AND email!='farmer@kiza.rw' LIMIT 1").fetchone()
        if not other: self.skipTest("no second farmer")
        con = db.conn(); con.execute("INSERT INTO spray_log(user_id,product,applied_on,planned) VALUES(?,?,?,0)", (other[0], "Theirs", str(dt.date.today()))); con.commit()
        sid = con.execute("SELECT id FROM spray_log WHERE product='Theirs'").fetchone()[0]
        c.post(f"/care/spray/{sid}/delete", data={"_csrf": self._csrf(c)})
        self.assertTrue(db.conn().execute("SELECT 1 FROM spray_log WHERE id=?", (sid,)).fetchone())

    def test_rain_reminder(self):
        con = db.conn(); d = con.execute("SELECT district FROM users WHERE email='farmer@kiza.rw'").fetchone()[0]
        con.execute("DELETE FROM weather WHERE district=? AND day=?", (d, str(dt.date.today())))
        con.execute("INSERT INTO weather(district,day,temp,rain_prob,rain_mm,wind,humidity,is_demo) VALUES(?,?,20,80,12,5,80,0)", (d, str(dt.date.today()))); con.commit()
        self.assertGreaterEqual(CR.send_rain_reminders(), 1); self.assertEqual(CR.send_rain_reminders(), 0)
        c = A.app.test_client(); login(c, "farmer@kiza.rw"); c.get("/lang/rw")
        self.assertIn("Imvura yaguye", c.get("/care").get_data(True))

    def test_history_page(self):
        for ident in ("farmer@kiza.rw", "buyer@kiza.rw", "gov@kiza.rw"):
            for lg in ("en", "rw", "fr"):
                c = A.app.test_client(); login(c, ident); c.get("/lang/" + lg)
                r = c.get("/history"); self.assertEqual(r.status_code, 200, (ident, lg)); self.assertIn("trade.gov", r.get_data(True))
        c = A.app.test_client(); login(c, "farmer@kiza.rw"); self.assertIn("class=\"tl\"", c.get("/history").get_data(True))
        self.assertNotEqual(A.app.test_client().get("/history").status_code, 200)

    def test_inputs_coach(self):
        from kiza8 import inputs as IN
        con = db.conn(); row = con.execute("SELECT f.id, f.size_ha FROM fields f JOIN farms fa ON fa.id=f.farm_id JOIN users u ON u.id=fa.user_id WHERE u.email='farmer@kiza.rw' LIMIT 1").fetchone()
        con.execute("UPDATE fields SET crop='Maize' WHERE id=?", (row[0],))
        yr = dt.date.today().year
        con.execute("INSERT INTO expenses(field_id,category,item,quantity,unit,unit_cost_rwf,total_rwf,spent_on) VALUES(?,?,?,?,?,?,?,?)", (row[0], "seed", "maize", row[1] * 25 * 3, "kg", 1000, row[1] * 25 * 3 * 1000, f"{yr}-01-15"))
        con.execute("INSERT INTO expenses(field_id,category,item,quantity,unit,unit_cost_rwf,total_rwf,spent_on) VALUES(?,?,?,?,?,?,?,?)", (row[0], "fertilizer", "dap", 1, "kg", 900, 900, f"{yr}-01-16")); con.commit()
        c = A.app.test_client(); login(c, "farmer@kiza.rw")
        with A.app.test_request_context():
            from flask import g; g.user = {"id": con.execute("SELECT id FROM users WHERE email='farmer@kiza.rw'").fetchone()[0]}
            a = [x for x in IN.analyse(g.user) if x["f"]["id"] == row[0]][0]
        self.assertEqual(a["seed"]["verdict"], "high"); self.assertGreater(a["seed"]["waste"], 0); self.assertEqual(a["fert"]["verdict"], "low")
        for lg in ("en", "rw", "fr"):
            c.get("/lang/" + lg); self.assertEqual(c.get("/inputs").status_code, 200)
        b = A.app.test_client(); login(b, "buyer@kiza.rw"); self.assertEqual(b.get("/inputs").status_code, 403)

    def test_day_window_rules(self):
        bad = CR.day_window({"day": str(dt.date.today()), "rain_mm": 20, "wind_kmh": 30, "temp_max": 25, "rain_prob": 90}, None, "en")
        self.assertEqual(bad["level"], "avoid")

    def test_badges_derived(self):
        c = A.app.test_client(); login(c, "farmer@kiza.rw")
        j = c.get("/api/v11/badges").get_json(); self.assertTrue(j)


if __name__ == "__main__":
    unittest.main()
