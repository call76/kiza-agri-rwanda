"""Versioned, idempotent, additive migrations for v8. Existing tables/rows are never dropped or rewritten destructively.
Each step is recorded in schema_version so it runs once. Reverse notes are in migrations/*.sql (down sections)."""
import db

STEPS = [
(1, "security: reset tokens, email verification, outbox", """
CREATE TABLE IF NOT EXISTS password_resets(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), token_hash TEXT UNIQUE NOT NULL, expires_at TEXT NOT NULL, used_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, ip TEXT);
CREATE TABLE IF NOT EXISTS email_verifications(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), email TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL, expires_at TEXT NOT NULL, used_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS email_outbox(id INTEGER PRIMARY KEY, to_addr TEXT NOT NULL, subject TEXT, body TEXT, status TEXT DEFAULT 'queued', provider TEXT, error TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, sent_at TEXT);
CREATE TABLE IF NOT EXISTS rate_events(id INTEGER PRIMARY KEY, bucket TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_rate ON rate_events(bucket, created_at);
"""),
(2, "farm records: expenses, harvest records", """
CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY, field_id INTEGER NOT NULL REFERENCES fields(id), category TEXT NOT NULL CHECK(category IN ('seed','fertilizer','pesticide','labor','transport','other')),
  item TEXT, quantity REAL CHECK(quantity IS NULL OR quantity>=0), unit TEXT, unit_cost_rwf REAL CHECK(unit_cost_rwf IS NULL OR unit_cost_rwf>=0), total_rwf REAL NOT NULL CHECK(total_rwf>=0), spent_on TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS harvest_records(id INTEGER PRIMARY KEY, field_id INTEGER NOT NULL REFERENCES fields(id), season_year INTEGER NOT NULL, season TEXT NOT NULL, crop TEXT,
  estimated_kg REAL CHECK(estimated_kg IS NULL OR estimated_kg>=0), actual_kg REAL CHECK(actual_kg IS NULL OR actual_kg>=0), sold_kg REAL DEFAULT 0, reserved_kg REAL DEFAULT 0, lost_kg REAL DEFAULT 0,
  verify_status TEXT DEFAULT 'Estimated' CHECK(verify_status IN ('Estimated','Submitted','Verified','Rejected')), verified_by INTEGER REFERENCES users(id), verified_at TEXT, verify_note TEXT,
  harvested_on TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(field_id, season_year, season));
CREATE INDEX IF NOT EXISTS ix_exp_field ON expenses(field_id, spent_on);
CREATE INDEX IF NOT EXISTS ix_hr_field ON harvest_records(field_id, season_year);
"""),
(3, "farm issue reporting with photos", """
CREATE TABLE IF NOT EXISTS issue_reports(id INTEGER PRIMARY KEY, farmer_id INTEGER NOT NULL REFERENCES users(id), farm_id INTEGER REFERENCES farms(id), field_id INTEGER REFERENCES fields(id),
  category TEXT NOT NULL, description TEXT NOT NULL, lang TEXT DEFAULT 'en', urgency TEXT DEFAULT 'normal' CHECK(urgency IN ('low','normal','high','critical')), lat REAL, lng REAL, observed_on TEXT,
  status TEXT DEFAULT 'Submitted' CHECK(status IN ('Submitted','Assigned','Under Review','Action Recommended','Resolved','Rejected','Info Requested')),
  advisor_id INTEGER REFERENCES users(id), recommendation TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS issue_attachments(id INTEGER PRIMARY KEY, issue_id INTEGER NOT NULL REFERENCES issue_reports(id), stored_name TEXT UNIQUE NOT NULL, bytes INTEGER, width INTEGER, height INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS issue_events(id INTEGER PRIMARY KEY, issue_id INTEGER NOT NULL REFERENCES issue_reports(id), actor_id INTEGER, from_status TEXT, to_status TEXT, note TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS ix_issue_status ON issue_reports(status, advisor_id);
CREATE INDEX IF NOT EXISTS ix_issue_farmer ON issue_reports(farmer_id);
"""),
(4, "marketplace: stock movements, offer lifecycle columns", """
CREATE TABLE IF NOT EXISTS stock_movements(id INTEGER PRIMARY KEY, listing_id INTEGER NOT NULL REFERENCES listings(id), offer_id INTEGER REFERENCES offers(id),
  kind TEXT NOT NULL CHECK(kind IN ('initial','reserve','release','sale','adjust')), qty_kg REAL NOT NULL, available_after REAL NOT NULL, reserved_after REAL NOT NULL, actor_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS ix_sm_listing ON stock_movements(listing_id, id);
"""),
(5, "price observations (source, unit, type, freshness)", """
CREATE TABLE IF NOT EXISTS price_observations(id INTEGER PRIMARY KEY, crop TEXT NOT NULL REFERENCES crops(name), district TEXT REFERENCES districts(name), market TEXT, price_type TEXT NOT NULL DEFAULT 'retail' CHECK(price_type IN ('retail','wholesale','farm_gate','other')),
  grade TEXT, unit TEXT NOT NULL DEFAULT 'kg', price_rwf REAL NOT NULL CHECK(price_rwf>0), observed_on TEXT NOT NULL, source TEXT NOT NULL, source_url TEXT, verified INTEGER DEFAULT 0, is_simulated INTEGER DEFAULT 0, imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(crop, district, market, price_type, unit, observed_on, source));
CREATE INDEX IF NOT EXISTS ix_po ON price_observations(crop, district, observed_on);
"""),
(6, "pipelines, sms, alerts, nisr, ml", """
CREATE TABLE IF NOT EXISTS pipeline_runs(id INTEGER PRIMARY KEY, run_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL, source TEXT, destination TEXT, started_at TEXT, finished_at TEXT, status TEXT, rows_extracted INTEGER DEFAULT 0, rows_inserted INTEGER DEFAULT 0,
  rows_updated INTEGER DEFAULT 0, rows_rejected INTEGER DEFAULT 0, validation TEXT, error TEXT, retry_count INTEGER DEFAULT 0, source_timestamp TEXT, code_version TEXT);
CREATE TABLE IF NOT EXISTS pipeline_rejects(id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, row_no INTEGER, reason TEXT, raw TEXT);
CREATE TABLE IF NOT EXISTS weather_alerts(id INTEGER PRIMARY KEY, district TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('heavy_rain','drought_risk','flood_risk')), severity TEXT NOT NULL CHECK(severity IN ('info','watch','warning')),
  window_start TEXT, window_end TEXT, source TEXT, is_simulated INTEGER DEFAULT 0, detail TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(district, kind, window_start));
CREATE TABLE IF NOT EXISTS sms_outbox(id INTEGER PRIMARY KEY, dedupe_key TEXT UNIQUE NOT NULL, user_id INTEGER REFERENCES users(id), phone TEXT NOT NULL, lang TEXT, body TEXT NOT NULL, kind TEXT,
  status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','submitted','delivered','failed','retry','blocked')), provider TEXT, provider_msg_id TEXT, attempts INTEGER DEFAULT 0, next_attempt_at TEXT, last_error TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT);
CREATE TABLE IF NOT EXISTS nisr_indicators(id INTEGER PRIMARY KEY, publication TEXT NOT NULL, year INTEGER NOT NULL, season TEXT, table_ref TEXT, indicator TEXT NOT NULL, geography TEXT NOT NULL, crop TEXT, unit TEXT NOT NULL, value REAL, source_url TEXT,
  is_official INTEGER NOT NULL DEFAULT 0, is_synthetic INTEGER NOT NULL DEFAULT 1, file_sha256 TEXT, imported_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(publication, year, season, indicator, geography, crop, unit));
CREATE TABLE IF NOT EXISTS yield_models(id INTEGER PRIMARY KEY, version TEXT UNIQUE NOT NULL, trained_at TEXT, n_train INTEGER, n_test INTEGER, mae_model REAL, mae_baseline REAL, status TEXT, notes TEXT, params TEXT);
CREATE TABLE IF NOT EXISTS yield_predictions(id INTEGER PRIMARY KEY, field_id INTEGER REFERENCES fields(id), crop TEXT, model_version TEXT NOT NULL, features TEXT, predicted_kg REAL, low_kg REAL, high_kg REAL, basis TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, actual_kg REAL);
"""),
(7, "users: sms consent, email verified", """
ALTER TABLE users ADD COLUMN sms_optin INTEGER DEFAULT 1;
ALTER TABLE users ADD COLUMN email_verified_at TEXT;
"""),
(8, "listings: reserved/sold counters", """
ALTER TABLE listings ADD COLUMN reserved_kg REAL DEFAULT 0;
ALTER TABLE listings ADD COLUMN sold_kg REAL DEFAULT 0;
"""),
(9, "v9: poverty index, production history, site settings, outside sales, auto-accept", """
CREATE TABLE IF NOT EXISTS poverty_index(district TEXT PRIMARY KEY REFERENCES districts(name), poverty_rate REAL NOT NULL CHECK(poverty_rate>=0 AND poverty_rate<=100), extreme_rate REAL, year TEXT, source TEXT NOT NULL, is_official INTEGER DEFAULT 0, note TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS production_history(id INTEGER PRIMARY KEY, district TEXT NOT NULL REFERENCES districts(name), year INTEGER NOT NULL, crop TEXT NOT NULL, tonnes REAL NOT NULL CHECK(tonnes>=0), source TEXT NOT NULL, is_demo INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(district,year,crop));
CREATE TABLE IF NOT EXISTS site_settings(k TEXT PRIMARY KEY, v TEXT);
ALTER TABLE listings ADD COLUMN sold_outside_kg REAL DEFAULT 0;
ALTER TABLE listings ADD COLUMN outside_note TEXT;
ALTER TABLE listings ADD COLUMN auto_accept INTEGER DEFAULT 0;
ALTER TABLE listings ADD COLUMN last_confirmed TEXT;
"""),
]

def migrate(conn=None):
    own = conn is None; c = conn or db.conn()
    c.execute("CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY, name TEXT, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    done = {r[0] for r in c.execute("SELECT version FROM schema_version")}
    for v, name, sql in STEPS:
        if v in done: continue
        for st in [s.strip() for s in sql.split(";\n") if s.strip()]:
            try: c.execute(st)
            except Exception as e:
                if "duplicate column" not in str(e).lower(): raise
        c.execute("INSERT INTO schema_version(version,name) VALUES(?,?)", (v, name))
    # backfill (idempotent): existing offers/listings -> reserved/sold counters and initial stock movements
    if 8 not in done:
        c.execute("UPDATE listings SET reserved_kg=COALESCE((SELECT SUM(qty_kg) FROM offers WHERE listing_id=listings.id AND status='Accepted'),0)")
        c.execute("UPDATE listings SET sold_kg=COALESCE((SELECT SUM(qty_kg) FROM offers WHERE listing_id=listings.id AND status='Completed'),0)")
    c.commit()
    if own: c.close()

if __name__ == "__main__":
    migrate(); print("v8 schema up to date")
