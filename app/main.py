"""The web server. Run it with:  uvicorn app.main:app --reload
It serves:
  - a JSON API under /api/...  (used by the dashboard page)
  - the dashboard page itself at /  (static/index.html, a single-page app)
"""
import json
import time
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, db as dbmod, security
from .agents.controller import Controller

app = FastAPI(title="Explainable Multi-Agent AI - Police Case Intelligence Platform")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

controller = Controller()

ROLE_ALL = {"Investigating Officer", "Case Records Clerk", "Police Commander", "System Administrator"}
ROLE_COMMANDER = {"Police Commander", "System Administrator"}
ROLE_CLERK_PLUS = {"Case Records Clerk", "Investigating Officer", "Police Commander", "System Administrator"}


# --------------------------------------------------------------------------- auth
def get_user(authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "").strip()
    uid = security.read_token(token) if token else None
    if not uid:
        raise HTTPException(status_code=401, detail="Please log in again.")
    with dbmod.connect() as db:
        user = db.one("SELECT id, username, full_name, role, station_id FROM users WHERE id=%s AND is_active=1", [uid])
    if not user:
        raise HTTPException(status_code=401, detail="Please log in again.")
    return user


def require_role(user, allowed):
    if user["role"] not in allowed:
        raise HTTPException(status_code=403, detail="Your role ({}) cannot do this.".format(user["role"]))


class LoginBody(BaseModel):
    username: str
    password: str


@app.post("/api/login")
def login(body: LoginBody):
    with dbmod.connect() as db:
        user = db.one("SELECT * FROM users WHERE username=%s AND is_active=1", [body.username.strip()])
        if not user or not security.verify_password(body.password, user["password_hash"], user["salt"]):
            controller.log(db, None, "login_failed", detail=body.username)
            raise HTTPException(status_code=401, detail="Wrong username or password.")
        token = security.make_token(user["id"])
        controller.log(db, user, "login_success")
    return {"token": token, "user": {"id": user["id"], "username": user["username"],
                                     "full_name": user["full_name"], "role": user["role"]}}


# --------------------------------------------------------------------------- dashboard
@app.get("/api/dashboard")
def dashboard(user=Depends(get_user)):
    with dbmod.connect() as db:
        return controller.dashboard_stats(db)


# --------------------------------------------------------------------------- cases
class CaseBody(BaseModel):
    title: str
    offence_type: str
    priority: int
    station_id: int
    location: str = ""
    reported_date: str
    narrative: str


@app.get("/api/cases")
def list_cases(status: str = "", q: str = "", user=Depends(get_user)):
    sql = "SELECT id, case_number, title, offence_type, status, priority, station_id, reported_date FROM cases WHERE 1=1"
    params = []
    if status:
        sql += " AND status=%s"; params.append(status)
    if q:
        sql += " AND (title ILIKE %s OR case_number ILIKE %s OR narrative ILIKE %s)" if False else \
               " AND (title LIKE %s OR case_number LIKE %s OR narrative LIKE %s)"
        like = "%" + q + "%"
        params += [like, like, like]
    sql += " ORDER BY reported_date DESC, id DESC LIMIT 200"
    with dbmod.connect() as db:
        return db.q(sql, params)


@app.post("/api/cases")
def create_case(body: CaseBody, user=Depends(get_user)):
    require_role(user, ROLE_CLERK_PLUS)
    with dbmod.connect() as db:
        n = db.one("SELECT COUNT(*) AS n FROM cases")["n"] + 1
        year = body.reported_date[:4] if body.reported_date else time.strftime("%Y")
        case_number = "SLP-{}-{:05d}".format(year, n)
        fields = body.dict()
        fields["case_number"] = case_number
        fields["status"] = "Open"
        case_id, result = controller.new_case(db, user, fields)
    return {"case_id": case_id, "case_number": case_number, **result}


@app.get("/api/cases/{case_id}")
def get_case(case_id: int, user=Depends(get_user)):
    with dbmod.connect() as db:
        case = db.one("SELECT * FROM cases WHERE id=%s", [case_id])
        if not case:
            raise HTTPException(status_code=404, detail="Case not found.")
        entities = db.q("SELECT entity_type, value, normalized, role, source FROM case_entities "
                        "WHERE case_id=%s ORDER BY entity_type", [case_id])
        recs = db.q("SELECT id, agent, kind, score, explanation, status, created_at FROM recommendations "
                   "WHERE case_id=%s ORDER BY created_at DESC", [case_id])
        timeline = controller.timeline(db, case_id)
        similar = controller.similar_cases(db, case_id)
    return {"case": case, "entities": entities, "recommendations": recs,
           "timeline": timeline, "similar_cases": similar}


# --------------------------------------------------------------------------- recommendations
@app.get("/api/recommendations")
def list_recommendations(status: str = "pending", kind: str = "", user=Depends(get_user)):
    sql = "SELECT * FROM recommendations WHERE status=%s"
    params = [status]
    if kind:
        sql += " AND kind=%s"; params.append(kind)
    sql += " ORDER BY created_at DESC LIMIT 200"
    with dbmod.connect() as db:
        return db.q(sql, params)


class DecisionBody(BaseModel):
    decision: str
    comment: str = ""


@app.post("/api/recommendations/{rec_id}/decide")
def decide(rec_id: int, body: DecisionBody, user=Depends(get_user)):
    require_role(user, ROLE_COMMANDER)
    if body.decision not in ("accepted", "rejected"):
        raise HTTPException(status_code=400, detail="decision must be 'accepted' or 'rejected'.")
    with dbmod.connect() as db:
        controller.decide(db, user, rec_id, body.decision, body.comment)
    return {"ok": True}


# --------------------------------------------------------------------------- resource optimisation
@app.post("/api/optimise")
def optimise(pool_size: int = 10, user=Depends(get_user)):
    require_role(user, ROLE_COMMANDER)
    with dbmod.connect() as db:
        result, rid = controller.run_optimisation(db, user, pool_size=pool_size)
    return {"recommendation_id": rid, **result}


@app.get("/api/stations")
def stations(user=Depends(get_user)):
    with dbmod.connect() as db:
        return controller.resource_agent.station_risk(db, time.strftime("%Y-%m-%d"))


# --------------------------------------------------------------------------- audit trail
@app.get("/api/audit")
def audit(limit: int = 100, user=Depends(get_user)):
    require_role(user, ROLE_COMMANDER)
    with dbmod.connect() as db:
        return db.q("SELECT * FROM audit_log ORDER BY created_at DESC, id DESC LIMIT %s", [limit])


@app.get("/api/whoami")
def whoami(user=Depends(get_user)):
    return user


@app.get("/api/system_status")
def system_status():
    from .agents import extraction, linkage as lk
    return {
        "database_engine": config.db_engine(),
        "spacy": extraction.spacy_status(),
        "faiss": "available" if _has("faiss") else "not installed (using NumPy search instead)",
        "shap": "available" if _has("shap") else "not installed (using exact linear explanation)",
    }


def _has(mod):
    try:
        __import__(mod)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- serve the frontend
@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))
