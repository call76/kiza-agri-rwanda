"""Crop-health helper: colour screening of a leaf photo + symptom-based candidate diseases.
GUIDANCE ONLY - not a laboratory or agronomist diagnosis. Advice is deliberately generic (no chemical doses)."""
import io
SYMPTOMS = {"spots": "Brown / dark spots on leaves", "yellow": "Yellowing leaves", "powder": "White powder or fuzzy mould", "holes": "Holes / chewed leaves",
            "wilt": "Wilting plant", "curl": "Curled, twisted or mosaic leaves", "streaks": "Stripes or streaks on leaves", "rot": "Rotting stem, root or fruit", "rust": "Orange / rust-coloured pustules"}
SYMPTOMS_RW = {"spots": "Utudomo tw'ikigina cyangwa umukara ku mababi", "yellow": "Amababi acyeye", "powder": "Ifu yera cyangwa ibumba ku mababi", "holes": "Amababi arimo imyobo", "wilt": "Igihingwa cyuhuye",
               "curl": "Amababi yizinze cyangwa afite ibara ritandukanye", "streaks": "Imirongo ku mababi", "rot": "Igiti, umuzi cyangwa imbuto byabora", "rust": "Utudomo tw'umuhondo-mwinshi / ingese"}
# crop -> [(disease, symptom set, plain advice, urgency)]
D = {
 "Potato": [("Late blight", {"spots", "rot", "powder"}, "Remove and destroy infected plants, avoid overhead watering, do not store affected tubers, rotate crops. Ask your extension officer which fungicide is approved.", "high"),
            ("Early blight", {"spots", "yellow"}, "Remove lower infected leaves, keep plants well fed and watered, rotate crops, avoid planting potato again in the same field next season.", "medium"),
            ("Bacterial wilt", {"wilt", "rot", "yellow"}, "Uproot and destroy wilted plants, do not move soil or water from that spot, rotate with a non-host crop such as maize. Report to your extension officer.", "high")],
 "Maize": [("Fall armyworm", {"holes"}, "Scout early in the whorl, hand-pick egg masses and larvae, report heavy infestation to your extension officer for approved control.", "high"),
           ("Leaf blight / grey leaf spot", {"spots", "streaks"}, "Rotate crops, bury crop residues, use tolerant varieties next season and ask your officer about approved treatment if severe.", "medium"),
           ("Maize streak virus", {"streaks", "yellow", "curl"}, "Remove infected plants early, control weeds, plant tolerant varieties and plant at the start of the rains.", "medium"),
           ("Common rust", {"rust", "spots"}, "Usually mild; monitor. Use resistant varieties next season.", "low")],
 "Beans": [("Angular leaf spot", {"spots", "yellow"}, "Use clean seed, rotate crops, avoid working in wet fields, remove crop residues.", "medium"),
           ("Bean rust", {"rust", "spots"}, "Remove badly infected leaves, avoid dense planting, use resistant varieties next season.", "medium"),
           ("Common bacterial blight", {"spots", "yellow", "wilt"}, "Use clean seed, rotate crops, avoid handling wet plants.", "medium"),
           ("Bean common mosaic virus", {"curl", "yellow", "streaks"}, "Remove infected plants, use certified seed, control aphids.", "medium")],
 "Tomato": [("Early blight", {"spots", "yellow"}, "Remove lower infected leaves, stake plants for airflow, mulch, rotate crops.", "medium"),
            ("Late blight", {"spots", "rot", "powder"}, "Remove and destroy infected plants, avoid wetting leaves, ask your officer about approved fungicide.", "high"),
            ("Bacterial wilt", {"wilt", "rot"}, "Uproot wilted plants, do not replant tomato/potato in that spot, rotate crops.", "high"),
            ("Leaf curl virus", {"curl", "yellow"}, "Remove infected plants, control whiteflies, use clean seedlings.", "medium")],
 "Cassava": [("Cassava mosaic disease", {"curl", "yellow"}, "Plant clean cuttings from healthy plants, uproot infected plants, use resistant varieties.", "high"),
             ("Cassava brown streak", {"yellow", "rot", "streaks"}, "Use clean cuttings, harvest early, report to your extension officer.", "high"),
             ("Cassava bacterial blight", {"spots", "wilt"}, "Use clean cuttings, avoid planting in wet soil, burn infected residues.", "medium")],
 "Rice": [("Rice blast", {"spots", "streaks"}, "Avoid excess nitrogen, drain and manage water, use resistant varieties and ask your officer about approved treatment.", "high"),
          ("Brown spot", {"spots"}, "Improve soil fertility (balanced fertilizer), use healthy seed.", "low"),
          ("Bacterial leaf blight", {"yellow", "wilt", "streaks"}, "Avoid excess nitrogen, drain fields, use clean seed and resistant varieties.", "high")]}

GENERIC = [("Fungal leaf spot", {"spots"}, "Remove badly spotted leaves, avoid watering the leaves, space plants for airflow, rotate crops and ask your extension officer about approved treatment if it spreads.", "medium"),
           ("Nutrient shortage or virus (yellowing)", {"yellow", "streaks", "curl"}, "Check soil fertility first (compost or balanced fertilizer). If new leaves curl or show mosaic, uproot those plants and use clean seed or cuttings next time.", "medium"),
           ("Wilt (bacterial or fungal)", {"wilt", "rot"}, "Uproot and destroy wilted plants, do not replant the same crop there, improve drainage and rotate with a cereal.", "high"),
           ("Powdery mildew", {"powder"}, "Improve airflow, avoid crowding and late-evening watering, remove affected leaves and ask your officer about approved treatment.", "low")]

def rank(crop, syms):
    out = []
    for name, ss, adv, urg in D.get(crop) or GENERIC:
        hit = ss & set(syms)
        if hit: out.append({"name": name, "match": round(100 * len(hit) / len(ss)), "hit": sorted(hit), "advice": adv, "urgency": urg})
    return sorted(out, key=lambda x: (-x["match"], x["name"]))[:3]

def colour_screen(jpeg_path):
    """Share of green / yellow / brown-dark pixels among plant-coloured pixels (HSV). Crude screening, not a diagnosis."""
    from PIL import Image
    import numpy as np
    im = Image.open(jpeg_path).convert("RGB"); im.thumbnail((240, 240)); hsv = np.asarray(im.convert("HSV")).astype(int); h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    plant = (s > 55) & (v > 35) & (h >= 8) & (h <= 125); n = int(plant.sum()); tot = h.size
    if n < 0.04 * tot: return {"leaf_pct": round(100 * n / tot), "usable": False}
    green = plant & (h >= 58); yellow = plant & (h >= 28) & (h < 58); brown = plant & (h < 28) | ((s > 40) & (v <= 70) & (h >= 8) & (h <= 125))
    g, y, b = (round(100 * int(x.sum()) / n) for x in (green, yellow, brown))
    return {"usable": True, "leaf_pct": round(100 * n / tot), "green": g, "yellow": y, "brown": b, "health": max(0, min(100, g - b // 2)),
            "infer": (["yellow"] if y >= 25 else []) + (["spots"] if b >= 15 else [])}

def ai_diagnose(jpeg_bytes, crop_hint=""):
    """Optional: real vision AI when ANTHROPIC_API_KEY is set (internet needed). Returns dict or None."""
    import os, json, base64, urllib.request
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key: return None
    prompt = ("You are an agronomy assistant for smallholder farmers in Rwanda. Look at this plant photo" + (f" (farmer says crop: {crop_hint})" if crop_hint else "") +
              ". Reply with ONLY JSON: {\"crop\": str, \"healthy\": bool, \"problem\": str, \"confidence\": \"low|medium|high\", \"symptoms\": [str], \"advice\": [str], \"urgency\": \"low|medium|high\"}. "
              "Give simple, safe, practical advice, no chemical doses; recommend confirming with a local extension officer. If the image is not a plant, set crop to \"unknown\".")
    body = json.dumps({"model": os.environ.get("KIZA_AI_MODEL", "claude-sonnet-5-5"), "max_tokens": 700, "messages": [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(jpeg_bytes).decode()}}, {"type": "text", "text": prompt}]}]}).encode()
    try:
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", body, {"content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
        txt = json.load(urllib.request.urlopen(req, timeout=45))["content"][0]["text"]; return json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
    except Exception: return None
