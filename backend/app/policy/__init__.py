"""AICTE norms as declarative policy, and the Shadow Sandbox that re-runs them.

Rules live in `norms.json` as data, not code: a regulator changes a
threshold and every institution is re-judged with no deploy. `to_rego`
renders the same rules as the Open Policy Agent policy a production
deployment would load.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

RULES_PATH = Path(__file__).with_name("norms.json")

# Rough unit costs (₹ lakh) the remediation optimiser trades off.
COST = {
    "faculty_hire": 9.0,          # per faculty per year
    "phd_hire": 13.0,
    "land_acre": 60.0,
    "builtup_sqm": 0.28,
    "lab": 35.0,
    "fee_per_student": 1.1,       # revenue lost per seat cut
}


def load_policy() -> dict:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def with_overrides(policy: dict, overrides: dict[str, float]) -> dict:
    out = copy.deepcopy(policy)
    for rule in out["rules"]:
        if rule["id"] in overrides and overrides[rule["id"]] is not None:
            rule["value"] = float(overrides[rule["id"]])
    return out


def _passes(value: float, op: str, limit: float) -> bool:
    return value <= limit if op == "<=" else value >= limit


def evaluate(metrics: dict, policy: dict) -> list[dict]:
    """One verdict per rule: pass/fail, the measured value and the gap."""
    out = []
    for rule in policy["rules"]:
        value = metrics.get(rule["metric"])
        if value is None:
            out.append(rule | {"measured": None, "passed": None, "gap": None})
            continue
        ok = _passes(float(value), rule["op"], float(rule["value"]))
        gap = 0.0 if ok else abs(float(value) - float(rule["value"]))
        out.append(rule | {"measured": round(float(value), 2), "passed": ok, "gap": round(gap, 2)})
    return out


def compliant(results: list[dict]) -> bool:
    return all(r["passed"] is not False for r in results if r["severity"] == "critical")


def remediation(metrics: dict, results: list[dict]) -> list[dict]:
    """The cheapest fix for each failed rule.

    Where a rule can be met two ways (hire faculty, or cut intake), both are
    costed and the cheaper is proposed. Production would hand the joint
    problem to CP-SAT; per-rule minimisation is exact while rules don't share
    levers, which holds for this rule set except the intake lever.
    """
    plan = []
    students = float(metrics.get("students", 0) or 0)
    faculty = float(metrics.get("faculty", 0) or 0)
    revenue = float(metrics.get("revenue_lakh", 0) or 0)
    for r in results:
        if r["passed"] is not False:
            continue
        rid, limit = r["id"], float(r["value"])
        if rid == "FAC-RATIO" and faculty:
            hire = math.ceil(students / limit - faculty)
            cut = math.ceil(students - faculty * limit)
            options = [
                {"action": f"Recruit {hire} faculty", "cost_lakh": round(hire * COST["faculty_hire"], 1)},
                {"action": f"Reduce intake by {cut} seats", "cost_lakh": round(cut * COST["fee_per_student"], 1)},
            ]
            plan.append({"rule": rid, "options": options, "best": min(options, key=lambda o: o["cost_lakh"])})
        elif rid == "FAC-PHD" and faculty:
            need = math.ceil(limit / 100 * faculty - float(metrics.get("phd_count", 0)))
            o = {"action": f"Recruit or upgrade {need} PhD faculty", "cost_lakh": round(need * COST["phd_hire"], 1)}
            plan.append({"rule": rid, "options": [o], "best": o})
        elif rid == "LAND-MIN":
            acres = round(limit - float(metrics.get("land_acres", 0)), 2)
            o = {"action": f"Acquire {acres} more acres", "cost_lakh": round(acres * COST["land_acre"], 1)}
            plan.append({"rule": rid, "options": [o], "best": o})
        elif rid == "BUILT-UP" and students:
            sqm = math.ceil((limit - float(metrics.get("builtup_sqm_per_student", 0))) * students)
            o = {"action": f"Add {sqm:,} m² built-up area", "cost_lakh": round(sqm * COST["builtup_sqm"], 1)}
            plan.append({"rule": rid, "options": [o], "best": o})
        elif rid == "LABS" and students:
            labs = math.ceil(limit * students / 100 - float(metrics.get("labs", 0)))
            o = {"action": f"Commission {labs} more labs", "cost_lakh": round(labs * COST["lab"], 1)}
            plan.append({"rule": rid, "options": [o], "best": o})
        elif rid == "FIN-DEFICIT" and revenue:
            cut = round((float(metrics.get("deficit_pct", 0)) - limit) / 100 * revenue, 1)
            o = {"action": f"Close ₹{cut} lakh of the operating gap", "cost_lakh": cut}
            plan.append({"rule": rid, "options": [o], "best": o})
        elif rid == "FIN-CORPUS":
            add = round(limit - float(metrics.get("corpus_lakh", 0)), 1)
            o = {"action": f"Deposit ₹{add} lakh into the corpus FDR", "cost_lakh": add}
            plan.append({"rule": rid, "options": [o], "best": o})
    return plan


def simulate(institutions: list[dict], overrides: dict[str, float]) -> dict:
    """Judge every institution under current and proposed norms; report who flips."""
    base, proposed = load_policy(), with_overrides(load_policy(), overrides)
    rows = []
    for inst in institutions:
        m = inst["metrics"]
        if not m:
            continue
        before = evaluate(m, base)
        after = evaluate(m, proposed)
        ok_before, ok_after = compliant(before), compliant(after)
        rows.append({
            "institution_id": inst["id"], "name": inst["name"], "code": inst["code"],
            "state": inst["state"],
            "before": ok_before, "after": ok_after,
            "flip": None if ok_before == ok_after else ("newly_non_compliant" if ok_before else "newly_compliant"),
            "failing": [r["id"] for r in after if r["passed"] is False],
            "plan": remediation(m, after) if not ok_after else [],
        })
    total = len(rows)
    return {
        "total": total,
        "compliant_before": sum(r["before"] for r in rows),
        "compliant_after": sum(r["after"] for r in rows),
        "flips": [r for r in rows if r["flip"]],
        "rows": rows,
        "policy": proposed,
        "rego": to_rego(proposed),
    }


def to_rego(policy: dict) -> str:
    lines = [f"package {policy['package']}", "", "import rego.v1", ""]
    for r in policy["rules"]:
        bad = ">" if r["op"] == "<=" else "<"
        lines += [
            f"# {r['title']} ({r['ref']})",
            "deny contains msg if {",
            f"    input.{r['metric']} {bad} {r['value']}",
            f"    msg := sprintf(\"{r['id']}: {r['metric']} = %v, required {r['op']} {r['value']}\", [input.{r['metric']}])",
            "}",
            "",
        ]
    return "\n".join(lines)
