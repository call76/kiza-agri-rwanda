"""Yield estimation. Honest by construction:
 * training data = VERIFIED actual harvests only (harvest_records.verify_status='Verified') with field area
 * time-based split (train on earlier seasons, test on the latest) - no temporal leakage
 * model (per-crop ridge-free mean yield/ha adjusted by district effect) is compared with a baseline (global crop mean); it is only 'active' if it beats the baseline on held-out data
 * with too little data the status is 'insufficient_data' and predictions fall back to the crops-table reference yield, labelled as a reference value (not a model output)."""
import json, datetime as dt
import numpy as np
import db
from .core import ts

MIN_TRAIN, MIN_TEST = 8, 3
VERSION_PREFIX = "yield-v8-"

def dataset(c):
    return [dict(r) for r in c.execute("""SELECT h.id, h.season_year yr, h.season, f.crop, fa.district, h.actual_kg/f.size_ha kg_ha FROM harvest_records h JOIN fields f ON f.id=h.field_id JOIN farms fa ON fa.id=f.farm_id
        WHERE h.verify_status='Verified' AND h.actual_kg IS NOT NULL AND f.size_ha>0 ORDER BY h.season_year, h.season""").fetchall()]

def train(c=None):
    own = c is None; c = c or db.conn(); rows = dataset(c)
    years = sorted({r["yr"] for r in rows}); res = dict(status="insufficient_data", n_total=len(rows))
    if len(years) >= 2:
        test = [r for r in rows if r["yr"] == years[-1]]; tr = [r for r in rows if r["yr"] < years[-1]]       # strictly earlier -> later
        if len(tr) >= MIN_TRAIN and len(test) >= MIN_TEST:
            def fit(data):
                crop_m, dist_m = {}, {}
                for r in data: crop_m.setdefault(r["crop"], []).append(r["kg_ha"])
                cm = {k: float(np.mean(v)) for k, v in crop_m.items()}
                for r in data: dist_m.setdefault((r["crop"], r["district"]), []).append(r["kg_ha"] - cm[r["crop"]])
                dm = {k: float(np.mean(v)) * len(v) / (len(v) + 3) for k, v in dist_m.items()}      # shrink small district samples toward 0
                return cm, dm
            cm, dm = fit(tr); gm = float(np.mean([r["kg_ha"] for r in tr]))
            pred = lambda r: cm.get(r["crop"], gm) + dm.get((r["crop"], r["district"]), 0.0)
            base = lambda r: cm.get(r["crop"], gm)
            mae_m = float(np.mean([abs(pred(r) - r["kg_ha"]) for r in test])); mae_b = float(np.mean([abs(base(r) - r["kg_ha"]) for r in test]))
            resid = [r["kg_ha"] - pred(r) for r in tr]; sd = float(np.std(resid, ddof=1)) if len(resid) > 2 else None
            cm_all, dm_all = fit(rows); ver = VERSION_PREFIX + dt.date.today().strftime("%Y%m%d") + f"-n{len(rows)}"
            active = mae_m < mae_b
            c.execute("INSERT OR REPLACE INTO yield_models(version,trained_at,n_train,n_test,mae_model,mae_baseline,status,notes,params) VALUES(?,?,?,?,?,?,?,?,?)", (ver, ts(), len(tr), len(test), mae_m, mae_b, "active" if active else "not_better_than_baseline",
                "Held-out = latest season. Verified harvests only.", json.dumps(dict(crop=cm_all, district={f"{k[0]}|{k[1]}": v for k, v in dm_all.items()}, sd=sd, global_mean=float(np.mean([r['kg_ha'] for r in rows]))))))
            c.commit(); res = dict(n_total=len(rows), status="active" if active else "not_better_than_baseline", version=ver, mae_model=round(mae_m), mae_baseline=round(mae_b), n_train=len(tr), n_test=len(test))
    if own: c.close()
    return res

def active_model(c):
    r = c.execute("SELECT * FROM yield_models WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone(); return dict(r) if r else None

def predict(c, field_id, store=True):
    f = c.execute("SELECT f.id,f.crop,f.size_ha,fa.district FROM fields f JOIN farms fa ON fa.id=f.farm_id WHERE f.id=?", (field_id,)).fetchone()
    if not f or not f["crop"]: return None
    m = active_model(c); feats = dict(crop=f["crop"], district=f["district"], area_ha=f["size_ha"])
    if m:
        p = json.loads(m["params"]); base = p["crop"].get(f["crop"])
        if base is not None:
            kgha = base + p["district"].get(f"{f['crop']}|{f['district']}", 0.0); sd = p.get("sd") or 0.25 * kgha
            lo, hi = max(0, kgha - 1.28 * sd) * f["size_ha"], (kgha + 1.28 * sd) * f["size_ha"]; out = dict(model_version=m["version"], predicted_kg=round(kgha * f["size_ha"]), low_kg=round(lo), high_kg=round(hi), basis="model",
                limitations=f"Trained on {m['n_train']} verified harvests; held-out MAE {m['mae_model']:.0f} kg/ha vs baseline {m['mae_baseline']:.0f}. Uses crop and district only (no weather/soil features yet). Estimate, not guaranteed production.")
    else: out = None
    if out is None:
        cr = c.execute("SELECT yield_t_ha FROM crops WHERE name=?", (f["crop"],)).fetchone()
        if not cr or not cr[0]: return None
        kg = cr[0] * 1000 * f["size_ha"]; out = dict(model_version="reference-table", predicted_kg=round(kg), low_kg=round(kg * 0.6), high_kg=round(kg * 1.2), basis="reference_yield",
            limitations="No trained model is available (not enough verified harvest records). This is the reference yield from the crops table (DEMO values unless replaced by RAB/NISR figures), not a prediction. Range is indicative only.")
    if store: c.execute("INSERT INTO yield_predictions(field_id,crop,model_version,features,predicted_kg,low_kg,high_kg,basis) VALUES(?,?,?,?,?,?,?,?)", (field_id, f["crop"], out["model_version"], json.dumps(feats), out["predicted_kg"], out["low_kg"], out["high_kg"], out["basis"])); c.commit()
    return out

def monitor(c):
    """Fill actual_kg on stored predictions once a verified harvest exists; return MAE of model-based predictions that have actuals."""
    c.execute("""UPDATE yield_predictions SET actual_kg=(SELECT h.actual_kg FROM harvest_records h WHERE h.field_id=yield_predictions.field_id AND h.verify_status='Verified' ORDER BY h.season_year DESC LIMIT 1)
                 WHERE actual_kg IS NULL""")
    r = c.execute("SELECT AVG(ABS(predicted_kg-actual_kg)) m, COUNT(*) n FROM yield_predictions WHERE actual_kg IS NOT NULL AND basis='model'").fetchone(); c.commit()
    return dict(mae_kg=None if r["m"] is None else round(r["m"]), n=r["n"])
