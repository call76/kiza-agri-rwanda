"""KIZA-AGRI database layer: schema + DEMO seed (SQLite for the trial; relational, maps 1:1 to MySQL)."""
import sqlite3, os, random, datetime as dt
import crops_data
from werkzeug.security import generate_password_hash

DB = os.environ.get("KIZA_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "kiza.db"))
DEMO_PASSWORD = os.environ.get("KIZA_DEMO_PASSWORD", "Kiza@2026-demo")

def conn():
    c = sqlite3.connect(DB, timeout=20); c.row_factory = sqlite3.Row; c.execute("PRAGMA foreign_keys=ON")
    try: c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA synchronous=NORMAL"); c.execute("PRAGMA temp_store=MEMORY")   # readers never wait for the background sync writer
    except sqlite3.DatabaseError: pass
    return c

SCHEMA = """
CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, phone TEXT, pw_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('farmer','buyer','extension','government','admin')), district TEXT, sector TEXT, lang TEXT DEFAULT 'en',
  status TEXT DEFAULT 'active', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE districts(name TEXT PRIMARY KEY, province TEXT, lat REAL, lng REAL);
CREATE TABLE crops(name TEXT PRIMARY KEY, yield_t_ha REAL, price_kg REAL, cost_ha REAL, temp_min REAL, temp_max REAL,
  rain_min REAL, rain_max REAL, ph_min REAL, ph_max REAL, seasons TEXT, water_need TEXT, disease_risk REAL, cycle_days INTEGER);
CREATE TABLE farms(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), name TEXT NOT NULL,
  size_ha REAL NOT NULL CHECK(size_ha>0), lat REAL, lng REAL, district TEXT NOT NULL REFERENCES districts(name),
  sector TEXT, soil_type TEXT, soil_ph REAL, irrigation INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE fields(id INTEGER PRIMARY KEY, farm_id INTEGER NOT NULL REFERENCES farms(id), name TEXT NOT NULL,
  size_ha REAL NOT NULL CHECK(size_ha>0), crop TEXT REFERENCES crops(name), season TEXT, planting_date TEXT, expected_harvest TEXT,
  luc_status TEXT DEFAULT 'unknown', status TEXT DEFAULT 'Planned' CHECK(status IN ('Planned','Prepared','Planted','Growing','Flowering','Harvesting','Harvested','Failed')),
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE luc_zones(id INTEGER PRIMARY KEY, district TEXT REFERENCES districts(name), sector TEXT NOT NULL, mandated_crop TEXT REFERENCES crops(name), UNIQUE(district,sector));
CREATE TABLE imihigo_targets(id INTEGER PRIMARY KEY, district TEXT REFERENCES districts(name), crop TEXT REFERENCES crops(name), target_ha REAL CHECK(target_ha>0), UNIQUE(district,crop));
CREATE TABLE weather(id INTEGER PRIMARY KEY, district TEXT REFERENCES districts(name), day TEXT, temp REAL, rain_prob INTEGER,
  rain_mm REAL, rain_7d REAL, humidity INTEGER, wind REAL, is_demo INTEGER DEFAULT 1, fetched_at TEXT);
CREATE TABLE markets(id INTEGER PRIMARY KEY, name TEXT, district TEXT REFERENCES districts(name), lat REAL, lng REAL);
CREATE TABLE market_prices(id INTEGER PRIMARY KEY, market_id INTEGER REFERENCES markets(id), crop TEXT REFERENCES crops(name),
  day TEXT, price_kg REAL CHECK(price_kg>0), source TEXT, UNIQUE(market_id,crop,day));
CREATE TABLE esoko_prices(id INTEGER PRIMARY KEY, district TEXT, crop TEXT, current_price_rwf REAL, predicted_trend TEXT, change_pct REAL, as_of TEXT, UNIQUE(district,crop));
CREATE TABLE fertilizer_subsidies(id INTEGER PRIMARY KEY, crop TEXT REFERENCES crops(name), stage TEXT, fertilizer_type TEXT, kg_per_ha REAL,
  market_price_per_kg REAL, subsidized_price_per_kg REAL, source TEXT, approval TEXT DEFAULT 'pending', approved_by INTEGER REFERENCES users(id), effective_date TEXT);
CREATE TABLE listings(id INTEGER PRIMARY KEY, seller_id INTEGER REFERENCES users(id), crop TEXT REFERENCES crops(name), qty_kg REAL CHECK(qty_kg>0),
  available_kg REAL, price_kg REAL CHECK(price_kg>0), district TEXT, quality TEXT, status TEXT DEFAULT 'Available', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE offers(id INTEGER PRIMARY KEY, listing_id INTEGER REFERENCES listings(id), buyer_id INTEGER REFERENCES users(id),
  qty_kg REAL CHECK(qty_kg>0), price_kg REAL CHECK(price_kg>0), status TEXT DEFAULT 'Pending', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE distress_reports(id INTEGER PRIMARY KEY, farmer_id INTEGER REFERENCES users(id), district TEXT, crop TEXT, kind TEXT, qty_kg REAL,
  details TEXT, status TEXT DEFAULT 'New', officer_note TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE notifications(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), kind TEXT, message TEXT, link TEXT, is_read INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE audit_logs(id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT, detail TEXT, ip TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE data_quality_logs(id INTEGER PRIMARY KEY, source TEXT, row_no INTEGER, issue TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX ix_fields_farm ON fields(farm_id); CREATE INDEX ix_prices ON market_prices(crop,day); CREATE INDEX ix_listings ON listings(crop,status);
"""

MIGRATE = """
CREATE TABLE IF NOT EXISTS soil_profiles(district TEXT PRIMARY KEY REFERENCES districts(name), soil_type TEXT, ph_level REAL, nitrogen_g_kg REAL, organic_c_g_kg REAL,
  clay_pct REAL, sand_pct REAL, main_nutrient_deficit TEXT, recommended_fertilizer TEXT, source TEXT NOT NULL, is_demo INTEGER DEFAULT 0, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT, contact TEXT, topic TEXT, message TEXT, status TEXT DEFAULT 'New', ip TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS scans(id INTEGER PRIMARY KEY, user_id INTEGER, image TEXT, crop TEXT, mode TEXT, symptoms TEXT, result TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS watches(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), crop TEXT NOT NULL, district TEXT NOT NULL DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id,crop,district));
CREATE TABLE IF NOT EXISTS fertilizer_outlets(id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT DEFAULT 'Cooperative', district TEXT NOT NULL REFERENCES districts(name), sector TEXT,
  fertilizers TEXT, subsidized INTEGER DEFAULT 1, stock TEXT DEFAULT 'In stock', phone TEXT, hours TEXT, source TEXT NOT NULL DEFAULT 'DEMO sample', is_demo INTEGER DEFAULT 1, updated_at TEXT);
CREATE INDEX IF NOT EXISTS ix_fo_d ON fertilizer_outlets(district);
CREATE TABLE IF NOT EXISTS sync_log(id INTEGER PRIMARY KEY, kind TEXT, status TEXT, detail TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
"""
# DEMO soil rows (indicative, NOT verified) so the soil page works offline; replaced by SoilGrids / official RAB-NISR uploads
SOIL_DEMO = [("Musanze", "Volcanic loam", 5.8, "Potassium (K)", "NPK 17-17-17 + lime"), ("Bugesera", "Sandy clay", 6.5, "Phosphorus (P)", "DAP + compost"),
             ("Nyagatare", "Alluvial", 7.2, "Nitrogen (N)", "Urea"), ("Gasabo", "Lateritic", 5.2, "Phosphorus & Nitrogen", "NPK 15-15-15")]

CROPS = [  # DEMO agronomic estimates - replace with RAB/NISR validated values
 ("Maize",3.0,400,650000,18,30,15,60,5.5,7.0,"A,B","Medium",.30,120), ("Beans",1.2,800,500000,16,27,10,50,5.8,6.8,"A,B","Low",.35,90),
 ("Potato",15,350,1500000,10,22,20,60,5.0,6.5,"A,B,C","High",.50,100), ("Cassava",12,250,600000,20,32,10,60,5.0,7.0,"A,B","Low",.25,300),
 ("Rice",5,700,1100000,22,32,40,100,5.5,7.0,"A,B","High",.40,130), ("Tomato",25,450,2500000,18,28,15,50,6.0,6.8,"B,C","High",.55,100)]
# 30 districts, approximate centroids (lat,lng) - refine from NISR boundaries if needed
RW30 = [("Gasabo","Kigali",-1.89,30.13),("Kicukiro","Kigali",-1.99,30.10),("Nyarugenge","Kigali",-1.96,30.05),("Nyanza","Southern",-2.35,29.75),
 ("Gisagara","Southern",-2.60,29.85),("Nyaruguru","Southern",-2.72,29.52),("Huye","Southern",-2.60,29.74),("Nyamagabe","Southern",-2.47,29.42),
 ("Ruhango","Southern",-2.22,29.78),("Muhanga","Southern",-2.08,29.75),("Kamonyi","Southern",-2.00,29.90),("Karongi","Western",-2.10,29.38),
 ("Rutsiro","Western",-1.95,29.35),("Rubavu","Western",-1.68,29.35),("Nyabihu","Western",-1.67,29.50),("Ngororero","Western",-1.87,29.62),
 ("Rusizi","Western",-2.48,28.95),("Nyamasheke","Western",-2.32,29.10),("Rulindo","Northern",-1.75,29.97),("Gakenke","Northern",-1.70,29.78),
 ("Musanze","Northern",-1.50,29.63),("Burera","Northern",-1.45,29.85),("Gicumbi","Northern",-1.58,30.07),("Rwamagana","Eastern",-1.95,30.43),
 ("Nyagatare","Eastern",-1.30,30.33),("Gatsibo","Eastern",-1.60,30.40),("Kayonza","Eastern",-1.88,30.65),("Kirehe","Eastern",-2.25,30.70),
 ("Ngoma","Eastern",-2.15,30.50),("Bugesera","Eastern",-2.20,30.20)]
# Nkunganire: crop, stage, fertilizer, kg/ha, open-market RWF/kg, subsidized RWF/kg  (DEMO placeholders - pending approval)
FERT = [("Maize","planting","DAP",100,1100,750),("Maize","top_dressing","Urea",100,900,600),("Beans","planting","DAP",50,1100,750),
 ("Potato","planting","NPK 17-17-17",300,1000,700),("Potato","top_dressing","Urea",100,900,600),("Cassava","planting","NPK 17-17-17",100,1000,700),
 ("Rice","planting","DAP",100,1100,750),("Rice","top_dressing","Urea",100,900,600),("Tomato","planting","NPK 17-17-17",250,1000,700),("Tomato","top_dressing","Urea",100,900,600)]

COLS = {"offers": [("completed_at", "TEXT"), ("rating", "INTEGER"), ("review", "TEXT")], "users": [("photo", "TEXT"), ("village", "TEXT"), ("bio", "TEXT")],
 "listings": [("village", "TEXT"), ("sector", "TEXT"), ("lat", "REAL"), ("lng", "REAL"), ("contact", "TEXT"), ("photo", "TEXT"), ("harvest_date", "TEXT"), ("notes", "TEXT"),
  ("verify_status", "TEXT DEFAULT 'Pending'"), ("verified_by", "INTEGER"), ("verified_at", "TEXT"), ("verify_note", "TEXT"),
  ("visited", "INTEGER DEFAULT 0"), ("verified_qty", "REAL"), ("visit_lat", "REAL"), ("visit_lng", "REAL"), ("reject_reason", "TEXT")]}
def add_cols(c):
    """Add columns introduced after the first release (idempotent)."""
    for t, cols in COLS.items():
        have = {r[1] for r in c.execute(f"PRAGMA table_info({t})")}
        for n, ty in cols:
            if n not in have: c.execute(f"ALTER TABLE {t} ADD COLUMN {n} {ty}")

INDEXES = """CREATE INDEX IF NOT EXISTS ix_l_vs ON listings(verify_status,status); CREATE INDEX IF NOT EXISTS ix_l_seller ON listings(seller_id); CREATE INDEX IF NOT EXISTS ix_o_listing ON offers(listing_id);
CREATE INDEX IF NOT EXISTS ix_o_buyer ON offers(buyer_id); CREATE INDEX IF NOT EXISTS ix_n_user ON notifications(user_id,is_read); CREATE INDEX IF NOT EXISTS ix_f_status ON fields(status);
CREATE INDEX IF NOT EXISTS ix_u_role ON users(role,district); CREATE INDEX IF NOT EXISTS ix_w_d ON weather(district,day); CREATE INDEX IF NOT EXISTS ix_e_d ON esoko_prices(district,crop);"""

OUTLET_SEC = ["Central", "North", "South", "East", "West"]
def seed_outlets(c):
    """DEMO sample cooperatives / agro-dealers (2-3 per district). Clearly flagged is_demo=1; replace with real ones via Admin > Data > fertilizer_outlets."""
    rnd = random.Random(7); today = str(dt.date.today())
    for d in c.execute("SELECT name FROM districts").fetchall():
        n = d[0]
        rows = [(f"Koperative y'Abahinzi {n} (sample)", "Cooperative", "Central", "DAP, Urea, NPK 17-17-17", 1, rnd.choice(["In stock", "In stock", "Low"]), "Mon-Sat 8:00-17:00"),
                (f"{n} Agro-dealer Nkunganire (sample)", "Agro-dealer", "South", "DAP, Urea, NPK 17-17-17, NPK 22-6-12", 1, rnd.choice(["In stock", "Low", "Out of stock"]), "Mon-Sat 8:00-18:00"),
                (f"Koperative Twigire {n} (sample)", "Cooperative", "East", "NPK 17-17-17, Urea", 0, rnd.choice(["In stock", "Low"]), "Mon-Fri 8:00-16:00")]
        for i, (nm, k, sec, fz, sub, st, hrs) in enumerate(rows):
            if n == "Musanze" and i == 0: sec, st = "Muhoza", "In stock"
            c.execute("INSERT INTO fertilizer_outlets(name,kind,district,sector,fertilizers,subsidized,stock,phone,hours,source,is_demo,updated_at) VALUES(?,?,?,?,?,?,?,?,?,'DEMO sample - not a real outlet',1,?)", (nm, k, n, sec, fz, sub, st, "", hrs, today))

def migrate():
    """Create tables added after the first release (safe to run on an existing database)."""
    c = conn(); c.executescript(MIGRATE); add_cols(c); c.executescript(INDEXES); c.commit(); c.close()

def init(force=False):
    if os.path.exists(DB):
        if not force: migrate(); return
        os.remove(DB)
    import esoko
    c = conn(); c.executescript(SCHEMA); c.executescript(MIGRATE); add_cols(c); c.executescript(INDEXES)
    rnd = random.Random(2026); today = dt.date.today(); pw = generate_password_hash(DEMO_PASSWORD)
    c.executemany("INSERT INTO crops VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", CROPS + crops_data.EXTRA)
    for d in RW30: c.execute("INSERT INTO districts VALUES(?,?,?,?)", d)
    for s in SOIL_DEMO: c.execute("INSERT INTO soil_profiles(district,soil_type,ph_level,main_nutrient_deficit,recommended_fertilizer,source,is_demo,fetched_at) VALUES(?,?,?,?,?,'DEMO - indicative, not verified',1,?)", (*s, str(today)))
    for d in RW30:
        c.execute("INSERT INTO markets(name,district,lat,lng) VALUES(?,?,?,?)", (d[0] + " Market", d[0], d[2] + .01, d[3] + .01))
        for k in range(3):
            c.execute("INSERT INTO weather(district,day,temp,rain_prob,rain_mm,rain_7d,humidity,wind,is_demo,fetched_at) VALUES(?,?,?,?,?,?,?,?,1,?)",
              (d[0], str(today + dt.timedelta(k)), round(rnd.uniform(16, 25), 1), rnd.choice([15, 35, 60, 80]), round(rnd.uniform(0, 14), 1), round(rnd.uniform(18, 55), 1), rnd.randint(55, 90), round(rnd.uniform(6, 30), 1), str(today)))
    for m in c.execute("SELECT id FROM markets").fetchall():
        for cr in CROPS:
            base = cr[2] * (0.9 + rnd.random() * .25); trend = rnd.uniform(-.015, .025)
            for w in range(8, -1, -1):
                c.execute("INSERT INTO market_prices(market_id,crop,day,price_kg,source) VALUES(?,?,?,?,?)", (m["id"], cr[0], str(today - dt.timedelta(7 * w)), round(base * (1 + trend * (8 - w)) * (1 + rnd.uniform(-.03, .03))), "DEMO DATA"))
    for f in FERT + crops_data.FERT_EXTRA: c.execute("INSERT INTO fertilizer_subsidies(crop,stage,fertilizer_type,kg_per_ha,market_price_per_kg,subsidized_price_per_kg,source,approval,effective_date) VALUES(?,?,?,?,?,?,'DEMO placeholder - pending approval','pending',?)", (*f, str(today)))
    for n, e, r, d, ph in (("Uwase Marie","farmer@kiza.rw","farmer","Musanze","0788000001"),("Habimana Jean","buyer@kiza.rw","buyer","Gasabo","0788000002"),
            ("Mukamana Alice","officer@kiza.rw","extension","Musanze","0788000003"),("Nsengiyumva Paul","gov@kiza.rw","government","Gasabo","0788000004"),("System Admin","admin@kiza.rw","admin","Gasabo","0788000005")):
        c.execute("INSERT INTO users(name,email,phone,pw_hash,role,district,sector) VALUES(?,?,?,?,?,?,?)", (n, e, ph, pw, r, d, "Muhoza" if r == "farmer" else ""))
    c.execute("INSERT INTO users(name,email,phone,pw_hash,role,district,sector,village,lang) VALUES(?,?,?,?,'extension','Musanze','Muhoza','Demo Village','rw')", ("Village Advisor (demo)", "advisor@kiza.rw", "0788000006", pw))
    c.execute("UPDATE users SET village='Demo Village' WHERE email='farmer@kiza.rw'")
    cn = [x[0] for x in CROPS]; mand = {}
    for d in RW30:   # DEMO land-use-consolidation priority crop per demo sector + Imihigo targets
        mand[d[0]] = rnd.choice(cn[:4]); c.execute("INSERT INTO luc_zones(district,sector,mandated_crop) VALUES(?,?,?)", (d[0], "Demo Sector", mand[d[0]]))
        for cr in cn[:4]: c.execute("INSERT INTO imihigo_targets(district,crop,target_ha) VALUES(?,?,?)", (d[0], cr, rnd.randint(8, 30)))
    c.execute("INSERT INTO luc_zones(district,sector,mandated_crop) VALUES('Musanze','Muhoza','Maize')")
    for i, d in enumerate(RW30):
        for j in range(2):
            uid = c.execute("INSERT INTO users(name,email,phone,pw_hash,role,district,sector) VALUES(?,?,?,?,'farmer',?,?)", (f"Farmer {d[0]} {j+1}", f"demo.{d[0].lower()}{j}@kiza.rw", f"07881{i:02d}{j:03d}", pw, d[0], "Demo Sector")).lastrowid
            fid = c.execute("INSERT INTO farms(user_id,name,size_ha,lat,lng,district,sector,soil_type,soil_ph,irrigation) VALUES(?,?,?,?,?,?,?,?,?,?)", (uid, f"{d[0]} Farm {j+1}", 20, d[2], d[3], d[0], "Demo Sector", "Loam", round(rnd.uniform(5.4, 6.8), 1), rnd.randint(0, 1))).lastrowid
            for k in range(2):
                cr = rnd.choice(CROPS[:4]); c.execute("INSERT INTO fields(farm_id,name,size_ha,crop,season,planting_date,expected_harvest,luc_status,status) VALUES(?,?,?,?,?,?,?,?,?)",
                  (fid, f"Field {k+1}", round(rnd.uniform(3, 15), 1), cr[0], "A", str(today - dt.timedelta(30)), str(today + dt.timedelta(cr[13] - 30)), "aligned" if mand[d[0]] == cr[0] else "not_aligned", rnd.choice(["Planted", "Growing"])))
    fu = c.execute("SELECT id FROM users WHERE email='farmer@kiza.rw'").fetchone()[0]
    fid = c.execute("INSERT INTO farms(user_id,name,size_ha,lat,lng,district,sector,soil_type,soil_ph,irrigation) VALUES(?,?,?,?,?,?,?,?,?,?)", (fu, "Uwase Family Farm", 2.0, -1.50, 29.63, "Musanze", "Muhoza", "Volcanic loam", 6.0, 0)).lastrowid
    c.execute("INSERT INTO fields(farm_id,name,size_ha,crop,season,planting_date,expected_harvest,luc_status,status) VALUES(?,?,?,?,?,?,?,'not_aligned','Growing')", (fid, "North Plot", 0.8, "Potato", "A", str(today - dt.timedelta(35)), str(today + dt.timedelta(65))))
    c.execute("INSERT INTO distress_reports(farmer_id,district,crop,kind,qty_kg,details,status) VALUES(?,?,?,?,?,?,?)", (c.execute("SELECT id FROM users WHERE email='demo.rubavu0@kiza.rw'").fetchone()[0], "Rubavu", "Potato", "Glut / no buyers", 4000, "DEMO: prices dropped after a bumper harvest.", "New"))
    # DEMO marketplace: confirmed / waiting / rejected listings + one completed, rated deal so every screen has content
    adv = c.execute("SELECT id FROM users WHERE email='advisor@kiza.rw'").fetchone()[0]; bu = c.execute("SELECT id FROM users WHERE email='buyer@kiza.rw'").fetchone()[0]
    for cr, q, pr, st, note, rsn in (("Potato", 800, 330, "Verified", "DEMO: seen on site", None), ("Maize", 1200, 380, "Verified", "DEMO: seen on site", None), ("Beans", 300, 760, "Pending", None, None), ("Tomato", 200, 420, "Rejected", "DEMO", "Crop not found at the farm")):
        lid = c.execute("INSERT INTO listings(seller_id,crop,qty_kg,available_kg,price_kg,district,quality,village,sector,contact,harvest_date,notes,verify_status,verified_by,verified_at,verify_note,visited,reject_reason) VALUES(?,?,?,?,?,'Musanze','Good','Demo Village','Muhoza','0788000001',?,?,?,?,?,?,?,?)",
                        (fu, cr, q, q, pr, str(today - dt.timedelta(2)), "DEMO listing", st, None if st == "Pending" else adv, None if st == "Pending" else str(today), note, 1 if st == "Verified" else 0, rsn)).lastrowid
        if cr == "Maize": c.execute("INSERT INTO offers(listing_id,buyer_id,qty_kg,price_kg,status,completed_at,rating,review) VALUES(?,?,?,?,'Completed',?,5,'DEMO: honest farmer, good quality.')", (lid, bu, 400, 380, str(today - dt.timedelta(1)))); c.execute("UPDATE listings SET available_kg=800, status='Reserved' WHERE id=?", (lid,))
    c.execute("INSERT INTO notifications(user_id,kind,message,link) VALUES(?,?,?,?)", (fu, "system", "Welcome to KIZA-AGRI. Start with the Crop Advisor.", "/advisor"))
    seed_outlets(c); esoko.refresh(c); c.commit(); c.close()

def init_real(force=False):
    """Clean database for REAL use: schema + 30 districts + staff accounts with generated passwords. NO demo data."""
    import secrets
    if os.path.exists(DB):
        if not force: raise SystemExit(f"{DB} already exists. Re-run with --force to delete it and start clean.")
        os.remove(DB)
    c = conn(); c.executescript(SCHEMA); c.executescript(MIGRATE); add_cols(c); c.executescript(INDEXES)
    for d in RW30: c.execute("INSERT INTO districts VALUES(?,?,?,?)", d)
    out = []
    for role, email, ph in (("admin", os.environ.get("KIZA_ADMIN_EMAIL", "admin@kiza.rw"), "0788000005"), ("government", os.environ.get("KIZA_GOV_EMAIL", "gov@kiza.rw"), "0788000004"), ("extension", os.environ.get("KIZA_OFFICER_EMAIL", "officer@kiza.rw"), "0788000003")):
        pw = secrets.token_urlsafe(9)
        c.execute("INSERT INTO users(name,email,phone,pw_hash,role,district,sector) VALUES(?,?,?,?,?,?,?)", (role.title(), email, ph, generate_password_hash(pw), role, "Gasabo", "")); out.append((role, email, pw))
    c.commit(); c.close()
    print("Clean database created. SAVE THESE PASSWORDS NOW (shown once):")
    for r, e, p in out: print(f"  {r:11s} {e:24s} {p}")

if __name__ == "__main__":
    import sys
    if "--real" in sys.argv: init_real(force="--force" in sys.argv)
    else: init(force=True); print("Demo database created:", DB)
