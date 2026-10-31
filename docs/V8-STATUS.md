# KIZA-AGRI v8 - status (honest)
Test commands (from the project folder):
  python -m unittest tests.test_v8 -v          # 44 new tests
  for t in test_flow test_ussd test_zfeatures test_live; do python tests/$t.py; done   # 50 v7 tests
Result when packaged: 44/44 + 50/50 passed (Python 3.12, Flask 3.1, SQLite). Not run: Docker build, real SMTP/SMS, browsers.

## Implemented AND tested
Transactional stock (reserve/release/sale, no overselling incl. concurrent test, audit rows) | buyer cancel / seller cancel | future-harvest hiding | multi-farmer matching (proposal only) |
farm expenses, harvest records, season economics (verified vs estimate, yield/ha, net margin not profit, YoY) | advisor harvest verify/reject with reason | general issue reports + secure photos (type/size check,
EXIF stripped, random names, private access-controlled) + status workflow + audit | forgot-password (hashed, expiring, single-use, rate-limited, no enumeration) | email verification | price observations (source/unit/type/
freshness, missing != 0) | baseline-first price forecast with rolling-origin validation and intervals | CSV price import + NISR import pipelines (idempotent, rejects, sha256, failure rollback/retry) |
weather alert rules + localized SMS queue (dedupe, opt-out, retry/backoff, delivered only from provider report) | yield model with time split vs baseline + labelled fallback | gov analytics (verified/reported/estimated kept apart) |
admin ops console | EN/RW catalog (288 keys) with parity/missing-key tests across all role pages.
## Implemented, NOT fully verified
SMTP and HTTP SMS adapters (no credentials/network here) | CAPTCHA hook (needs provider keys) | Docker files (not built here).
## Simulated / illustrative
All demo prices, weather, soil, crop reference values (flagged DEMO/simulated in UI). NISR file is SYNTHETIC layout sample, is_official=0.
## Not done (unavailable or out of scope in this round)
Full split of app.py into app/ package (v7 routes kept; v8 is an additive kiza8/ package) | translation of ALL legacy v7 pages to the new catalog (v7 pages keep their EN/RW/FR inline texts; v8 pages are EN/RW only, FR falls back to EN) |
Real e-Soko/NISR figures (no network; adapter + templates ready) | CNN disease model (no trained weights - existing disease.py rules stay) | Leaflet boundary heatmaps (no verified boundary dataset) |
USSD extensions for new modules | weather-forecast ingestion beyond existing weather table | login throttling is the v7 per-IP limiter (reset/verify use DB rate limits) | Kinyarwanda needs native-speaker review.
