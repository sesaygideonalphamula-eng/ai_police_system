"""End-to-end test: create two related cases and confirm the system links them, extracts
entities, and produces at least one explained recommendation - the core promise of the
Case Intelligence and Explainability modules."""
from app import db as dbmod, schema, security
from app.agents.controller import Controller


def _make_user(db):
    h, salt = security.hash_password("Test@123")
    uid = db.insert("users", {
        "username": "tester", "full_name": "Test User", "role": "Case Records Clerk",
        "station_id": None, "password_hash": h, "salt": salt, "is_active": 1,
        "created_at": "2026-01-01T00:00:00",
    })
    return db.one("SELECT * FROM users WHERE id=%s", [uid])


def test_new_case_is_analysed_and_linked_cases_are_found(db_with_schema):
    db = db_with_schema
    station_id = db.insert("stations", {
        "name": "Central Division", "code": "CEN", "patrol_officers": 20,
        "investigators": 6, "coverage_weight": 1.2,
    })
    user = _make_user(db)
    ctrl = Controller()

    case1_id, r1 = ctrl.new_case(db, user, {
        "case_number": "SLP-TEST-0001", "title": "Robbery A", "offence_type": "Armed Robbery",
        "priority": 3, "status": "Open", "station_id": station_id, "location": "Congo Town",
        "reported_date": "2026-06-01", "narrative":
        "The complainant, Aminata Bah, reported that the suspect, Ibrahim Kargbo, alias "
        "\"Black Rat\", robbed her at Congo Town with a knife and took a mobile phone.",
        "outcome_note": None,
    })
    assert r1["entities_found"] > 0

    case2_id, r2 = ctrl.new_case(db, user, {
        "case_number": "SLP-TEST-0002", "title": "Robbery B", "offence_type": "Armed Robbery",
        "priority": 3, "status": "Open", "station_id": station_id, "location": "Congo Town",
        "reported_date": "2026-06-05", "narrative":
        "The complainant, Foday Sesay, reported that the suspect, Ibrahim Kargbo, alias "
        "\"Black Rat\", robbed him at Congo Town with a knife and took a mobile phone.",
        "outcome_note": None,
    })
    assert r2["link_recommendations"] >= 1

    recs = db.q("SELECT * FROM recommendations WHERE case_id=%s AND kind='possible_link'", [case2_id])
    assert len(recs) >= 1
    assert recs[0]["explanation"]
    assert "suspect" in recs[0]["explanation"].lower() or "Ibrahim" in recs[0]["explanation"]

    audit = db.q("SELECT event FROM audit_log ORDER BY id")
    assert "case_created" in [a["event"] for a in audit]
    assert "case_analysed" in [a["event"] for a in audit]


def test_recommendation_decision_and_audit_trail(db_with_schema):
    db = db_with_schema
    station_id = db.insert("stations", {
        "name": "Central Division", "code": "CEN", "patrol_officers": 20,
        "investigators": 6, "coverage_weight": 1.2,
    })
    commander_h, commander_salt = security.hash_password("Commander@123")
    cid = db.insert("users", {
        "username": "commander", "full_name": "Commander", "role": "Police Commander",
        "station_id": None, "password_hash": commander_h, "salt": commander_salt,
        "is_active": 1, "created_at": "2026-01-01T00:00:00",
    })
    commander = db.one("SELECT * FROM users WHERE id=%s", [cid])
    ctrl = Controller()
    result, rid = ctrl.run_optimisation(db, commander, pool_size=5)
    assert result["pool_size"] == 5
    assert result["allocations"][0]["station"] == "Central Division"

    ctrl.decide(db, commander, rid, "accepted", "Approved for this week.")
    rec = db.one("SELECT * FROM recommendations WHERE id=%s", [rid])
    assert rec["status"] == "accepted"
    assert rec["decision_comment"] == "Approved for this week."

    events = [a["event"] for a in db.q("SELECT event FROM audit_log ORDER BY id")]
    assert "optimisation_run" in events
    assert "recommendation_accepted" in events
