# KIZA-AGRI Rwanda: Smart Agriculture for a Better Tomorrow

> **Live app:** https://kiza-agri-rwanda.onrender.com/  ·  **Code:** https://github.com/call76/kiza-agri-rwanda  ·  **Demo video:** `demo/demo.webm`
>
> **NISR 2026 Big Data Hackathon submission.** A Flask web app that gives Rwandan farmers one place for weather-aware spraying, seed and fertilizer checks, field care, market prices and farm history, with dashboards for buyers, extension officers and government.

## 1. What data it uses
| Data | Where | Status |
|---|---|---|
| Crops, districts, soil profiles, markets, prices, fertilizer rates, LUC zones, Imihigo targets | `data/templates/*.csv`, seeded by `db.py` | **Demo / sample values** (every table shows a DEMO tag). Replace with official data via `scripts/import_nisr.py` and `scripts/import_prices.py` |
| NISR Seasonal Agricultural Survey layout | `data/templates/nisr_sas_SAMPLE_SYNTHETIC.csv` | **Synthetic sample, not NISR data** (rows flagged `is_official=0`). See `data/NISR_README.md` for loading real figures with lineage and checksums |
| Live weather (hourly wind, rain chance, soil moisture, 7-day) | Open-Meteo API (no key), read in the browser | Live when the phone/PC is online; falls back to the stored forecast |
| data.gov.rw datasets | `kiza8/datagov.py` + Admin > data.gov.rw (needs your own API key in `KIZA_DATAGOV_KEY`) | Connector tested with mocked responses only |
| Fertilizer subsidy figures and Rwanda agriculture history | `kiza8/knowledge.py`, `kiza8/history.py` | Quoted from the cited public sources (New Times, KT Press, US Commercial Service) |

Data files are small and included in `data/`. Nothing here is presented as official unless it is flagged so.

## 2. What it communicates

### October 2026 visual update
- Added an original AI-generated Kiza Agri Rwanda hero image at `static/photos/hero.jpg` (wide 1672×941 JPEG). It fixes the previously missing `/static/photos/hero.jpg` asset used by the landing, welcome, and auth visual styles.
- The generated image is an illustrative promotional visual, not documentary evidence of a specific farmer, farm, or organization. Replace it with consented, verified project photography if you need documentary imagery.
- **Farm health score (0-100)** from soil pH, weather, season, land-use alignment, market and harvest timing.
- **When to spray**: best hours from wind, rain chance and temperature; planned sprays with reminders and pre-harvest safe dates (timing only, never doses).
- **Rain reminder**: after 5 mm or more of rain, the farmer is told to prepare the field.
- **Seed & fertilizer check** (`/inputs`): compares what the farmer recorded with the amount the field needs, says "too much / too little / about right", the RWF wasted, and common varieties.
- **History** (`/history`): Rwanda's agriculture timeline and the farmer's own farm story.
- **Find fertilizer (new, `/fertilizer#where`)**: a farmer who needs fertilizer sees at once which **cooperatives and agro-dealers in their district** sell it, whether it is **in stock / low / out**, whether the **Nkunganire subsidised price** is available, and which ones are in the farmer's own sector. After the cost calculator runs, the list also shows which of the needed fertilizers (DAP, Urea, NPK) each outlet is missing. Shortcut button **🧪 Find fertilizer** on the farmer dashboard. **Magic features on the same page:** (1) **✨ Magic plan** adds up the fertilizer for *all* the farmer's fields, shows the Nkunganire saving, picks the best in-stock outlet for each fertilizer (with a map link), gives a **rain-aware "apply now or wait" tip** from the forecast and shares the shopping list on **WhatsApp**; (2) **📍 Use my location** finds the nearest district by GPS (`/api/nearest-district`); JSON at `/api/fertilizer/outlets?district=Musanze&fert=DAP,Urea`. **The outlets shipped are DEMO samples (names end with "(sample)", tagged DEMO)**; the admin replaces them with the real register via **Admin > Data > fertilizer_outlets** (CSV/Excel; DEMO rows are rejected).
- **Food prices & magic basket (`/reference-prices`, public)**: 78 food items from Kigali markets (staples, meat/fish/dairy, vegetables, fruits, oils) in `data/reference_prices_kigali_2026.csv`. Tick what you need, enter the quantity, see the total at once and share the list on WhatsApp. Pumpkin (ibihaza) is set to 1,500 RWF/kg as confirmed by the team. **Indicative prices compiled from public reports (NISR/BNR news, Numbeo, Chamber of Commerce); not official NISR figures.**
- **Real photos from the internet** (people, community, markets, crops, soil, animals, wildlife, nature): loaded live from **Wikimedia Commons** (free licences, API `commons.wikimedia.org/w/api.php`, no key). Every photo shows its author and licence and links to its source page (`static/photos.js`). Needs internet; the page still works offline. Two small team-supplied soil/seedling images are in `static/photos/` (confirm their licence or replace them before publishing widely).
- **AI assistant** is for visitors who have not logged in (public pages). **Guest mode and the USSD simulator were removed** to keep the product focused.
- Market prices, profit simulator, planting calendar, crop-disease scanner, offers and deals, achievements, and government/extension dashboards.
- Kinyarwanda, English and French. Reference rates and varieties are **general guidance**: confirm with the sector agronomist or RAB.

## 3. How to interact (sample credentials)
Open the deployed link, then log in (password for all demo accounts: `Kiza@2026-demo`). There is no guest mode: use a real or demo account.

| Role | Login |
|---|---|
| Farmer | `farmer@kiza.rw` |
| Buyer | `buyer@kiza.rw` |
| Extension officer | `advisor@kiza.rw` |
| Government | `gov@kiza.rw` |
| Admin | `admin@kiza.rw` |

Suggested tour as farmer: Today > **Find fertilizer (`/fertilizer#where`)** > Spray (`/care`) > Seed & fertilizer (`/inputs`) > History (`/history`) > Profit > Calendar > Achievements. Use the language menu (EN/RW/FR).

## 4. Run on any machine
```bash
pip install -r requirements.txt
KIZA_DEMO=1 python app.py          # Windows PowerShell: $env:KIZA_DEMO=1; python app.py
# open http://127.0.0.1:5000
```
Without `KIZA_DEMO=1` the app starts in clean "real" mode (empty database, passwords printed once).

## 5. Deploy (free) on Render, as shown in the NISR webinar
1. Push this folder to a **public** GitHub repository.
2. Render > New > Blueprint > select the repo (`render.yaml` is included), or New Web Service with build `pip install -r requirements.txt` and start `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120`.
3. Open your `onrender.com` link in a private window shortly before the deadline so the free service is awake. The demo database is re-seeded automatically after every sleep.

## 6. Repository layout (hackathon checklist)
- `README.md` this file
- `app.py`, `db.py`, `kiza8/`, `templates/`, `static/` the application code
- `data/` the data used + `data/NISR_README.md`
- `demo/demo.webm` desktop screen recording (about 2 minutes, with on-screen captions) that follows the tour in section 3
- `requirements.txt`, `render.yaml`, `Procfile`
- `student_cards/student_cards.pdf` student cards of both team members (eligibility)
- `tests/` automated tests (`python -m unittest tests.test_v11`)

## 7. Team (CUR - Catholic University of Rwanda, FST, Computer Science)
| Member | Reg. No | Email | Phone |
|---|---|---|---|
| Rukundo Callixte | 1CUR25AK010978 | rukundocallixte1@gmail.com | +250 792 409 274 |
| Nshimiyimana Jean Damascene | 1CUR25AK011289 | dnshimiyimana252@gmail.com | +250 794 467 989 |

## 8. Submission checklist (NISR webinar)
- Public GitHub: https://github.com/call76/kiza-agri-rwanda · Deployed (Render): https://kiza-agri-rwanda.onrender.com/ (free tier sleeps: open it a minute before the check).
- Sample login for the deployed app: `farmer@kiza.rw` / `Kiza@2026-demo`.
- Files: README, code (`app.py` ...), `data/`, `demo/demo.webm`, `requirements.txt`, `student_cards/student_cards.pdf`.
- Submit at https://statistics.gov.rw/form/2026-hackathon-submission-form by **30 October 2026**.


---

# KIZA-AGRI v11 (this build) - Farmly-style look, new features, data.gov.rw

### v11 — spray planner, care timeline, achievements

- **/care – "Igihe cyo gutera umuti"**: best spray hours from live Open-Meteo (daylight, wind ≤12 km/h, no rain in the next 3 h, ≤28 °C) plus 3-day windows from stored forecasts. Dashboard card shows the next good window.
- **Plan a spray** with product, field and pre-harvest interval (PHI from the label). Reminders go out as in-app notification + SMS (respects consent) on the day before/of; the reminder re-checks the weather and suggests a better day. A warning appears if the planned harvest is before the safe-harvest date.
- **Care timeline** per field (crop-type schedules + weekly scouting) and **fungal disease pressure** from humidity/rain.
- **/badges**: 11 achievements derived only from real records (no fake progress), with confetti on first unlock.
- **Rain reminder**: when ≥5 mm of rain is recorded (yesterday/today) for the farmer's district, KIZA sends one notification + SMS per day: "Imvura yaguye — tegura umurima" (drain, loosen soil, weed, plant/top-dress, hold spraying until leaves dry). Also shown as a banner on /care; runs in the background job and when the farmer opens the app.
- **New logo** (farmer with hat working terraced hills under the sun, with a sprout) — `static/logo.svg`, app icons and every in-page logo.
- **/history (Amateka)**: Rwanda's agriculture timeline using only figures from the two cited sources (US Commercial Service, The New Times) plus a personal *My farm story* timeline built from the farmer's own records.
- Scene reacts to the clock and weather (night sky, rain). Optional browser notifications while the app is open.
- Guidance is general timing, **not doses** — always follow the product label and local extension advice.
**Run:** unchanged (`pip install -r requirements.txt`, then `START-KIZA-AGRI.bat` / `./start.sh`). The data.gov.rw key is in `.env` (`KIZA_DATAGOV_KEY`); keep that file private.
- **New look (from your Farmly video):** animated Rwandan-hills scene (sunrise, drifting clouds, terraces, drone), splash with growing seedling on `/welcome`, sheet-style **login** and a 3-step **register wizard** (role -> details -> password) with focus glow, shake on error, spinner button, password meter. Dashboard hero with **Farm health ring**, live weather card, count-up **Quick stats**, floating bottom bar with sliding indicator and a centre **+** (sell / scan / report / farms / profit / daily plan). Ripple, scroll reveal, confetti on success, command palette (**Ctrl+K** or `/`). Dark mode and reduced-motion supported.
- **Farm health score** (`/api/v11/health`): 0-100 from your own fields: soil pH vs crop range, 3-day weather risk, season fit, LUC match, price trend, harvest timing. Tap the ring for the breakdown.
- **Daily plan** (`/api/v11/plan`, ✨ button): prioritised actions with reasons (weather, offers waiting, harvest countdown, price movers, Nkunganire price).
- **Profit simulator** `/profit`: crop, land, yield, price and fertilizer sliders; real Nkunganire prices (subsidy vs open market), break-even price, ROI, profit per month. Yield/base cost are baseline estimates unless you upload RAB data.
- **Planting calendar** `/calendar`: plant/harvest windows per crop for seasons A/B/C, "plant now" first, price trend, harvest countdown rings for your fields.
- **Live farm** `/live`: browser fetches Open-Meteo directly (no key): current weather, **soil moisture**, 7-day forecast, spraying window, irrigation, frost/heat/UV advice. Works for each farm's GPS point, any district, or "my location". Needs internet on the *user's* device.
- **data.gov.rw connector** (`/admin/datagov`, `kiza8/datagov.py`): uses header `X-API-Key` and `GET {base}/assets/public/<dataset-id>/download?format=json`. Add dataset IDs, choose Market prices or Production, press Import (columns are recognised automatically, optional JSON mapping). Unknown districts/crops are skipped and counted. Runs with scheduled jobs (`KIZA_JOBS=1`). The key is read only from `.env`/environment and is shown masked.
  - **Check once:** the screenshot cut off the start of the API URL. Press **Test** on a dataset; on HTTP 404 copy the exact URL prefix from the dark box on data.gov.rw/api-access into "API base URL". Default guess: `https://data.gov.rw/api/v1`.
- Tests: `python tests/test_v11.py` (6 tests). The 28 failures in older test files were already there before v11 (identical list, none added).
- Not verifiable offline: real calls to data.gov.rw and Open-Meteo (tested with mock servers / fixtures). Kinyarwanda/French wording for new screens should be reviewed by a native speaker.

---
# KIZA-AGRI v10 (this build) - real AI assistant, real data, new look
**Run:** `pip install -r requirements.txt`, then (optional but recommended) set `ANTHROPIC_API_KEY=sk-ant-...`, then `START-KIZA-AGRI.bat` / `./start.sh`. First run creates a CLEAN real-mode database (no demo rows) and prints admin / government / officer passwords ONCE.
- **Assistant fixed for EVERYONE** (visitor, guest, farmer, buyer, advisor, government, admin): it was only shown to guests. Now: Claude AI **with live web search**, grounded on live weather, prices, soil, the user's OWN records and sourced facts; replies in Kinyarwanda / English / French (auto-detects Kinyarwanda). Chat memory, typing indicator, voice input, new-chat button. No key or no internet? It still answers from sourced facts and platform data (never an error).
- **Real, sourced data (`kiza8/knowledge.py`, 9 Oct 2026):** Nkunganire prices for 2027A (urea 1,980 retail / you pay 1,090; NPK 17-17-17 1,861 / 1,054; DAP 46% subsidy), Smart Nkunganire registration (*774), seasons A/B/C, Meteo Rwanda Sep-Dec 2026 rain outlook, 2027A season label. Each fact shows its source link on **/season**. Review each season.
- **New page `/season`** (public): farming calendar, rain outlook, subsidy table + "how much will I save" calculator, crop care tips, sources. **"Today" card** on farmer / buyer / advisor dashboards (weather advice, price movers, season, subsidy).
- **Real mode by default**; live market (WFP), weather (Open-Meteo) and soil (SoilGrids) sync as before when the server has internet.
- **New design layer** `static/v10.css`: gradients, depth, motion, dark-mode aware, reduced-motion safe.
- Tests: `python tests/test_v10.py` (7 new). Four older test files already had failures before v10 (they expect pages v9 removed for government and the guest-only simulator); v10 adds none.
- Not verifiable offline: live WFP/Open-Meteo/SoilGrids calls and the real Claude API (tested against a mock). DAP's retail price was not found in the sources.

---
# KIZA-AGRI v8

Start: `pip install -r requirements.txt && python db.py && python app.py` (http://127.0.0.1:5000). Dev logins (password `Kiza@2026-demo`): farmer@kiza.rw, buyer@kiza.rw, advisor@kiza.rw, officer@kiza.rw, gov@kiza.rw, admin@kiza.rw.
v8 adds: `kiza8/` package, see `docs/V8-STATUS.md` (what is tested / simulated / missing), `.env.example`, `scripts/import_prices.py`, `scripts/import_nisr.py`, `python -m kiza8.jobs` for scheduled jobs.
Admin console: /admin/ops. Public prices: /public/prices.

---

# KIZA-AGRI — Hackathon build
**Grow Smarter. Sell Better. Plan Together.** A farm-to-national-decision platform for Rwanda (NST2 aligned).

## Run (2 minutes)
1. Install Python 3.10+, then once: `pip install -r requirements.txt`
2. Windows: double-click **START-KIZA-AGRI.bat** · Mac/Linux: `./start.sh`
3. Open http://127.0.0.1:5000 (database is created and seeded automatically).

## Demo logins — password `Kiza@2026-demo`
You can sign in with **phone or email**.
| Role | Phone | Email |
|---|---|---|
| Farmer (Musanze / Muhoza) | 0788000001 | farmer@kiza.rw |
| Buyer | 0788000002 | buyer@kiza.rw |
| Extension officer | 0788000003 | officer@kiza.rw |
| Government | 0788000004 | gov@kiza.rw |
| Admin | 0788000005 | admin@kiza.rw |
| **Village advisor** (Musanze / Muhoza / *Demo Village*) | 0788000006 | advisor@kiza.rw |
Anyone can also register with a Rwandan phone number (email optional). Language choice (English / Kinyarwanda / Français) on the first screen and in the menu.

## The 7 core deliverables
1. **Digital Farm Passport** — farmer → farm → fields, linked to province / district / sector.
2. **Smart Crop Advisor + LUC guardrail** — explained crop score; a field whose crop is not the sector's Land Use Consolidation priority crop is blocked until the farmer confirms with the sector agronomist; every field stores its LUC status.
3. **Weather Smart Alerting** — forecast turned into plain farming instructions (live from Open-Meteo, or clearly-labelled DEMO).
4. **Smart Nkunganire Fertilizer Engine** — kg needed, cost at **open-market vs subsidized price**, and the saving.
5. **Distress Harvest Registry** — farmers report gluts / price manipulation / spoilage; officers triage (New → Reviewing → Resolved) and the farmer is notified.
6. **E-Soko Pricing Pipeline** — CSV **or Excel** price sheets are validated and loaded; district prices and a recent trend (14-day window for weekly data, previous reading for monthly data) are computed; Python service gives an experimental 2-week range.
7. **Imihigo Command Map** — Leaflet map of planted hectares vs district targets (colour-coded), plus government Command Center (LUC compliance, distress alerts, price movers).
Plus: marketplace with offers (phone shared only after acceptance), 8-attempt login throttle, CSRF, role-based access, audit log, notifications.

## v3 additions
- **Sell / buy with proof:** farmers list harvest with crop, kg, price, harvest date, village, sector, GPS (browser location), contact phone and a photo. Buyers browse cards (filter by crop, district, village, *verified only*) and send offers. Phone numbers are masked until an offer is accepted (staff and the owner see them in full).
- **Verification (`/verify`):** extension officers (their district) and government/admin (all) review each listing by village: photo, GPS map link, and an automatic plausibility check of claimed kg against the farmer's registered fields x typical yield. Decisions: Verified / Needs visit / Rejected (+ note); the farmer is notified; verified listings show a green badge and come first.
- **Crop scanner (`/scan`, all roles):** upload or take a leaf photo -> colour screening (green / yellow / brown share) + symptom checklist -> likely diseases with simple advice for Potato, Maize, Beans, Tomato, Cassava, Rice. Set `ANTHROPIC_API_KEY` (optional `KIZA_AI_MODEL`) to add real AI vision diagnosis. Guidance only, never a laboratory diagnosis.
- **Profile (`/profile`) for every role:** photo, name, phone, email, district, sector, village, bio, language, password. Public farmer page at `/u/<id>`.
- Uploads are validated, re-encoded as JPEG (max 1280 px) and stored in `uploads/` (set `KIZA_UPLOADS` to change). Requires `pillow`.
- Guest accounts are read-only for marketplace, offers and reports.

## v4 additions
- **109 crops (103 added).** Cereals, legumes, roots and tubers, vegetables, fruits, cash crops, herbs and spices, fodder (`crops_data.py`). Demo databases get all of them; a clean real-mode database gets them on the first price sync. **Every agronomy number is a BASELINE estimate, not RAB/NISR data**: replace by uploading `data/templates/crops_baseline.csv` (edited) on the Data page (updates by crop name). `cycle_days` now accepts up to 3650 (days to first harvest of trees). Prices page lists only crops that have price data; the advisor shows the best 25 and ranks perennials by profit per year; ties are broken by suitability then profit; the scanner gives general leaf-problem advice for crops without specific data; 20 fertilizer placeholders (DEMO) were added for the main crops.
- **USSD (feature phones, no internet).** `POST /ussd` speaks the Africa's Talking format (`sessionId`, `phoneNumber`, `text` -> `CON ...` / `END ...`). Menu: prices, weather, soil & fertilizer, what to plant, report a problem (registered farmers). Kinyarwanda first (9 = English), 0 = back, 00 = main menu; known phones skip the province/district questions. Replies are plain ASCII, <= 182 characters, stateless (no session table). **Try it now: Help → USSD** (`/ussd-sim`, a phone simulator; it never saves anything).
  - Set `KIZA_USSD_TOKEN=<secret>` and give the gateway the callback `https://YOUR-SERVER/ussd?token=<secret>` (or header `X-Kiza-Token`). Without a token the endpoint is read-only and farmer reports are switched off, because the phone number is the user's identity. `KIZA_USSD_CODE` only changes the example code shown in the simulator.
  - **To go live you still need:** a short code from a mobile operator (MTN / Airtel Rwanda; approval via the regulator), a USSD gateway account (e.g. Africa's Talking), and the app on a public HTTPS server. None of that can be built into the code. Test first with the gateway's own sandbox or a tunnel (ngrok).
- **Fixed:** the assistant matched crop names inside other words ("price" -> Rice, "photo" -> pH, "which" -> hi) - now whole words, longest crop name first (sweet potato beats potato), more Kinyarwanda crop names; crop upload limit for perennials; crop-ranking ties.

## v5 additions
- **Welcome + language (`/welcome`).** First visit shows "Welcome to KIZA-AGRI" with *Choose language / Hitamo ururimi / Choisissez la langue*; the whole system then continues in the chosen language (EN / RW / FR), which is also saved on the account and in the menu (🌐) and on the register / profile forms. French covers menus, login/register, marketplace, verification, profile and the landing hero; any text without a French entry falls back to English (add more in `i18n_fr.py`: `FR` for menu keys, `FRL` for page texts, `MSG` for messages). USSD stays Kinyarwanda/English.
- **Village agricultural advisor (umujyanama w'ubuhinzi).** One advisor per village (admin/government: **Admin → Village advisors**, `/admin/advisors`; the password is shown once). When a farmer lists a harvest, the advisor of that village is notified. On `/verify` the advisor sees only their village and must **go to the farm** and either
  - **Confirm** - requires ticking *"I was at the farm and saw the crop myself"*; may enter the quantity actually seen (listing is capped to it) and capture GPS as proof of the visit; or
  - **Reject** - requires a reason (crop not found / quantity far below / different crop / not ready / farmer unreachable / other + explanation). The farmer is notified with the reason; or
  - **Will visit** - tells the farmer to be at the farm.
- **Buyers see only confirmed harvests** (marketplace, farmer public pages) and cannot make offers on unconfirmed or rejected ones. No advisor in the village? The district officer (extension account without a village) handles it. Government/admin can verify anywhere.
- **Security fix:** staff can no longer change their own district/village in *Profile* (that would let an advisor widen their own scope); only admin assigns it.
- Existing databases upgrade automatically (new listing columns). Old district officers keep working unchanged.

## v6 additions
- **Deals + trust.** After the farmer accepts an offer, the **buyer confirms receipt and rates the farmer (1-5 stars + comment)** -> status *Completed*. Farmer public pages show completed deals, average rating, kg sold and the latest reviews; marketplace cards show the star rating. Only the buyer of an accepted offer can complete it, once.
- **Smarter marketplace.** Sort (newest / price low-high / price high-low / largest quantity), pagination (12 per page), **price vs national market average** badge on every card (from the E-Soko data), and a *"Confirmed on site by <advisor> on <date>"* line.
- **Harvest alerts (buyers).** Choose a crop (+ optional district); you are notified the moment an advisor confirms a matching harvest. Up to 10 alerts, removable.
- **Dashboards.** Farmer: live / waiting listings, kg sold, revenue, rating. Advisor / officer: waiting visits, confirmed kg, rejected, farmers in the area.
- **Exports (admin / government):** Admin -> Village advisors -> CSV of all listings, offers & deals, advisors. Excel-safe (UTF-8 BOM, formula-injection guard).
- **Professional design (`static/pro.css`, `pro.js`).** Cleaner cards and tables, active-menu highlight, toast-style messages (auto-close), double-submit protection, back-to-top, friendlier error pages, print-ready reports, **dark mode** (button in the top bar, remembers your choice and follows the phone setting by default).
- Demo data now includes confirmed, waiting and rejected listings and one completed, rated deal so every screen has content. Upgrading an old database is automatic (new columns + `watches` table).
- Tests: 51 (all pass); a crawl of 861 page requests (7 roles x 3 languages) gave no server errors.

## v7 additions
- **Assistant fixed for every account** (guest, farmer, buyer, advisor, government, admin) in Kinyarwanda, English and French. It no longer depends on a form token (an expired page could silently break it for signed-in users), never returns an HTML error to the chat, and signed-in users get answers about **their own data**: *my listings* (verified / waiting / rejected), *my offers*, *my fields*, *to verify* (advisors), *notifications*.
- **Fast:** page fade-in and reveal animations removed (that was the visible delay); SQLite now runs in WAL mode with a 20 s busy timeout (the background live-data sync can no longer block pages) and extra indexes; HTML is gzip-compressed; static files are cached and served instantly by a service worker.
- **Phone-first:** compact top bar, **bottom navigation** per role (+ "More" sheet with every menu item, contrast and text size), full-screen assistant sheet, no sideways scrolling (tables scroll inside their card), 16 px inputs (no zoom on iOS), safe-area support.
- **Installable app (PWA):** "Add to home screen" gives a full-screen KIZA icon (`/manifest.webmanifest`, `/sw.js`, offline page). Pages and personal data are never cached.
- **Admin -> Users:** search accounts, block / unblock, and give a **temporary password** to someone who forgot theirs (shown once).
- **Farmers can change the price** of an active listing; the Today dashboard no longer shows a duplicate card; Imihigo map no longer logs 404s when Leaflet is not bundled.
- Tests: 54 (all pass); browser crawl (phone size) of every main page for 4 roles: no JS errors, no 404, no horizontal scroll.

## Live data (market · weather · soil)
Needs internet. Runs automatically while the app is open (turn off with `KIZA_AUTO_SYNC=0`) and from **Data → Live data sync → Run now** (admin / government).
| Layer | Source | Refresh | What it does |
|---|---|---|---|
| Market prices | WFP "Rwanda - Food Prices" on HDX (the app finds the current CSV through the HDX API) | checked daily; **publisher updates monthly** | On a clean real-mode database with no crops it first adds 6 BASELINE crop estimates (flagged in the sync log; replace via Data → crops). Loads RWF/kg retail prices for the catalogue crops WFP reports (Maize, Beans, Potato, Sweet potato, Cassava, Rice, Sorghum ...) into markets + market prices, recomputes district trends, **replaces the DEMO prices** |
| Weather | Open-Meteo (free, no key) | every 3 h | 3-day forecast + 7-day rain per district, turned into farming advice |
| Soil | ISRIC SoilGrids 2.0 (modelled 250 m, topsoil 0-30 cm) at each district centroid | monthly (throttled, ~6 min) | pH, nitrogen, organic carbon, texture → likely limiting nutrient + suggested fertilizer |
| Soil (official) | RAB / NISR table uploaded on the Data page (`soil_profiles`) | when you upload | Official rows are **never overwritten** by SoilGrids |

**Fusion:** `/soil` and `GET /api/live/<district>` combine soil + weather + prices ("heavy rain tomorrow on acidic Musanze soil: do not spread fertilizer today; lime first"). A farm registered without a pH takes the district soil pH instead of a made-up number.
Every run is logged (Data page). A failed run keeps the previous data and the pages say how old it is. Prices are the **latest published** WFP prices, not a live tick; with monthly data the app shows a trend but not the 2-week ML forecast.
Soil from SoilGrids is a model estimate for screening, not a lab test. The 4 DEMO soil rows shipped for offline demos are labelled DEMO and are replaced by SoilGrids / official data.
No API keys are needed. Upgrading an old `kiza.db` is automatic (new tables are created on start).

## Real data (no demo)
Run **SETUP-REAL.bat** (clean DB: 30 districts + staff accounts; passwords shown once) → log in as admin → **Data** page → download each template, fill from official sources, upload (.csv/.xlsx). Order: crops → markets → market prices → fertilizer subsidies → LUC zones → Imihigo targets. Bad rows are rejected and listed. `DEMO DATA` labels vanish automatically.

## Removed as unnecessary (kept the product focused)
Digital-twin cards, "what-if" crop compare, ML yield card, harvest-record step, surplus/deficit & fertilizer-stock modules, Simple/Advanced toggle, enterprise-style extras.

## Honest status
- Built with **Flask + SQLite** (not Laravel/MySQL or FastAPI): the build environment had no PHP/Composer/internet. Schema is relational and maps 1:1 to MySQL; the Python service exposes a documented REST API and can be ported to FastAPI.
- **All seeded numbers are DEMO**: yields, prices, Nkunganire fertilizer prices, LUC priority crops, Imihigo targets, weather. They must be replaced with RAB / MINAGRI / NISR data; nothing here states real subsidy rates or legal rules.
- LUC guardrail asks for confirmation rather than refusing outright, because enforcement rules must come from your sector authorities.
- Leaflet map needs internet once (or copy Leaflet into `static/vendor/leaflet`); otherwise district tiles are shown. District points are approximate centroids, not boundaries.
- Kinyarwanda covers menus, login/register, dashboard and key screens; wording should be reviewed by a native speaker. Live provider calls (Open-Meteo, HDX, SoilGrids) could not be run in the build sandbox: parsers, loaders, fallbacks and scheduling are tested with realistic fake payloads - run **Data → Run now** once with internet to confirm each source.
- Tests: `python -m unittest discover tests` (48 tests, all offline: the 7 deliverables, security, real-data mode, live price / soil / weather layers, 109-crop catalogue, USSD, assistant fixes).

---
## v9 (this build)
- 5 roles, each with its own dashboard: Farmer `/farmer`, Buyer `/buyer`, Village advisor `/advisor/home`, Government `/gov`, Admin `/admin` (full control: users, advisors, marketplace, government data, data uploads, announcements, support, audit, settings).
- Government: poverty ranking of 30 districts (NISR EICV7 2023/24, pairing to confirm) + annual production rise/fall per district (`/gov/poverty`, `/gov/production`). Production history is a DEMO series until admin uploads official CSV (`/admin/govdata`).
- Assistant and USSD simulator are guest-only. Scanner/verify/data/users/help removed from Government.
- Bulk buying combines farmers of the same sector; farmers can mark "sold elsewhere", schedule future harvests, and opt in to instant auto-accept.
- Whole-system language switch (EN/RW/FR) incl. crop names: `kiza8/i18n_post.py` + `kiza8/i18n/ui_*.json`; untranslated text falls back to English.
- Header: logo, contrast, A-/A+ zoom, social icons, RAB/NISR/Meteo Rwanda/RISA links. Admin edits email/phone/social links in `/admin/settings` (defaults are placeholders).
