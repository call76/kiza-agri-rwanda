"""v10: assistant works for every account type, answers from SOURCED facts offline, uses Claude + web search when a key is set (mock server), /season page."""
import os, sys, json, re, threading, unittest, tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["KIZA_DB"] = tempfile.mktemp(suffix=".db"); os.environ["KIZA_AUTO_SYNC"] = "0"; os.environ["KIZA_JOBS"] = "0"
os.environ.pop("ANTHROPIC_API_KEY", None)
import db; db.init(force=True)
import app as A
from kiza8 import knowledge as K

class Mock(BaseHTTPRequestHandler):
    seen = {}
    def do_POST(self):
        Mock.seen = json.loads(self.rfile.read(int(self.headers["content-length"])))
        self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"content": [{"type": "text", "text": "OK from mock"}]}).encode())
    def log_message(self, *a): pass

def login(c, ident):
    t = c.get("/login"); csrf = re.search(r'name="_csrf" value="([^"]+)"', t.get_data(True)).group(1)
    return c.post("/login", data={"_csrf": csrf, "ident": ident, "password": db.DEMO_PASSWORD})

class T(unittest.TestCase):
    def ask(self, c, q): return c.post("/api/assistant", data={"q": q}).get_json()
    def test_offline_sourced_answers_for_everyone(self):
        for ident in (None, "farmer@kiza.rw", "buyer@kiza.rw", "advisor@kiza.rw", "gov@kiza.rw", "admin@kiza.rw"):
            c = A.app.test_client()
            if ident: self.assertEqual(login(c, ident).status_code, 302)
            r = self.ask(c, "Nkunganire urea price")
            self.assertIn("1,090", r["reply"]); self.assertFalse(r["ai"])
            self.assertIn("2027A", self.ask(c, "which season are we in?")["reply"])
    def test_kinyarwanda_autodetect_and_no_html_errors(self):
        c = A.app.test_client(); r = self.ask(c, "ibihembwe turimo?")
        self.assertIn("2027A", r["reply"]); self.assertIn("Turi", r["reply"])
        self.assertTrue(self.ask(c, "zzz qqq")["reply"])
    def test_ai_path_sends_user_context_and_web_search(self):
        srv = HTTPServer(("127.0.0.1", 0), Mock); threading.Thread(target=srv.serve_forever, daemon=True).start()
        from kiza8 import assistant as AS
        os.environ["ANTHROPIC_API_KEY"] = "k"; AS.API = f"http://127.0.0.1:{srv.server_port}/v1/messages"
        try:
            c = A.app.test_client(); login(c, "farmer@kiza.rw"); r = self.ask(c, "what should I do this week?")
            self.assertTrue(r["ai"]); self.assertEqual(r["reply"], "OK from mock")
            s = Mock.seen["system"]; self.assertIn("role=farmer", s); self.assertIn("FARMER DATA", s); self.assertIn("1980", s)
            self.assertEqual(Mock.seen["tools"][0]["type"], "web_search_20250305")
        finally: os.environ.pop("ANTHROPIC_API_KEY", None); srv.shutdown()
    def test_ai_failure_falls_back(self):
        from kiza8 import assistant as AS
        os.environ["ANTHROPIC_API_KEY"] = "k"; AS.API = "http://127.0.0.1:9/x"
        try: r = self.ask(A.app.test_client(), "Nkunganire urea price"); self.assertFalse(r["ai"]); self.assertIn("1,090", r["reply"])
        finally: os.environ.pop("ANTHROPIC_API_KEY", None)
    def test_season_page_and_today_api_all_languages(self):
        c = A.app.test_client()
        for lg in ("en", "rw", "fr"):
            c.get(f"/lang/{lg}"); p = c.get("/season"); self.assertEqual(p.status_code, 200); self.assertIn("2027A", p.get_data(True))
            j = c.get("/api/v10/today").get_json(); self.assertEqual(j["season"], "2027A")
    def test_facts_are_consistent(self):
        for r in K.SUBSIDY["rows"]:
            if r["retail"]: self.assertAlmostEqual(r["govt"] / r["retail"] * 100, r["pct"], delta=1)
    def test_widget_for_signed_in_user(self):
        c = A.app.test_client(); login(c, "farmer@kiza.rw"); self.assertIn('id="ka-fab"', c.get("/farmer").get_data(True))
if __name__ == "__main__": unittest.main()
