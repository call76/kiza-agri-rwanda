"""Farmer Learning Center (courses, quiz, certificate) + Satellite view (Esri World Imagery tiles)."""
import json, datetime as dt, secrets
from flask import Blueprint, render_template, request, redirect, flash, abort
import db
from .core import Q, Q1, X, me, need, notify, audit

bp = Blueprint("learn", __name__)

def migrate():
    c = db.conn()
    c.execute("CREATE TABLE IF NOT EXISTS course_progress(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), course_id TEXT NOT NULL, score INTEGER NOT NULL, passed INTEGER NOT NULL, attempts INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, course_id))")
    c.execute("""CREATE TABLE IF NOT EXISTS learning_questions(
        id INTEGER PRIMARY KEY, course_id TEXT NOT NULL, question_rw TEXT NOT NULL,
        options_json TEXT NOT NULL, answer_index INTEGER NOT NULL, explanation_rw TEXT DEFAULT '',
        source_name TEXT NOT NULL, source_url TEXT NOT NULL, verified INTEGER DEFAULT 0,
        created_by INTEGER REFERENCES users(id), created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        active INTEGER DEFAULT 1)""")
    c.execute("""CREATE TABLE IF NOT EXISTS course_certificates(
        id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
        course_id TEXT NOT NULL, certificate_no TEXT UNIQUE NOT NULL,
        score INTEGER NOT NULL, issued_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id,course_id))""")
    # Backfill certificates for learners who had already passed before certificates were added.
    for row in c.execute("SELECT user_id,course_id,score FROM course_progress WHERE passed=1").fetchall():
        exists = c.execute("SELECT 1 FROM course_certificates WHERE user_id=? AND course_id=?", (row[0], row[1])).fetchone()
        if not exists:
            number = "KIZA-" + dt.datetime.now().strftime("%Y%m") + "-" + secrets.token_hex(4).upper()
            c.execute("INSERT OR IGNORE INTO course_certificates(user_id,course_id,certificate_no,score) VALUES(?,?,?,?)",
                      (row[0], row[1], number, row[2]))
    c.commit(); c.close()

COURSES = [
 dict(id="ifumbire", en="Using fertilizer well", rw="Gukoresha ifumbire neza", video="https://www.youtube.com/embed/9lCfLvvFR7I",
  body="Ifumbire y'imborera ikomoka ku matungo n'ibisigazwa by'ibihingwa. Ifumbire mvaruganda (NPK, DAP, Urea) ishyirwa ukurikije isesengura ry'ubutaka. DAP ishyirwa mu gutera, Urea igashyirwa nyuma y'ibyumweru 4-6.",
  quiz=[("DAP ishyirwa ryari ku bigori?", ["Mu gutera", "Mu gusarura", "Nyuma y'amezi 3"], 0), ("Ifumbire y'imborera ikomoka kuki?", ["Plastique", "Amatungo n'ibisigazwa", "Umucanga"], 1), ("Urea ishyirwa nyuma y'igihe kingana iki?", ["Umunsi 1", "Ibyumweru 4-6", "Umwaka"], 1)]),
 dict(id="isuri", en="Fighting soil erosion", rw="Kurwanya isuri", video="https://www.youtube.com/embed/4iSFXcOQMbQ",
  body="Amaterasi y'indinganire, imirwanyasuri n'ibyatsi nka Napier birinda ubutaka gutwarwa n'amazi ku misozi. Ibiti bivangwa n'imyaka (agroforestry) bigabanya isuri bikongera n'umusaruro.",
  quiz=[("Ni iki kirinda isuri ku misozi?", ["Amaterasi", "Gutwika", "Kurandura ibyatsi"], 0), ("Ibyatsi bya Napier bifasha iki?", ["Gufata ubutaka", "Kongera isuri", "Nta na kimwe"], 0), ("Agroforestry ni iki?", ["Kuvanga ibiti n'imyaka", "Gutema amashyamba", "Korora inka gusa"], 0)]),
 dict(id="fall-armyworm", en="Fall armyworm in maize", rw="Nkongwa y'ibigori (Fall Armyworm)", video="https://www.youtube.com/embed/Nn6JcZ_Ji9Y",
  body="Nkongwa irya amababi y'ibigori igasiga imyobo n'imyanda. Genzura umurima kabiri mu cyumweru, kuramo amagi, koresha ivu cyangwa umucanga mu mutima w'igihingwa, kandi ukoreshe imiti yemewe na RAB iyo ikabije.",
  quiz=[("Ni kangahe ugenzura umurima mu cyumweru?", ["Rimwe mu kwezi", "Kabiri", "Nta na rimwe"], 1), ("Ni iki gishyirwa mu mutima w'ikigori?", ["Ivu", "Isukari", "Amazi"], 0), ("Imiti yemewe na nde?", ["RAB", "Umuturanyi", "Nta we"], 0)]),
]
PASS = 67
def _course(cid): return next((c for c in COURSES if c["id"] == cid), None)

@bp.get("/learning")
@need()
def learning():
    u = me(); prog = {r["course_id"]: r for r in Q("SELECT * FROM course_progress WHERE user_id=?", (u["id"],))}
    courses = [dict(c) for c in COURSES]
    for c in courses:
        extra = Q("SELECT id, question_rw, options_json, answer_index, explanation_rw, source_name, source_url FROM learning_questions WHERE course_id=? AND active=1 AND verified=1 ORDER BY id", (c["id"],))
        for q in extra:
            c["quiz"].append((q["question_rw"], json.loads(q["options_json"]), q["answer_index"]))
    certs = {r["course_id"]: r for r in Q("SELECT * FROM course_certificates WHERE user_id=?", (u["id"],))}
    return render_template("v11/learning.html", courses=courses, prog=prog, pass_mark=PASS, u=u, certs=certs)

@bp.post("/learning/<cid>/submit")
@need()
def learning_submit(cid):
    c = _course(cid)
    if not c: abort(404)
    # Keep quiz scoring in exactly the same order as the questions shown to learners,
    # including Admin-created questions that have been verified and activated.
    quiz = list(c["quiz"])
    extra = Q("SELECT question_rw, options_json, answer_index FROM learning_questions WHERE course_id=? AND active=1 AND verified=1 ORDER BY id", (cid,))
    for q in extra:
        quiz.append((q["question_rw"], json.loads(q["options_json"]), q["answer_index"]))
    u = me(); ok = 0
    for i, (_, _, a) in enumerate(quiz):
        if request.form.get(f"q{i}") == str(a): ok += 1
    score = round(ok / len(quiz) * 100); passed = int(score >= PASS)
    old = Q1("SELECT * FROM course_progress WHERE user_id=? AND course_id=?", (u["id"], cid))
    if old:   # a passed course stays passed; the best score is kept
        X("UPDATE course_progress SET score=?, passed=?, attempts=attempts+1, created_at=CURRENT_TIMESTAMP WHERE id=?", (max(score, old["score"]), max(passed, old["passed"]), old["id"]))
    else: X("INSERT INTO course_progress(user_id,course_id,score,passed) VALUES(?,?,?,?)", (u["id"], cid, score, passed))
    if passed:
        import secrets
        cert = Q1("SELECT * FROM course_certificates WHERE user_id=? AND course_id=?", (u["id"], cid))
        if not cert:
            number = "KIZA-" + dt.datetime.now().strftime("%Y%m") + "-" + secrets.token_hex(4).upper()
            X("INSERT INTO course_certificates(user_id,course_id,certificate_no,score) VALUES(?,?,?,?)", (u["id"], cid, number, score))
        notify(u["id"], "course", f"🎓 {c['rw']}: {score}%", "/learning")
    flash(("🎓 Watsinze! / You passed: " if passed else "Ongera usome usubiremo / Try again: ") + f"{score}%", "ok" if passed else "err")
    return redirect("/learning#" + cid)

@bp.get("/satellite")
@need()
def satellite():
    ds = Q("SELECT name, lat, lng FROM districts ORDER BY name"); u = me()
    return render_template("v11/satellite.html", ds=ds, start=(u.get("district") or "Musanze"))


@bp.route("/admin/learning/questions", methods=["GET", "POST"])
@need("admin")
def admin_learning_questions():
    if request.method == "POST":
        cid = (request.form.get("course_id") or "").strip()
        question = (request.form.get("question_rw") or "").strip()
        opts = [x.strip() for x in request.form.getlist("option") if x.strip()]
        source_name = (request.form.get("source_name") or "").strip()
        source_url = (request.form.get("source_url") or "").strip()
        try: answer = int(request.form.get("answer_index", "-1"))
        except ValueError: answer = -1
        if not _course(cid) or len(question) < 10 or len(opts) < 2 or answer < 0 or answer >= len(opts) or not source_name or not source_url.startswith(("https://", "http://")):
            flash("Uzuza ikibazo, ibisubizo nibura 2, igisubizo nyacyo n'inkomoko y'amakuru yizewe.", "err")
        else:
            X("INSERT INTO learning_questions(course_id,question_rw,options_json,answer_index,explanation_rw,source_name,source_url,verified,created_by) VALUES(?,?,?,?,?,?,?,?,?)",
              (cid, question, json.dumps(opts, ensure_ascii=False), answer, request.form.get("explanation_rw","").strip(), source_name, source_url, 0, me()["id"]))
            audit("learning_question_created", f"{cid}: {question[:100]}")
            flash("Ikibazo cyabitswe. Kigomba kubanza kugenzurwa mbere yo gushyirwa mu bizamini.", "ok")
        return redirect("/admin/learning/questions")
    rows = Q("SELECT q.*,u.name AS author FROM learning_questions q LEFT JOIN users u ON u.id=q.created_by ORDER BY q.id DESC")
    for r in rows: r["options"] = json.loads(r["options_json"])
    return render_template("v11/admin_learning_questions.html", courses=COURSES, questions=rows)

@bp.post("/admin/learning/questions/<int:qid>/verify")
@need("admin")
def verify_learning_question(qid):
    q = Q1("SELECT * FROM learning_questions WHERE id=?", (qid,))
    if not q: abort(404)
    verified = 0 if q["verified"] else 1
    X("UPDATE learning_questions SET verified=? WHERE id=?", (verified, qid))
    audit("learning_question_verification", f"{qid}: {verified}")
    flash("Ikibazo cyemejwe." if verified else "Icyemezo cyakuweho.", "ok")
    return redirect("/admin/learning/questions")

@bp.get("/learning/certificate/<int:cert_id>")
@need()
def learning_certificate(cert_id):
    u = me()
    cert = Q1("SELECT * FROM course_certificates WHERE id=? AND user_id=?", (cert_id, u["id"]))
    if not cert: abort(404)
    course = _course(cert["course_id"])
    if not course: abort(404)
    return render_template("v11/certificate.html", cert=cert, course=course, u=u)

@bp.get("/learning/verify/<certificate_no>")
def verify_learning_certificate(certificate_no):
    cert = Q1("SELECT c.*,u.name FROM course_certificates c JOIN users u ON u.id=c.user_id WHERE c.certificate_no=?", (certificate_no,))
    if not cert: abort(404)
    course = _course(cert["course_id"])
    return render_template("v11/certificate_verify.html", cert=cert, course=course)
