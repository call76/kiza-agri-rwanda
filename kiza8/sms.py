"""SMS: provider adapter + outbox with dedupe, consent, retries. 'delivered' is only ever set from a provider delivery report - never assumed."""
import os, logging, datetime as dt, uuid
import db
from .core import ts, utcnow, Tl

log = logging.getLogger("kiza.sms")
MAX_ATTEMPTS = 4

class Provider:
    name = "base"
    def send(self, phone, body):        # -> provider message id; raise TemporaryError / PermanentError
        raise NotImplementedError
class TemporaryError(Exception): pass
class PermanentError(Exception): pass

class MockProvider(Provider):
    """Test/dev provider. Records messages in memory; failures can be scripted. Delivery reports are simulated through confirm()."""
    name = "mock"; sent = []; fail_next = 0; permanent = set()
    def send(self, phone, body):
        if phone in self.permanent: raise PermanentError("invalid number")
        if MockProvider.fail_next > 0: MockProvider.fail_next -= 1; raise TemporaryError("provider 503")
        mid = "mock-" + uuid.uuid4().hex[:10]; MockProvider.sent.append((mid, phone, body)); return mid

class HttpProvider(Provider):
    """Generic JSON-over-HTTPS gateway (e.g. Africa's Talking-style). Needs KIZA_SMS_URL + KIZA_SMS_KEY. Not exercised in tests (no network/credentials)."""
    name = "http"
    def send(self, phone, body):
        import urllib.request, json
        req = urllib.request.Request(os.environ["KIZA_SMS_URL"], json.dumps({"to": phone, "message": body}).encode(), {"Content-Type": "application/json", "Authorization": "Bearer " + os.environ.get("KIZA_SMS_KEY", "")})
        try: r = json.load(urllib.request.urlopen(req, timeout=15)); return str(r["id"])
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500 and e.code != 429: raise PermanentError(str(e.code))
            raise TemporaryError(str(e.code))
        except Exception as e: raise TemporaryError(type(e).__name__)

def provider():
    return HttpProvider() if (os.environ.get("KIZA_SMS_PROVIDER") == "http" and os.environ.get("KIZA_SMS_URL")) else MockProvider()

def queue(c, user, key, body, kind):
    """Idempotent: same dedupe_key -> nothing new. Respects consent (sms_optin) and requires a phone."""
    if not user["phone"]: return None
    st = "queued" if user["sms_optin"] else "blocked"
    cur = c.execute("INSERT OR IGNORE INTO sms_outbox(dedupe_key,user_id,phone,lang,body,kind,status,provider,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (key, user["id"], user["phone"], user["lang"] or "en", body, kind, st, provider().name, ts()))
    return cur.lastrowid if cur.rowcount else None

def dispatch(limit=200, prov=None):
    """Send queued/retry messages whose time has come. Temporary failures back off (5, 15, 45 min...) up to MAX_ATTEMPTS; permanent -> failed."""
    prov = prov or provider(); c = db.conn(); n = dict(submitted=0, retry=0, failed=0)
    try:
        for m in c.execute("SELECT * FROM sms_outbox WHERE status IN ('queued','retry') AND (next_attempt_at IS NULL OR next_attempt_at<=?) ORDER BY id LIMIT ?", (ts(), limit)).fetchall():
            got = c.execute("UPDATE sms_outbox SET status='submitted', attempts=attempts+1, updated_at=? WHERE id=? AND status IN ('queued','retry')", (ts(), m["id"]))   # claim (no double send across workers)
            if got.rowcount != 1: continue
            try:
                mid = prov.send(m["phone"], m["body"]); c.execute("UPDATE sms_outbox SET provider_msg_id=?, provider=?, last_error=NULL WHERE id=?", (mid, prov.name, m["id"])); n["submitted"] += 1   # 'submitted' = accepted by provider, NOT delivered
            except TemporaryError as e:
                att = m["attempts"] + 1
                if att >= MAX_ATTEMPTS: c.execute("UPDATE sms_outbox SET status='failed', last_error=? WHERE id=?", (str(e), m["id"])); n["failed"] += 1
                else: c.execute("UPDATE sms_outbox SET status='retry', last_error=?, next_attempt_at=? WHERE id=?", (str(e), ts(utcnow() + dt.timedelta(minutes=5 * 3 ** (att - 1))), m["id"])); n["retry"] += 1
            except PermanentError as e: c.execute("UPDATE sms_outbox SET status='failed', last_error=? WHERE id=?", (str(e), m["id"])); n["failed"] += 1
            c.commit()
    finally: c.close()
    return n

def delivery_report(provider_msg_id, delivered):
    """Webhook/provider callback: the ONLY place a message becomes 'delivered' (or failed)."""
    c = db.conn(); cur = c.execute("UPDATE sms_outbox SET status=?, updated_at=? WHERE provider_msg_id=? AND status='submitted'", ("delivered" if delivered else "failed", ts(), provider_msg_id)); c.commit(); c.close(); return cur.rowcount == 1
