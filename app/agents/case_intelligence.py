"""Agent 1: Case Intelligence.
When a new case is saved, this agent:
  1. Reads the narrative and pulls out people, places, dates, exhibits (extraction.py).
  2. Compares the new case with older cases (linkage.py) using the vector store + model.
  3. Writes a "possible_link" recommendation for every pair that scores above the threshold,
     each with a plain-English explanation (explainability.py).
"""
import json
import time

from .base import Agent
from . import extraction, linkage, explainability


class CaseIntelligenceAgent(Agent):
    name = "case_intelligence"

    def __init__(self, link_model):
        self.link_model = link_model

    def analyse_case(self, db, case):
        """case: dict row from the cases table (already saved, has an id)."""
        entities = extraction.extract_entities(case["narrative"])
        for e in entities:
            db.insert("case_entities", {
                "case_id": case["id"], "entity_type": e["entity_type"], "value": e["value"],
                "normalized": e["normalized"], "role": e["role"], "source": e["source"],
            })

        others = db.q(
            "SELECT id, offence_type, station_id, reported_date, narrative FROM cases "
            "WHERE id != %s AND analysed = 1", [case["id"]])
        created = []
        if others:
            store = linkage.VectorStore().fit(
                [o["id"] for o in others], [o["narrative"] for o in others])
            sims = store.tfidf_similarity(case["narrative"])
            sets_new = linkage.entity_sets(entities)

            for other in others:
                other_ents = db.q(
                    "SELECT entity_type, normalized, role FROM case_entities WHERE case_id = %s",
                    [other["id"]])
                sets_other = linkage.entity_sets(
                    [{"entity_type": r["entity_type"], "normalized": r["normalized"], "role": r["role"]}
                    for r in other_ents])
                feats, evidence = linkage.pair_features(
                    case, sets_new, other, sets_other, sims.get(other["id"], 0.0))
                prob = self.link_model.probability(feats)
                if prob >= linkage.THRESHOLD:
                    text = explainability.build_explanation_text(self.link_model, feats, evidence, prob)
                    rid = db.insert("recommendations", {
                        "agent": self.name, "kind": "possible_link", "case_id": case["id"],
                        "station_id": None, "score": prob,
                        "payload": json.dumps({"other_case_id": other["id"], "features": feats,
                                              "evidence": evidence}),
                        "explanation": text, "status": "pending",
                        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    })
                    created.append(rid)

        db.run("UPDATE cases SET analysed = 1 WHERE id = %s", [case["id"]])
        return {"entities_found": len(entities), "link_recommendations": len(created)}

    def similar_cases(self, db, case_id, k=5):
        """Used by the dashboard 'similar cases' panel."""
        case = db.one("SELECT * FROM cases WHERE id = %s", [case_id])
        others = db.q("SELECT id, narrative FROM cases WHERE id != %s AND analysed = 1", [case_id])
        if not others:
            return []
        store = linkage.VectorStore().fit([o["id"] for o in others], [o["narrative"] for o in others])
        hits = store.search(case["narrative"], k=k)
        out = []
        for cid, score in hits:
            c = db.one("SELECT id, case_number, title, offence_type, status FROM cases WHERE id = %s", [cid])
            if c:
                c["similarity"] = round(score, 3)
                out.append(c)
        return out
