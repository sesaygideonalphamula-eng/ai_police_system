"""Agent 2: Investigation Support.
Builds a timeline for a case (and any cases it is linked to) and suggests concrete leads:
 - a suspect/alias named in this case that was also arrested in a solved case (strong lead)
 - a suspect who appears in several unsolved cases in the same series (repeat-offender lead)
 - a shared exhibit description worth checking at second-hand markets
"""
import json
import time

from .base import Agent


class InvestigationSupportAgent(Agent):
    name = "investigation_support"

    def build_timeline(self, db, case_id):
        """Combine this case with every case it has a 'possible_link' or 'confirmed_link' to."""
        links = db.q(
            "SELECT payload, score FROM recommendations WHERE case_id = %s "
            "AND kind IN ('possible_link','confirmed_link') AND status != 'rejected'", [case_id])
        ids = {case_id}
        for r in links:
            ids.add(json.loads(r["payload"])["other_case_id"])
        rows = db.q(
            "SELECT id, case_number, title, offence_type, status, reported_date, location, narrative "
            "FROM cases WHERE id IN ({})".format(",".join(["%s"] * len(ids))), list(ids))
        rows.sort(key=lambda r: r["reported_date"])
        return rows

    def suggest_leads(self, db, case_id):
        timeline = self.build_timeline(db, case_id)
        if len(timeline) < 2:
            return []
        ent_by_case = {}
        for c in timeline:
            rows = db.q(
                "SELECT entity_type, normalized, value, role FROM case_entities WHERE case_id = %s",
                [c["id"]])
            ent_by_case[c["id"]] = rows

        leads = []
        solved = [c for c in timeline if c["status"] in ("Solved", "Closed")]
        open_cases = [c for c in timeline if c["status"] not in ("Solved", "Closed")]

        for oc in open_cases:
            oc_suspects = {r["normalized"]: r["value"] for r in ent_by_case[oc["id"]]
                          if r["entity_type"] == "PERSON" and r["role"] == "suspect"}
            for sc in solved:
                sc_people = {r["normalized"]: r["value"] for r in ent_by_case[sc["id"]]
                            if r["entity_type"] == "PERSON"}
                overlap = set(oc_suspects) & set(sc_people)
                for norm in overlap:
                    leads.append({
                        "kind": "known_suspect", "case_id": oc["id"], "related_case_id": sc["id"],
                        "text": "{} is named as a suspect in open case {} and was already arrested "
                                "in solved case {}. Recommend re-interviewing this person and "
                                "checking their whereabouts on the date of case {}.".format(
                                    oc_suspects[norm], oc["case_number"], sc["case_number"],
                                    oc["case_number"]),
                    })

        # repeat suspect across several open cases (series-style lead)
        from collections import defaultdict
        suspect_cases = defaultdict(set)
        suspect_name = {}
        for c in timeline:
            for r in ent_by_case[c["id"]]:
                if r["entity_type"] == "PERSON" and r["role"] == "suspect":
                    suspect_cases[r["normalized"]].add(c["case_number"])
                    suspect_name[r["normalized"]] = r["value"]
        for norm, case_numbers in suspect_cases.items():
            if len(case_numbers) >= 2:
                leads.append({
                    "kind": "repeat_suspect", "case_id": case_id, "related_case_id": None,
                    "text": "{} is named as a suspect in {} linked case(s): {}. Recommend "
                            "prioritising surveillance and a joint file for these cases.".format(
                                suspect_name[norm], len(case_numbers), ", ".join(sorted(case_numbers))),
                })

        # shared distinctive exhibit across open cases only
        exhibit_cases = defaultdict(set)
        for c in open_cases:
            for r in ent_by_case[c["id"]]:
                if r["entity_type"] == "EXHIBIT" and r["normalized"] not in ("cash",):
                    exhibit_cases[r["normalized"]].add(c["case_number"])
        for item, case_numbers in exhibit_cases.items():
            if len(case_numbers) >= 2:
                leads.append({
                    "kind": "shared_exhibit", "case_id": case_id, "related_case_id": None,
                    "text": "The item '{}' appears in {} open, linked case(s): {}. Recommend "
                            "checking second-hand markets and pawn shops for this item.".format(
                                item, len(case_numbers), ", ".join(sorted(case_numbers))),
                })
        return leads

    def save_leads_as_recommendations(self, db, case_id):
        leads = self.suggest_leads(db, case_id)
        created = []
        for lead in leads:
            rid = db.insert("recommendations", {
                "agent": self.name, "kind": "investigation_lead", "case_id": lead["case_id"],
                "station_id": None, "score": 0.8 if lead["kind"] == "known_suspect" else 0.6,
                "payload": json.dumps(lead), "explanation": lead["text"], "status": "pending",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            created.append(rid)
        return created
