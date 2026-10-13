"""Sets up the database from nothing: creates tables, adds stations and demo users,
loads simulated case data, runs the Case Intelligence agent on every case (so entities
and link recommendations exist), trains the link-likelihood model on the simulated
data's hidden ground truth, and saves it to models/link_model.joblib.

Run with:  python -m scripts.seed
Safe to re-run: it wipes and rebuilds everything (only ever touches simulated data).
"""
import itertools
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, db as dbmod, schema, security, data_gen
from app.agents import linkage, case_intelligence, controller as controller_mod

DEMO_USERS = [
    ("admin", "System Administrator", "System Administrator", "Admin@123", None),
    ("commander", "ACP Fatmata Bangura", "Police Commander", "Commander@123", None),
    ("clerk1", "WPC Isatu Mansaray", "Case Records Clerk", "Clerk@123", 0),
    ("officer1", "Sgt Ibrahim Kargbo", "Investigating Officer", "Officer@123", 0),
    ("officer2", "Insp Mohamed Turay", "Investigating Officer", "Officer@123", 1),
]


def build_pairs_for_training(cases_with_gt):
    """Turn the simulated ground-truth series labels into (features, label) training pairs."""
    X, y = [], []
    for a, b in itertools.combinations(cases_with_gt, 2):
        sets_a = {"persons": a["gt"]["persons"], "suspects": a["gt"]["persons"], "places": a["gt"]["places"],
                  "exhibits": a["gt"]["exhibits"]}
        sets_b = {"persons": b["gt"]["persons"], "suspects": b["gt"]["persons"], "places": b["gt"]["places"],
                  "exhibits": b["gt"]["exhibits"]}
        text_sim = 1.0 if a["offence_type"] == b["offence_type"] else 0.0  # placeholder, replaced below
        feats, _ = linkage.pair_features(
            {"reported_date": a["reported_date"], "offence_type": a["offence_type"], "station_id": a.get("station_id")},
            sets_a,
            {"reported_date": b["reported_date"], "offence_type": b["offence_type"], "station_id": b.get("station_id")},
            sets_b, text_sim)
        label = 1 if (a["series"] is not None and a["series"] == b["series"]) else 0
        X.append(linkage.vector(feats)); y.append(label)
    return X, y


def main():
    print("Building database schema (engine: {}) ...".format(config.db_engine()))
    if config.db_engine() == "postgres":
        dbmod.ensure_postgres_database()
    with dbmod.connect() as db:
        schema.drop_schema(db)
        schema.create_schema(db)

        print("Adding stations ...")
        station_id_by_code = {}
        for s in data_gen.STATIONS:
            sid = db.insert("stations", {
                "name": s["name"], "code": s["code"], "patrol_officers": s["patrol_officers"],
                "investigators": s["investigators"], "coverage_weight": s["coverage_weight"],
            })
            station_id_by_code[s["code"]] = sid

        print("Adding demo user accounts ...")
        for username, full_name, role, password, station_idx in DEMO_USERS:
            station_id = station_id_by_code[data_gen.STATIONS[station_idx]["code"]] if station_idx is not None else None
            h, salt = security.hash_password(password)
            db.insert("users", {
                "username": username, "full_name": full_name, "role": role, "station_id": station_id,
                "password_hash": h, "salt": salt, "is_active": 1,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })

        print("Generating simulated case data ...")
        data = data_gen.generate()
        case_rows = []
        for c in data["cases"]:
            cid = db.insert("cases", {
                "case_number": "SLP-2026-{:05d}".format(len(case_rows) + 1),
                "title": c["title"], "offence_type": c["offence_type"], "priority": c["priority"],
                "status": c["status"], "station_id": station_id_by_code[c["station_code"]],
                "location": c["location"], "reported_date": c["reported_date"],
                "narrative": c["narrative"], "outcome_note": c["outcome_note"],
                "created_by": None, "created_at": c["reported_date"] + "T09:00:00", "analysed": 0,
            })
            c["id"] = cid
            c["station_id"] = station_id_by_code[c["station_code"]]
            case_rows.append(c)

    print("Training the link-likelihood model on {} simulated cases ...".format(len(case_rows)))
    X, y = build_pairs_for_training(case_rows)
    # replace the placeholder text_similarity with a real TF-IDF value now that all text exists
    store = linkage.VectorStore().fit([c["id"] for c in case_rows], [c["narrative"] for c in case_rows])
    idx = 0
    pairs = list(itertools.combinations(case_rows, 2))
    for k, (a, b) in enumerate(pairs):
        sim_map = store.tfidf_similarity(a["narrative"])
        X[k][0] = sim_map.get(b["id"], 0.0)
    model = linkage.train_model(X, y, info={"trained_on": "simulated_data_gen", "n_cases": len(case_rows)})
    Path(config.model_path()).parent.mkdir(parents=True, exist_ok=True)
    linkage.save_model(model, config.model_path())
    print("Model saved to", config.model_path())

    print("Running the Case Intelligence agent on every case (entities + link recommendations) ...")
    ctrl = controller_mod.Controller()  # reloads the model we just saved
    with dbmod.connect() as db:
        rows = db.q("SELECT * FROM cases ORDER BY id")
        total_links = 0
        for row in rows:
            result = ctrl.case_agent.analyse_case(db, row)
            total_links += result["link_recommendations"]
        for row in rows:
            ctrl.invest_agent.save_leads_as_recommendations(db, row["id"])
        ctrl.run_optimisation(db, {"id": None, "username": "seed_script"}, pool_size=10)
    print("Done. {} cases loaded, {} link recommendations created.".format(len(rows), total_links))
    print()
    print("Login accounts (username / password):")
    for username, full_name, role, password, _ in DEMO_USERS:
        print("  {:<10} / {:<14} -> {} ({})".format(username, password, role, full_name))


if __name__ == "__main__":
    main()
