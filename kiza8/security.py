"""Account recovery + email verification + rate limiting + security headers.
Tokens: 32 random bytes (urlsafe); only SHA-256 hashes are stored; expiring; single use. Tokens/passwords are never logged or audited."""
import os, re, secrets, smtplib, logging
from email.message import EmailMessage
from flask import Blueprint, request, redirect, render_template, flash, session, g, abort
from werkzeug.security import generate_password_hash
import datetime as dt
from .core import Q, Q1, X, T, Tl, sha, ts, utcnow, audit, need, me

bp = Blueprint("security8", __name__)
RESET_TTL_MIN = int(os.environ.get("KIZA_RESET_TTL_MIN", "30"))
VERIFY_TTL_H = int(os.environ.get("KIZA_VERIFY_TTL_H", "48"))
log = logging.getLogger("kiza.security")

# ---------- email provider adapter ----------
def send_email(to, subject, body):
    """Queue in email_outbox, then deliver via SMTP if KIZA_SMTP_HOST is set; otherwise status 'logged' (dev/test: read it in /admin/ops).
    The outbox body may contain a one-time link: it is stored only for dev/test visibility; set KIZA_EMAIL_STORE_BODY=0 in production."""
    store = os.environ.get("KIZA_EMAIL_STORE_BODY", "1") != "0"
    eid = X("INSERT INTO email_outbox(to_addr,subject,body,status,provider) VALUES(?,?,?,?,?)", (to, subject, body if store else "(not stored)", "queued", "smtp" if os.environ.get("KIZA_SMTP_HOST") else "dev-log"))
    host = os.environ.get("KIZA_SMTP_HOST")
    if not host: X("UPDATE email_outbox SET status='logged' WHERE id=?", (eid,)); return "logged"
    try:
        m = EmailMessage(); m["From"] = os.environ.get("KIZA_MAIL_FROM", "no-reply@kiza-agri.rw"); m["To"] = to; m["Subject"] = subject; m.set_content(body)
        with smtplib.SMTP(host, int(os.environ.get("KIZA_SMTP_PORT", "587")), timeout=15) as s:
            if os.environ.get("KIZA_SMTP_TLS", "1") == "1": s.starttls()
            if os.environ.get("KIZA_SMTP_USER"): s.login(os.environ["KIZA_SMTP_USER"], os.environ.get("KIZA_SMTP_PASS", ""))
            s.send_message(m)
        X("UPDATE email_outbox SET status='sent', sent_at=? WHERE id=?", (ts(), eid)); return "sent"
    except Exception as e:
        X("UPDATE email_outbox SET status='failed', error=? WHERE id=?", (type(e).__name__, eid)); log.warning("email failed: %s", type(e).__name__); return "failed"

# ---------- DB-backed rate limiter (survives restarts, works across workers) ----------
def rate_ok(bucket, limit, per_sec):
    now = utcnow(); since = ts(now - dt.timedelta(seconds=per_sec))
    n = Q1("SELECT COUNT(*) c FROM rate_events WHERE bucket=? AND created_at>=?", (bucket, since))["c"]
    if n >= limit: return False
    X("INSERT INTO rate_events(bucket,created_at) VALUES(?,?)", (bucket, ts(now))); return True

def _captcha_ok():
    """Human verification: if KIZA_CAPTCHA_SECRET is configured, verify a Cloudflare Turnstile / hCaptcha-compatible token via KIZA_CAPTCHA_VERIFY_URL.
    Not configured -> skipped (dev). Rate limits still apply."""
    url, sec = os.environ.get("KIZA_CAPTCHA_VERIFY_URL"), os.environ.get("KIZA_CAPTCHA_SECRET")
    if not (url and sec): return True
    import urllib.request, urllib.parse, json
    try:
        data = urllib.parse.urlencode({"secret": sec, "response": request.form.get("cf-turnstile-response", request.form.get("h-captcha-response", ""))}).encode()
        return bool(json.load(urllib.request.urlopen(urllib.request.Request(url, data), timeout=8)).get("success"))
    except Exception: return False

def issue_reset_token(user_id, ip=None):
    tok = secrets.token_urlsafe(32)
    X("UPDATE password_resets SET used_at=? WHERE user_id=? AND used_at IS NULL", (ts(), user_id))      # invalidate older links
    X("INSERT INTO password_resets(user_id,token_hash,expires_at,ip) VALUES(?,?,?,?)", (user_id, sha(tok), ts(utcnow() + dt.timedelta(minutes=RESET_TTL_MIN)), ip))
    return tok

def _consume(tok, new_pw):
    h = sha(tok); cx = __import__("kiza8.core", fromlist=["_c"])._c()
    cur = cx.execute("UPDATE password_resets SET used_at=? WHERE token_hash=? AND used_at IS NULL AND expires_at>?", (ts(), h, ts()))
    if cur.rowcount != 1: cx.rollback(); return None
    uid = cx.execute("SELECT user_id FROM password_resets WHERE token_hash=?", (h,)).fetchone()[0]
    cx.execute("UPDATE users SET pw_hash=? WHERE id=?", (generate_password_hash(new_pw), uid)); cx.commit(); return uid

def pw_problem(pw):
    return None if (len(pw) >= 8 and re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw)) else "pw_weak"

@bp.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        if not _captcha_ok(): flash(T("sec.captcha_failed"), "err"); return render_template("v8/forgot.html")
        ident = request.form.get("ident", "").strip().lower(); ip = request.remote_addr or "?"
        if not (rate_ok("forgot-ip:" + ip, 10, 3600) and rate_ok("forgot-id:" + sha(ident)[:16], 3, 3600)): flash(T("sec.too_many"), "err"); return render_template("v8/forgot.html")
        u = Q1("SELECT * FROM users WHERE email=? AND email NOT LIKE '%@phone.kiza' AND email NOT LIKE '%@guest.kiza' AND status='active'", (ident,)) if "@" in ident else None
        if u:
            tok = issue_reset_token(u["id"], ip); link = request.host_url.rstrip("/") + "/reset/" + tok
            send_email(u["email"], Tl("sec.mail_reset_subject", u["lang"] or "en"), Tl("sec.mail_reset_body", u["lang"] or "en", link=link, minutes=RESET_TTL_MIN))
            audit("password.reset_requested", f"user {u['id']}", uid=u["id"])
        flash(T("sec.reset_sent"), "ok")          # identical message whether or not the account exists (no account enumeration)
    return render_template("v8/forgot.html")

@bp.route("/reset/<tok>", methods=["GET", "POST"])
def reset(tok):
    h = sha(tok); r = Q1("SELECT * FROM password_resets WHERE token_hash=?", (h,))
    valid = bool(r and not r["used_at"] and r["expires_at"] > ts())
    if request.method == "POST" and valid:
        pw = request.form.get("password", "")
        if pw != request.form.get("password2", ""): flash(T("sec.pw_mismatch"), "err")
        elif pw_problem(pw): flash(T("sec.pw_weak"), "err")
        else:
            uid = _consume(tok, pw)
            if uid: audit("password.reset_done", f"user {uid}", uid=uid); session.clear(); flash(T("sec.reset_done"), "ok"); return redirect("/login")
            valid = False
    return render_template("v8/reset.html", valid=valid)

@bp.post("/account/verify-email/send")
@need()
def send_verify():
    u = g.user
    if u["email"].endswith(("@phone.kiza", "@guest.kiza")): flash(T("sec.no_email"), "err"); return redirect("/profile")
    if not rate_ok(f"verify:{u['id']}", 3, 3600): flash(T("sec.too_many"), "err"); return redirect("/profile")
    tok = secrets.token_urlsafe(32)
    X("INSERT INTO email_verifications(user_id,email,token_hash,expires_at) VALUES(?,?,?,?)", (u["id"], u["email"], sha(tok), ts(utcnow() + dt.timedelta(hours=VERIFY_TTL_H))))
    send_email(u["email"], Tl("sec.mail_verify_subject", u["lang"] or "en"), Tl("sec.mail_verify_body", u["lang"] or "en", link=request.host_url.rstrip("/") + "/verify-email/" + tok, hours=VERIFY_TTL_H))
    flash(T("sec.verify_sent"), "ok"); return redirect("/profile")

@bp.get("/verify-email/<tok>")
def verify_email(tok):
    cx = __import__("kiza8.core", fromlist=["_c"])._c(); h = sha(tok)
    cur = cx.execute("UPDATE email_verifications SET used_at=? WHERE token_hash=? AND used_at IS NULL AND expires_at>?", (ts(), h, ts()))
    ok = cur.rowcount == 1
    if ok:
        uid = cx.execute("SELECT user_id FROM email_verifications WHERE token_hash=?", (h,)).fetchone()[0]
        cx.execute("UPDATE users SET email_verified_at=? WHERE id=?", (ts(), uid)); audit("email.verified", f"user {uid}", uid=uid)
    cx.commit(); flash(T("sec.verify_ok" if ok else "sec.verify_bad"), "ok" if ok else "err"); return redirect("/login")

def init(app):
    app.config.update(SESSION_COOKIE_SECURE=os.environ.get("KIZA_COOKIE_SECURE", "0") == "1", SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True,
                      PERMANENT_SESSION_LIFETIME=dt.timedelta(hours=int(os.environ.get("KIZA_SESSION_HOURS", "12"))))
    @app.after_request
    def headers(r):
        r.headers.setdefault("X-Frame-Options", "SAMEORIGIN"); r.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        r.headers.setdefault("Permissions-Policy", "camera=(self), geolocation=(self), microphone=()")
        if request.path.startswith(("/reset/", "/forgot", "/verify-email/")): r.headers["Cache-Control"] = "no-store"
        return r
