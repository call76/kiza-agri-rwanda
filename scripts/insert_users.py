"""Insert the 6 sample users (farmer, buyer, officer, government, admin, village advisor). Safe to re-run: existing accounts are skipped.
Usage: python scripts/insert_users.py            (password Kiza@2026-demo, or set KIZA_DEMO_PASSWORD)
Change these passwords before real use."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
from werkzeug.security import generate_password_hash
USERS = [("Demo Farmer","farmer@kiza.rw","0788000001","farmer","Musanze","Muhoza","","rw"),
         ("Demo Buyer","buyer@kiza.rw","0788000002","buyer","Kigali","","","rw"),
         ("District Officer","officer@kiza.rw","0788000003","extension","Gasabo","","","rw"),
         ("Government","gov@kiza.rw","0788000004","government","Gasabo","","","rw"),
         ("Admin","admin@kiza.rw","0788000005","admin","Gasabo","","","rw"),
         ("Village Advisor","advisor@kiza.rw","0788000006","extension","Musanze","Muhoza","Demo Village","rw")]
if not os.path.exists(db.DB): db.init_real()
c = db.conn(); db.add_cols(c)
pw = generate_password_hash(db.DEMO_PASSWORD); n = 0
for name, email, phone, role, dist, sec, vil, lang in USERS:
    if c.execute("SELECT 1 FROM users WHERE email=? OR phone=?", (email, phone)).fetchone():
        c.execute("UPDATE users SET pw_hash=? WHERE email=?", (pw, email)); print("reset password:", email); continue
    c.execute("INSERT INTO users(name,email,phone,pw_hash,role,district,sector,village,lang) VALUES(?,?,?,?,?,?,?,?,?)", (name, email, phone, pw, role, dist, sec, vil, lang)); n += 1; print("inserted:", role, email, phone)
c.commit(); c.close(); print(f"{n} inserted. Password: {db.DEMO_PASSWORD}")
