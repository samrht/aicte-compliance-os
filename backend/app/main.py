"""HTTP API for the institution portal and the AICTE regulator console."""
from __future__ import annotations

import asyncio
import json
import shutil
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import Session, select

from app import audit, dag, policy, risk
from app.db import get_session, init_db, session
from app.events import raise_alert
from app.models import (Alert, Application, AuditEntry, FacultyToken, Finding, Institution,
                        WorkflowNode, now)

_tasks: set[asyncio.Task] = set()
_tamper_backup: dict[int, dict] = {}


def schedule(app_id: int) -> None:
    task = asyncio.get_running_loop().create_task(dag.run(app_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    risk.model()
    with session() as s:
        empty = s.exec(select(Institution)).first() is None
    if empty:
        from app.seed import seed
        seed()
    for app_id in dag.resume_all():
        schedule(app_id)
    yield


app = FastAPI(title="AICTE Compliance OS", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# --- Serialisers ----------------------------------------------------------------

def inst_json(i: Institution) -> dict:
    return i.model_dump()


def app_json(s: Session, a: Application, full: bool = False) -> dict:
    inst = s.get(Institution, a.institution_id)
    out = a.model_dump(exclude={"signals", "contributions"} if not full else set())
    out["institution"] = {"id": inst.id, "name": inst.name, "code": inst.code,
                          "city": inst.city, "state": inst.state, "status": inst.status}
    if a.decided_at:
        out["turnaround_hours"] = round((a.decided_at - a.submitted_at).total_seconds() / 3600, 1)
    if full:
        out["nodes"] = [n.model_dump() for n in s.exec(
            select(WorkflowNode).where(WorkflowNode.application_id == a.id)
            .order_by(WorkflowNode.seq, WorkflowNode.lane)).all()]
        sev = {"critical": 0, "warn": 1, "info": 2}
        out["findings"] = sorted((f.model_dump() for f in s.exec(
            select(Finding).where(Finding.application_id == a.id)).all()),
            key=lambda f: sev.get(f["severity"], 3))
        out["alerts"] = [x.model_dump() for x in s.exec(
            select(Alert).where(Alert.application_id == a.id).order_by(Alert.id.desc())).all()]
    return out


# --- Institutions -----------------------------------------------------------------

@app.get("/api/institutions")
def list_institutions(s: Session = Depends(get_session)) -> list[dict]:
    return [inst_json(i) for i in s.exec(select(Institution).order_by(Institution.name)).all()]


@app.get("/api/institutions/{inst_id}")
def get_institution(inst_id: int, s: Session = Depends(get_session)) -> dict:
    inst = s.get(Institution, inst_id)
    if not inst:
        raise HTTPException(404, "unknown institution")
    apps = s.exec(select(Application).where(Application.institution_id == inst_id)
                  .order_by(Application.id.desc())).all()
    alerts = s.exec(select(Alert).where(Alert.institution_id == inst_id)
                    .order_by(Alert.id.desc())).all()
    results = policy.evaluate(inst.metrics, policy.load_policy()) if inst.metrics else []
    from app.seed import PREFILL
    return inst_json(inst) | {
        "prefill": PREFILL.get(inst.code),
        "applications": [app_json(s, a) for a in apps],
        "alerts": [a.model_dump() for a in alerts],
        "norms": results,
        "plan": policy.remediation(inst.metrics, results) if results else [],
    }


# --- Applications -------------------------------------------------------------------

@app.get("/api/applications")
def list_applications(status: Optional[str] = None, s: Session = Depends(get_session)) -> list[dict]:
    q = select(Application).order_by(Application.id.desc())
    if status:
        q = q.where(Application.status.in_(status.split(",")))
    return [app_json(s, a) for a in s.exec(q).all()]


@app.get("/api/applications/{app_id}")
def get_application(app_id: int, s: Session = Depends(get_session)) -> dict:
    a = s.get(Application, app_id)
    if not a:
        raise HTTPException(404, "unknown application")
    return app_json(s, a, full=True)


@app.post("/api/applications")
async def submit_application(
    institution_id: int = Form(...),
    students: int = Form(...),
    land_acres: float = Form(...),
    builtup_sqm: float = Form(...),
    labs: int = Form(...),
    kind: str = Form("Extension of Approval"),
    faculty_csv: Optional[UploadFile] = File(None),
    financials: Optional[UploadFile] = File(None),
    photos: list[UploadFile] = File(default=[]),
) -> dict:
    with session() as s:
        inst = s.get(Institution, institution_id)
        if not inst:
            raise HTTPException(404, "unknown institution")
        a = Application(institution_id=inst.id, kind=kind, metrics={
            "students": students, "land_acres": land_acres, "builtup_sqm": builtup_sqm, "labs": labs})
        s.add(a)
        s.flush()
        folder = dag.upload_dir(a.id)
        (folder / "photos").mkdir(parents=True, exist_ok=True)
        if faculty_csv is not None:
            (folder / "faculty.csv").write_bytes(await faculty_csv.read())
        if financials is not None:
            (folder / "financials.pdf").write_bytes(await financials.read())
        for p in photos:
            name = p.filename.replace("/", "_").replace("\\", "_")
            (folder / "photos" / name).write_bytes(await p.read())
        inst.status = "pending"
        s.add(inst)
        dag.create_nodes(s, a)
        audit.append(s, f"institution:{inst.code}", "application.submitted", f"application:{a.id}",
                     {"kind": kind, "photos": len(photos), "has_roster": faculty_csv is not None,
                      "has_financials": financials is not None})
        s.commit()
        app_id = a.id
    schedule(app_id)
    return {"id": app_id}


class Decision(BaseModel):
    approve: bool
    note: str = ""
    actor: str = "aicte:regional-officer"


@app.post("/api/applications/{app_id}/decision")
async def decide(app_id: int, body: Decision) -> dict:
    with session() as s:
        a = s.get(Application, app_id)
        if not a:
            raise HTTPException(404, "unknown application")
        try:
            dag.decide(s, a, body.approve, body.actor, body.note)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
    schedule(app_id)
    return {"ok": True}


# --- Dashboard ------------------------------------------------------------------------

@app.get("/api/dashboard")
def dashboard(s: Session = Depends(get_session)) -> dict:
    insts = s.exec(select(Institution)).all()
    apps = s.exec(select(Application)).all()
    alerts = s.exec(select(Alert)).all()
    decided = [a for a in apps if a.decided_at]
    auto = [a for a in decided if (a.decided_by or "").startswith("auto")]

    def avg_hours(xs):
        hrs = [(a.decided_at - a.submitted_at).total_seconds() / 3600 for a in xs]
        return round(sum(hrs) / len(hrs), 1) if hrs else None

    by_tier = defaultdict(list)
    for a in decided:
        by_tier[a.tier].append(a)
    return {
        "institutions": len(insts),
        "applications": len(apps),
        "in_flight": sum(a.status == "running" for a in apps),
        "awaiting_review": sum(a.status == "awaiting_review" for a in apps),
        "auto_ratified_pct": round(100 * len(auto) / len(decided), 1) if decided else 0,
        "open_alerts": sum(not x.acknowledged for x in alerts),
        "critical_alerts": sum(not x.acknowledged and x.severity == "critical" for x in alerts),
        "lockdowns": sum(i.status == "lockdown" for i in insts),
        "turnaround_hours": {t: avg_hours(v) for t, v in by_tier.items()},
        "tiers": Counter(a.tier for a in apps if a.tier),
        "statuses": Counter(i.status for i in insts),
        "by_state": [{"state": k, "count": v} for k, v in sorted(Counter(i.state for i in insts).items())],
        "risk_histogram": _histogram([a.risk_score for a in apps if a.risk_score is not None]),
        "model": {"auc": risk.model().auc, "importance": risk.model().importance()[:6]},
        "recent": [app_json(s, a) for a in sorted(apps, key=lambda a: a.id, reverse=True)[:8]],
    }


def _histogram(xs: list[float], bins: int = 10) -> list[dict]:
    counts = [0] * bins
    for x in xs:
        counts[min(bins - 1, int(x * bins))] += 1
    return [{"bin": f"{i / bins:.1f}", "count": c} for i, c in enumerate(counts)]


# --- Alerts -------------------------------------------------------------------------------

@app.get("/api/alerts")
def list_alerts(institution_id: Optional[int] = None, s: Session = Depends(get_session)) -> list[dict]:
    q = select(Alert).order_by(Alert.id.desc())
    if institution_id:
        q = q.where(Alert.institution_id == institution_id)
    names = {i.id: i.name for i in s.exec(select(Institution)).all()}
    return [a.model_dump() | {"institution": names.get(a.institution_id)} for a in s.exec(q).all()]


@app.post("/api/alerts/{alert_id}/ack")
def ack_alert(alert_id: int) -> dict:
    with session() as s:
        a = s.get(Alert, alert_id)
        if not a:
            raise HTTPException(404)
        a.acknowledged = True
        s.add(a)
        audit.append(s, "aicte:regional-officer", "alert.acknowledged", f"alert:{alert_id}", {})
        s.commit()
    return {"ok": True}


@app.post("/api/monitor/sweep")
def compliance_sweep() -> dict:
    """Continuous monitoring: re-judge every approved institution against the live norms."""
    raised = 0
    with session() as s:
        pol = policy.load_policy()
        for inst in s.exec(select(Institution)).all():
            if not inst.metrics or inst.status not in ("approved",):
                continue
            failed = [r for r in policy.evaluate(inst.metrics, pol) if r["passed"] is False
                      and r["severity"] == "critical"]
            if failed:
                raise_alert(s, kind="monitoring", severity="warn", institution_id=inst.id,
                            title=f"Compliance drift: {inst.name}",
                            message="Fails " + ", ".join(r["id"] for r in failed) + " under current norms.",
                            actor="monitor:sweep")
                raised += 1
        audit.append(s, "monitor:sweep", "monitor.sweep", "norms", {"alerts": raised})
        s.commit()
    return {"alerts_raised": raised}


# --- Collision radar ----------------------------------------------------------------------

@app.get("/api/collisions")
def collisions(s: Session = Depends(get_session)) -> dict:
    rows = s.exec(select(FacultyToken.token, FacultyToken.institution_id)).all()
    by_token: dict[str, set[int]] = defaultdict(set)
    for tok, inst_id in rows:
        by_token[tok].add(inst_id)
    shared = {t: ids for t, ids in by_token.items() if len(ids) > 1}
    edges: dict[tuple[int, int], list[str]] = defaultdict(list)
    for tok, ids in shared.items():
        ids = sorted(ids)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                edges[(ids[i], ids[j])].append(tok[:12])
    involved = {i for pair in edges for i in pair}
    insts = {i.id: i for i in s.exec(select(Institution)).all()}
    return {
        "total_tokens": len(by_token),
        "shared_tokens": len(shared),
        "nodes": [{"id": i, "name": insts[i].name, "code": insts[i].code, "status": insts[i].status,
                   "city": insts[i].city,
                   "shared": sum(len(v) for k, v in edges.items() if i in k)} for i in sorted(involved)],
        "edges": [{"source": a, "target": b, "count": len(toks), "tokens": toks[:6]}
                  for (a, b), toks in edges.items()],
        "sample": [{"token": t[:12] + "…" + t[-4:], "institutions": [insts[i].name for i in ids]}
                   for t, ids in list(shared.items())[:12]],
    }


# --- Audit log ---------------------------------------------------------------------------------

@app.get("/api/audit")
def audit_log(limit: int = 200, s: Session = Depends(get_session)) -> dict:
    entries = s.exec(select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit)).all()
    report = audit.verify_log(s)
    bad = set(report["tampered"])
    return {"verification": report,
            "entries": [e.model_dump() | {"tampered": e.id in bad} for e in entries]}


@app.post("/api/audit/verify")
def audit_verify(s: Session = Depends(get_session)) -> dict:
    return audit.verify_log(s)


@app.get("/api/audit/proof/{entry_id}")
def audit_proof(entry_id: int, s: Session = Depends(get_session)) -> dict:
    try:
        return audit.proof_for(s, entry_id)
    except KeyError as exc:
        raise HTTPException(404, "unknown entry") from exc


@app.post("/api/audit/tamper/{entry_id}")
def audit_tamper(entry_id: int) -> dict:
    """Demo only: edit a logged row directly, the way an insider with DB access would."""
    with session() as s:
        e = s.get(AuditEntry, entry_id)
        if not e:
            raise HTTPException(404)
        _tamper_backup.setdefault(entry_id, json.loads(json.dumps(e.payload)))
        forged = dict(e.payload)
        if "decision" in forged:
            forged["decision"] = "approved" if forged["decision"] != "approved" else "rejected"
        else:
            forged["forged"] = True
        e.payload = forged
        s.add(e)
        s.commit()
    return {"ok": True, "entry_id": entry_id}


@app.post("/api/audit/restore")
def audit_restore() -> dict:
    with session() as s:
        for entry_id, payload in _tamper_backup.items():
            e = s.get(AuditEntry, entry_id)
            if e:
                e.payload = payload
                s.add(e)
        s.commit()
    n = len(_tamper_backup)
    _tamper_backup.clear()
    return {"restored": n}


# --- Policy / Shadow Sandbox --------------------------------------------------------------------

@app.get("/api/policy")
def get_policy() -> dict:
    pol = policy.load_policy()
    return {"policy": pol, "rego": policy.to_rego(pol)}


class SandboxRequest(BaseModel):
    overrides: dict[str, float] = {}


@app.post("/api/sandbox/simulate")
def sandbox(body: SandboxRequest, s: Session = Depends(get_session)) -> dict:
    insts = [inst_json(i) for i in s.exec(select(Institution)).all()]
    return policy.simulate(insts, body.overrides)


@app.get("/api/model")
def model_info() -> dict:
    m = risk.model()
    return {"auc": m.auc, "features": risk.LABELS, "importance": m.importance()}


# --- Demo controls -------------------------------------------------------------------------------

@app.post("/api/admin/reset")
async def reset_demo() -> dict:
    from app import config
    from app.db import reset_db
    from app.seed import seed
    for t in list(_tasks):
        t.cancel()
    reset_db()
    shutil.rmtree(config.UPLOADS, ignore_errors=True)
    config.ensure_dirs()
    _tamper_backup.clear()
    seed()
    return {"ok": True}


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "time": now().isoformat()}
