"""Fertilizer finder: farmer sees outlets of own district, in-stock first, own sector flagged; loader rejects DEMO rows."""
import os, re, sys, tempfile, unittest
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, root)
os.environ["KIZA_DB"] = os.path.join(tempfile.mkdtemp(), "fo.db"); os.environ["KIZA_DEMO"] = "1"; os.environ["KIZA_ML_URL"] = "http://127.0.0.1:59999"
import db; db.init(force=True)
import app as A, loaders

class Outlets(unittest.TestCase):
    def setUp(self):
        self.c = A.app.test_client(); t = re.search(r'name="_csrf" value="(\w+)"', self.c.get("/login").data.decode()).group(1)
        self.assertEqual(self.c.post("/login", data={"ident": "farmer@kiza.rw", "password": "Kiza@2026-demo", "_csrf": t}).status_code, 302)
    def test_page_and_api(self):
        h = self.c.get("/fertilizer").data.decode(); self.assertIn("Where to buy fertilizer", h); self.assertIn("Musanze", h); self.assertIn("DEMO", h)
        o = self.c.get("/api/fertilizer/outlets?fert=DAP,Urea").json["outlets"]; self.assertTrue(o); self.assertTrue(all(x["district"] == "Musanze" for x in o))
        self.assertTrue(o[0]["near"] and o[0]["stock"] == "In stock")   # farmer's own sector, in stock, first
    def test_loader(self):
        with A.app.app_context():
            r = loaders.load("fertilizer_outlets", "name,kind,district,sector,fertilizers,subsidized,stock,phone,hours,source\nTest Coop,Cooperative,Huye,Tumba,DAP,1,In stock,,,RAB list\nBad,Cooperative,Huye,X,DAP,1,In stock,,,DEMO\n", None, A._c())
        self.assertEqual((r["ok"], r["bad"]), (1, 1))
if __name__ == "__main__": unittest.main()
