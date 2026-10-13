"""Agent 3: Resource Optimization.

Idea: each police station has a "risk score" built from its open/under-investigation cases
(weighted by priority and how recent they are) and a "coverage weight" (size of area/population,
taken from the proposal's station data). Stations whose risk per officer is far above the
citywide average are under-resourced.

A small reserve pool of extra patrol officers (a realistic surge deployment, not existing
officers taken away from another station) is allocated across stations to bring every
station's risk-per-officer ratio as close as possible to the citywide target. This is solved
as a Linear Program (LP): minimise the total remaining imbalance, subject to the pool size.

Note: the proposal names Google OR-Tools for this. OR-Tools' Python wheels are not published
for every Python version (including very new releases), so this module uses SciPy's linear
programming solver (`scipy.optimize.linprog`), which solves the same class of constrained
optimisation problem and installs reliably everywhere. This substitution is documented in
Chapter 2 under 'Technologies and Tools' / 'Challenges Encountered and Solutions'.
"""
import math
import time
import json

import numpy as np
from scipy.optimize import linprog

from .base import Agent

PRIORITY_WEIGHT = {1: 1.0, 2: 2.0, 3: 3.5}
RECENT_DAYS = 45


def _recency_weight(reported_date, today):
    days = max(0, (today - _parse(reported_date)).days)
    return math.exp(-days / RECENT_DAYS)


def _parse(iso):
    from datetime import date
    y, m, d = [int(x) for x in iso[:10].split("-")]
    return date(y, m, d)


class ResourceOptimizationAgent(Agent):
    name = "resource_optimization"

    def station_risk(self, db, today_iso):
        from datetime import date
        y, m, d = [int(x) for x in today_iso[:10].split("-")]
        today = date(y, m, d)
        stations = db.q("SELECT * FROM stations ORDER BY id")
        cases = db.q("SELECT station_id, priority, status, reported_date FROM cases "
                     "WHERE status IN ('Open','Under Investigation')")
        risk = {s["id"]: 0.0 for s in stations}
        counts = {s["id"]: 0 for s in stations}
        for c in cases:
            if c["station_id"] not in risk:
                continue
            w = PRIORITY_WEIGHT.get(c["priority"], 1.0) * _recency_weight(c["reported_date"], today)
            risk[c["station_id"]] += w
            counts[c["station_id"]] += 1
        for s in stations:
            s["open_case_count"] = counts[s["id"]]
            s["risk_score"] = round(risk[s["id"]] * s["coverage_weight"], 2)
        return stations

    def optimise(self, db, pool_size=10, today_iso=None):
        today_iso = today_iso or time.strftime("%Y-%m-%d")
        stations = self.station_risk(db, today_iso)
        n = len(stations)
        officers = np.array([s["patrol_officers"] for s in stations], dtype=float)
        risk = np.array([s["risk_score"] for s in stations], dtype=float)
        total_risk = risk.sum()
        total_officers = officers.sum() + pool_size
        target = total_risk / total_officers if total_officers > 0 else 0.0

        # variables: x_0..x_{n-1} (extra officers per station), d_0..d_{n-1} (unmet risk, >=0)
        n_vars = 2 * n
        c = np.zeros(n_vars)
        c[n:] = 1.0  # minimise total unmet risk

        A_ub = []
        b_ub = []
        for i in range(n):
            row = np.zeros(n_vars)
            row[i] = -target       # -target * x_i
            row[n + i] = -1.0      # - d_i
            A_ub.append(row)
            b_ub.append(-(risk[i] - target * officers[i]))
        # total officers handed out must not exceed the pool
        row = np.zeros(n_vars)
        row[:n] = 1.0
        A_ub.append(row)
        b_ub.append(pool_size)

        bounds = [(0, pool_size)] * n + [(0, None)] * n
        res = linprog(c, A_ub=np.array(A_ub), b_ub=np.array(b_ub), bounds=bounds, method="highs")

        if res.success:
            raw = res.x[:n]
        else:
            raw = np.zeros(n)  # fall back to "no change recommended" if the solver fails

        allocation = self._round_preserving_total(raw, pool_size)
        rows = []
        for i, s in enumerate(stations):
            new_total = officers[i] + allocation[i]
            new_ratio = risk[i] / new_total if new_total else 0.0
            rows.append({
                "station_id": s["id"], "station": s["name"], "current_officers": int(officers[i]),
                "risk_score": risk[i], "current_ratio": round(risk[i] / officers[i], 3) if officers[i] else None,
                "recommended_extra_officers": int(allocation[i]),
                "projected_ratio": round(new_ratio, 3),
            })
        rows.sort(key=lambda r: -r["risk_score"])
        return {
            "target_ratio": round(target, 3), "pool_size": pool_size,
            "solver": "scipy.optimize.linprog (HiGHS)", "solver_success": bool(res.success),
            "allocations": rows,
        }

    @staticmethod
    def _round_preserving_total(raw, pool_size):
        """Round the LP's fractional answer to whole officers without changing the total handed out."""
        floors = np.floor(raw).astype(int)
        remainder = int(round(pool_size - floors.sum()))
        fracs = raw - floors
        order = np.argsort(-fracs)
        alloc = floors.copy()
        for i in range(max(0, remainder)):
            alloc[order[i % len(order)]] += 1
        return alloc

    def save_recommendation(self, db, result):
        text_lines = ["Recommended one-time surge deployment of {} extra patrol officer(s), "
                     "target risk-per-officer ratio {:.2f} (solved with {}).".format(
                         result["pool_size"], result["target_ratio"], result["solver"])]
        for r in result["allocations"][:5]:
            if r["recommended_extra_officers"] > 0:
                text_lines.append("{}: +{} officer(s) (risk score {:.1f}, ratio {:.2f} -> {:.2f}).".format(
                    r["station"], r["recommended_extra_officers"], r["risk_score"],
                    r["current_ratio"] or 0.0, r["projected_ratio"]))
        explanation = " ".join(text_lines)
        rid = db.insert("recommendations", {
            "agent": self.name, "kind": "resource_allocation", "case_id": None, "station_id": None,
            "score": result["target_ratio"], "payload": json.dumps(result), "explanation": explanation,
            "status": "pending", "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        return rid
