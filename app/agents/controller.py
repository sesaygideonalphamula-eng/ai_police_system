"""The Controller: the single place the web app talks to. It routes work to the right
agent(s), exactly like the 'controller orchestrates the four agents' design in the proposal.
Every action it takes is written to the audit_log table (audit trail requirement)."""
import time

from .. import config
from . import linkage
from .case_intelligence import CaseIntelligenceAgent
from .investigation_support import InvestigationSupportAgent
from .resource_optimization import ResourceOptimizationAgent


class Controller:
    def __init__(self):
        self.link_model = linkage.load_model(config.model_path())
        self.case_agent = CaseIntelligenceAgent(self.link_model)
        self.invest_agent = InvestigationSupportAgent()
        self.resource_agent = ResourceOptimizationAgent()

    # ---------------------------------------------------------------- audit trail
    def log(self, db, user, event, case_id=None, recommendation_id=None, detail=None):
        db.insert("audit_log", {
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "user_id": user["id"] if user else None,
            "username": user["username"] if user else "system",
            "event": event, "case_id": case_id, "recommendation_id": recommendation_id,
            "detail": detail,
        })

    # ---------------------------------------------------------------- cases
    def new_case(self, db, user, fields):
        fields = dict(fields)
        fields.setdefault("outcome_note", None)
        fields["created_by"] = user["id"] if user else None
        fields["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        fields["analysed"] = 0
        case_id = db.insert("cases", fields)
        self.log(db, user, "case_created", case_id=case_id, detail=fields.get("case_number"))

        case_row = db.one("SELECT * FROM cases WHERE id=%s", [case_id])
        result = self.case_agent.analyse_case(db, case_row)
        self.invest_agent.save_leads_as_recommendations(db, case_id)
        self.log(db, user, "case_analysed", case_id=case_id,
                 detail="{} link recommendation(s)".format(result["link_recommendations"]))
        return case_id, result

    def timeline(self, db, case_id):
        return self.invest_agent.build_timeline(db, case_id)

    def similar_cases(self, db, case_id):
        return self.case_agent.similar_cases(db, case_id)

    # ---------------------------------------------------------------- recommendations
    def decide(self, db, user, rec_id, decision, comment):
        db.run("UPDATE recommendations SET status=%s, decided_by=%s, decided_at=%s, "
              "decision_comment=%s WHERE id=%s",
              [decision, user["id"] if user else None,
               time.strftime("%Y-%m-%dT%H:%M:%S"), comment, rec_id])
        self.log(db, user, "recommendation_{}".format(decision),
                 recommendation_id=rec_id, detail=comment)

    # ---------------------------------------------------------------- resource optimisation
    def run_optimisation(self, db, user, pool_size=10):
        result = self.resource_agent.optimise(db, pool_size=pool_size)
        rid = self.resource_agent.save_recommendation(db, result)
        self.log(db, user, "optimisation_run", recommendation_id=rid,
                 detail="pool_size={}".format(pool_size))
        return result, rid

    # ---------------------------------------------------------------- dashboard
    def dashboard_stats(self, db):
        """Field names here must match what static/index.html's Dashboard component reads:
        total_cases, pending_recommendations, cases_by_status, cases_by_offence, stations."""
        total = db.one("SELECT COUNT(*) AS n FROM cases")["n"]
        cases_by_status = db.q("SELECT status, COUNT(*) AS n FROM cases GROUP BY status")
        cases_by_offence = db.q("SELECT offence_type, COUNT(*) AS n FROM cases "
                                "GROUP BY offence_type ORDER BY n DESC")
        pending = db.one("SELECT COUNT(*) AS n FROM recommendations WHERE status='pending'")["n"]
        stations = self.resource_agent.station_risk(db, time.strftime("%Y-%m-%d"))
        return {
            "total_cases": total,
            "pending_recommendations": pending,
            "cases_by_status": cases_by_status,
            "cases_by_offence": cases_by_offence,
            "stations": stations,
        }