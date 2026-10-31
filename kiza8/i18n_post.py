"""Whole-page translation layer. Every HTML response is translated (text, titles, placeholders, aria labels, flash messages, crop names)
into the language chosen by the user, so the entire system switches language - not just the pages that have hand-written L() texts.
Dictionaries: kiza8/i18n/ui_rw.json, ui_fr.json  (English -> translation). Numbers are generalised: "Showing 5 of 30" matches "Showing {n} of {n}".
Missing strings stay in English and are recorded in MISSING (see scripts/find_untranslated.py)."""
import html, json, os, re
from functools import lru_cache

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "i18n")
_D = {}; MISSING = set()
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
TOKEN = re.compile(r"(<!--.*?-->|<script\b.*?</script>|<style\b.*?</style>|<textarea\b.*?</textarea>|<code\b.*?</code>|<pre\b.*?</pre>|<[^>]+>)", re.S | re.I)
ATTR = re.compile(r'\b(title|placeholder|aria-label|alt|data-ok|data-fail|data-err|data-hello|data-empty|data-confirm|label)="([^"]*)"')
LATIN = re.compile(r"[A-Za-z]{2,}")

def _load(lang):
    if lang not in _D:
        d = {}
        for f in ("ui_%s.json" % lang, "crops_%s.json" % lang):
            p = os.path.join(BASE, f)
            if os.path.exists(p): d.update(json.load(open(p, encoding="utf-8")))
        crops = json.load(open(os.path.join(BASE, "crops_%s.json" % lang), encoding="utf-8")) if os.path.exists(os.path.join(BASE, "crops_%s.json" % lang)) else {}
        pats = []
        pp = os.path.join(BASE, "patterns_%s.json" % lang)
        if os.path.exists(pp): pats = [(re.compile(a, re.S), b) for a, b in json.load(open(pp, encoding="utf-8"))]
        cr = re.compile(r"(?<![A-Za-z])(" + "|".join(re.escape(k) for k in sorted(crops, key=len, reverse=True)) + r")(?![A-Za-z])") if crops else None
        _D[lang] = (d, pats, cr, crops)
    return _D[lang]
def reload(): _D.clear(); tr.cache_clear()

def _fill(t, nums):
    it = iter(nums)
    return re.sub(r"\{n\}", lambda m: next(it, "{n}"), t)

def _lookup(core, d):
    if core in d: return d[core]
    key = NUM.sub("{n}", core)
    if key != core and key in d: return _fill(d[key], NUM.findall(core))
    return None

@lru_cache(maxsize=20000)
def tr(core, lang):
    """Translate one trimmed text. Returns None when nothing could be translated."""
    d, pats, cr, crops = _load(lang)
    r = _lookup(core, d)
    if r is not None: return r
    for rx, rep in pats:
        m = rx.match(core)
        if m: return rx.sub(rep, core)
    m = re.match(r"^([^\w\(\"“‘'#{]*)(.*?)([\s:.!?…→↗»]*)$", core, re.S)
    if m and (m.group(1) or m.group(3)) and m.group(2):
        r = tr(m.group(2), lang)
        if r is not None: return m.group(1) + r + m.group(3)
    parts = re.split(r"( · | — | – | \| | / )", core)
    if len(parts) > 1:
        out = [tr(p, lang) if i % 2 == 0 else p for i, p in enumerate(parts)]
        if any(o is not None for i, o in enumerate(out) if i % 2 == 0):
            return "".join((o if o is not None else parts[i]) for i, o in enumerate(out))
    if cr:
        s = cr.sub(lambda m: crops[m.group(1)], core)
        if s != core: return s
    return None

def text(s, lang):
    core = s.strip()
    if not core or not LATIN.search(core): return s
    lead = s[:len(s) - len(s.lstrip())]; trail = s[len(s.rstrip()):]
    r = tr(re.sub(r"\s+", " ", html.unescape(core)), lang)
    if r is None:
        MISSING.add(core); return s
    return lead + html.escape(r, quote=False) + trail

def _attrs(tag, lang):
    def f(m):
        v = html.unescape(m.group(2))
        if not LATIN.search(v): return m.group(0)
        r = tr(re.sub(r"\s+", " ", v.strip()), lang)
        if r is None: MISSING.add(v.strip()); return m.group(0)
        return '%s="%s"' % (m.group(1), html.escape(r, quote=True))
    return ATTR.sub(f, tag)

def translate_html(src, lang):
    if lang not in ("rw", "fr"): return src
    out = []; opt = None
    for part in TOKEN.split(src):
        if not part: continue
        if part[0] == "<":
            low = part[:9].lower()
            if low.startswith("<option") and "value=" not in part.lower():
                opt = len(out)             # needs value= pinned to its original English text
            elif part.startswith(("<!--", "<script", "<style", "<textarea", "<code", "<pre")): out.append(part); continue
            out.append(_attrs(part, lang) if part[1:2] not in ("/", "!") else part)
        else:
            if opt is not None and len(out) == opt + 1:
                orig = html.unescape(part.strip()); out[opt] = out[opt][:-1] + ' value="%s">' % html.escape(orig, quote=True); opt = None
            out.append(text(part, lang))
    return "".join(out)

def translate_response(r, lang):
    if lang not in ("rw", "fr") or r.direct_passthrough or r.mimetype != "text/html" or r.status_code >= 300: return
    r.set_data(translate_html(r.get_data(as_text=True), lang))
