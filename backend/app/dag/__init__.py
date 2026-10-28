"""Risk-adaptive workflow engine.

Every application starts as two nodes, ingestion and risk scoring. The risk
node then grows the rest of the graph for the tier it computed:

  low     checks run in parallel, then batch ratification with no human step
          (escalated to a human only if a check raises a critical finding)
  medium  checks run in parallel, then a human review
  high    approval lockdown, checks one after another, a physical
          inspection, then a human review

All state lives in the database and the engine holds none in memory: each
call to `advance` finishes the steps whose time is up and starts the ones
that became ready. The API calls it whenever a case is read, so any server
instance (or a restarted one) picks a case up exactly where it stopped, the
durable-execution property Temporal provides in production. Every transition
is also appended to the Merkle audit log.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import update
from sqlmodel import Session, select

from app import audit, config, policy, risk
from app.db import session
from app.events import raise_alert
from app.models import (Application, FacultyToken, Finding, Institution, PhotoHash,
                        Upload, WorkflowNode, now)
from app.verify import docai, faculty, photos

LABELS = {
    "ingest": "Evidence ingestion",
    "risk": "Risk scorer · LightGBM",
    "lockdown": "Approval lockdown",
    "geo": "Geo-tagged photo audit",
    "finance": "Financial DocAI",
    "faculty": "Faculty collision radar",
    "norms": "Norms policy · OPA",
    "decision": "Batch ratification",
    "inspection": "Physical inspection",
    "review": "Human review",
    "seal": "Audit seal",
}
CHECKS = ["geo", "finance", "faculty", "norms"]
DONE = {"passed", "flagged", "failed", "skipped"}

# key -> (depends_on, seq, lane)
PLANS: dict[str, list[tuple[str, list[str], int, int]]] = {
    "low": [("geo", ["risk"], 2, 0), ("finance", ["risk"], 2, 1), ("faculty", ["risk"], 2, 2),
            ("norms", ["risk"], 2, 3), ("decision", CHECKS, 3, 0), ("seal", ["decision"], 4, 0)],
    "medium": [("geo", ["risk"], 2, 0), ("finance", ["risk"], 2, 1), ("faculty", ["risk"], 2, 2),
               ("norms", ["risk"], 2, 3), ("review", CHECKS, 3, 0), ("seal", ["review"], 4, 0)],
    "high": [("lockdown", ["risk"], 2, 0), ("geo", ["lockdown"], 3, 0), ("finance", ["geo"], 4, 0),
             ("faculty", ["finance"], 5, 0), ("norms", ["faculty"], 6, 0),
             ("inspection", ["norms"], 7, 0), ("review", ["inspection"], 8, 0),
             ("seal", ["review"], 9, 0)],
}


def create_nodes(s: Session, app: Application) -> None:
    s.add(WorkflowNode(application_id=app.id, key="ingest", label=LABELS["ingest"], seq=0))
    s.add(WorkflowNode(application_id=app.id, key="risk", label=LABELS["risk"], seq=1,
                       depends_on=["ingest"]))


def _nodes(s: Session, app_id: int) -> list[WorkflowNode]:
    return list(s.exec(select(WorkflowNode).where(WorkflowNode.application_id == app_id)
                       .order_by(WorkflowNode.seq, WorkflowNode.lane)).all())


def _finding(s: Session, app_id: int, category: str, severity: str, title: str, message: str,
             evidence: dict | None = None) -> None:
    s.add(Finding(application_id=app_id, category=category, severity=severity,
                  title=title, message=message, evidence=evidence or {}))


def _findings(s: Session, app_id: int, category: str | None = None) -> list[Finding]:
    q = select(Finding).where(Finding.application_id == app_id)
    if category:
        q = q.where(Finding.category == category)
    return list(s.exec(q).all())


def _state_for(found: list[Finding]) -> str:
    return "flagged" if any(f.severity in ("critical", "warn") for f in found) else "passed"


# --- Node handlers ------------------------------------------------------------
# Each returns (state, detail). They run inside one DB session and commit with it.

def h_ingest(s: Session, app: Application, inst: Institution) -> tuple[str, str]:
    files = s.exec(select(Upload).where(Upload.application_id == app.id).order_by(Upload.filename)).all()
    declared = dict(app.metrics)
    signals: dict = {"photos": [], "photo_matches": [], "collisions": [], "doc": {}}

    # Photos: hash + GPS, matched against every other institution's photos.
    others = s.exec(select(PhotoHash, Institution).join(Institution)
                    .where(PhotoHash.institution_id != inst.id)).all()
    for up in (f for f in files if f.kind == "photo"):
        info = photos.inspect(data=up.data, filename=up.filename)
        dist = (round(photos.haversine_km(inst.lat, inst.lon, info.lat, info.lon), 2)
                if info.lat is not None else None)
        signals["photos"].append({"file": info.filename, "phash": info.phash, "lat": info.lat,
                                  "lon": info.lon, "distance_km": dist})
        for ph, other in others:
            d = photos.hamming(info.phash, ph.phash)
            if d <= config.PHASH_MAX_DISTANCE:
                signals["photo_matches"].append({
                    "file": info.filename, "hamming": int(d), "institution_id": other.id,
                    "institution": other.name, "their_file": ph.filename})
        s.add(PhotoHash(institution_id=inst.id, application_id=app.id, filename=info.filename,
                        phash=info.phash, lat=info.lat, lon=info.lon))

    # Faculty roster -> blinded tokens, matched against other institutions.
    roster = next((f for f in files if f.kind == "roster"), None)
    rows = faculty.parse_csv(roster.data) if roster else []
    if rows:
        tokens = [r.token for r in rows]
        hits = s.exec(select(FacultyToken, Institution).join(Institution)
                      .where(FacultyToken.token.in_(tokens))
                      .where(FacultyToken.institution_id != inst.id)).all()
        for ft, other in hits:
            signals["collisions"].append({"token": ft.token, "institution_id": other.id,
                                          "institution": other.name, "designation": ft.designation})
        for r in rows:
            s.add(FacultyToken(institution_id=inst.id, application_id=app.id, token=r.token,
                               designation=r.designation, qualification=r.qualification))

    # Financial statement -> fields.
    pdf = next((f for f in files if f.kind == "financials"), None)
    if pdf:
        signals["doc"] = docai.extract(pdf.data)

    m = metrics_from(declared, rows, signals["doc"].get("fields", {}))
    app.metrics = m
    distances = [p["distance_km"] for p in signals["photos"] if p["distance_km"] is not None]
    signals["geo_max_km"] = max(distances) if distances else 0.0
    signals["photo_flags"] = len({x["file"] for x in signals["photo_matches"]})
    signals["faculty_collisions"] = len({c["token"] for c in signals["collisions"]})
    app.signals = signals
    inst.metrics = m
    s.add(inst)
    detail = (f"{len(signals['photos'])} photos hashed · {len(rows)} faculty tokenised · "
              f"{len(signals['doc'].get('fields', {}))} financial fields extracted")
    return "passed", detail


def metrics_from(declared: dict, rows: list, fields: dict) -> dict:
    m = {k: v for k, v in declared.items() if v is not None}
    if rows:
        m["faculty"] = len(rows)
        m["phd_count"] = sum(1 for r in rows if "phd" in r.qualification.lower())
    m.update({k: v for k, v in fields.items() if k != "salary_lakh"})
    students = float(m.get("students") or 0)
    fac = float(m.get("faculty") or 0)
    if students and fac:
        m["students_per_faculty"] = round(students / fac, 2)
    if fac and "phd_count" in m:
        m["phd_pct"] = round(100 * m["phd_count"] / fac, 1)
    if students and m.get("builtup_sqm"):
        m["builtup_sqm_per_student"] = round(float(m["builtup_sqm"]) / students, 2)
    if students and m.get("labs") is not None:
        m["labs_per_100"] = round(100 * float(m["labs"]) / students, 2)
    return m


def h_risk(s: Session, app: Application, inst: Institution) -> tuple[str, str]:
    feats = risk.features_from(app.metrics, app.signals, inst.prior_violations, inst.established)
    result = risk.model().score(feats)
    app.risk_score, app.tier, app.contributions = round(result.probability, 4), result.tier, result.contributions
    inst.risk_score, inst.risk_tier = app.risk_score, app.tier
    s.add(inst)
    for key, deps, seq, lane in PLANS[result.tier]:
        s.add(WorkflowNode(application_id=app.id, key=key, label=LABELS[key], seq=seq, lane=lane,
                           depends_on=deps))
    top = result.contributions[0]["label"]
    if result.tier == "high":
        raise_alert(s, kind="high_risk", severity="critical", institution_id=inst.id,
                    application_id=app.id, title=f"High-risk application: {inst.name}",
                    message=f"Failure probability {result.probability:.0%}. Largest driver: {top}.")
    return "passed", f"p(fail) = {result.probability:.2f} → {result.tier.upper()} tier · top driver: {top}"


def h_lockdown(s: Session, app: Application, inst: Institution) -> tuple[str, str]:
    inst.status = "lockdown"
    s.add(inst)
    raise_alert(s, kind="lockdown", severity="critical", institution_id=inst.id, application_id=app.id,
                title="Approval lockdown applied",
                message="Admissions and approval changes are frozen until inspection and review complete.")
    return "flagged", "Admissions + approval changes frozen; checks forced sequential"


def h_geo(s: Session, app: Application, inst: Institution) -> tuple[str, str]:
    sig = app.signals
    for p in sig.get("photos", []):
        if p["distance_km"] is None:
            _finding(s, app.id, "geo", "warn", f"No GPS in {p['file']}",
                     "Photo carries no EXIF location; capture must be done in the app.", p)
        elif p["distance_km"] > config.GEO_TOLERANCE_KM:
            _finding(s, app.id, "geo", "critical", f"{p['file']} taken {p['distance_km']} km from campus",
                     f"Registered campus is at {inst.lat:.4f}, {inst.lon:.4f}; photo GPS is "
                     f"{p['lat']:.4f}, {p['lon']:.4f}.", p)
    for mt in sig.get("photo_matches", []):
        _finding(s, app.id, "photo", "critical", f"{mt['file']} recycled from {mt['institution']}",
                 f"Perceptual hash within {mt['hamming']} bits of '{mt['their_file']}' submitted by "
                 f"{mt['institution']}.", mt)
    s.flush()
    found = _findings(s, app.id, "geo") + _findings(s, app.id, "photo")
    crit = [f for f in found if f.severity == "critical"]
    if crit:
        raise_alert(s, kind="geo_mismatch", severity="critical", institution_id=inst.id,
                    application_id=app.id, title=f"Photo evidence failed for {inst.name}",
                    message=f"{len(crit)} campus photo issue(s): GPS mismatch or recycled images.")
    n = len(sig.get("photos", []))
    return _state_for(found), (f"{n} photos verified on-site, none recycled" if not found
                               else f"{len(found)} issue(s) across {n} photos")


def h_finance(s: Session, app: Application, inst: Institution) -> tuple[str, str]:
    doc = app.signals.get("doc", {})
    fields = doc.get("fields", {})
    if not fields:
        _finding(s, app.id, "finance", "warn", "Financial statement unreadable",
                 "No figures could be extracted; routed for manual reading.")
    else:
        rules = {r["id"]: r for r in policy.load_policy()["rules"]}
        limit = rules["FIN-DEFICIT"]["value"]
        d = fields.get("deficit_pct")
        if d is not None and d > limit:
            _finding(s, app.id, "finance", "critical", f"Operating deficit {d:.1f}% of revenue",
                     f"Expenditure ₹{fields.get('expenditure_lakh')} lakh vs revenue "
                     f"₹{fields.get('revenue_lakh')} lakh; norm is ≤ {limit}%.", doc)
            raise_alert(s, kind="financial", severity="warn", institution_id=inst.id,
                        application_id=app.id, title=f"Financial stress at {inst.name}",
                        message=f"Deficit {d:.1f}% exceeds the {limit}% norm.")
        if doc.get("confidence", 1) < 0.75:
            _finding(s, app.id, "finance", "info", "Partial extraction",
                     f"{int(doc['confidence'] * 100)}% of expected fields found.", doc)
    s.flush()
    found = _findings(s, app.id, "finance")
    summary = ", ".join(f"{k.replace('_lakh', '')} ₹{v:,.0f}L" for k, v in fields.items()
                        if k.endswith("_lakh") and k != "salary_lakh")
    return _state_for(found), summary or "no fields"


def h_faculty(s: Session, app: Application, inst: Institution) -> tuple[str, str]:
    hits = app.signals.get("collisions", [])
    by_inst: dict[str, int] = {}
    for c in hits:
        by_inst[c["institution"]] = by_inst.get(c["institution"], 0) + 1
    for name, n in by_inst.items():
        _finding(s, app.id, "faculty", "critical", f"{n} faculty also on {name}'s roster",
                 "Identical blinded identity tokens: the same people are declared full-time at both "
                 "institutions. Raw identities were never stored or compared.",
                 {"institution": name, "count": n,
                  "tokens": [c["token"][:12] for c in hits if c["institution"] == name]})
    if hits:
        raise_alert(s, kind="faculty_collision", severity="critical", institution_id=inst.id,
                    application_id=app.id, title=f"Ghost faculty detected at {inst.name}",
                    message=f"{len({c['token'] for c in hits})} faculty tokens collide with "
                            f"{len(by_inst)} other institution(s).")
    s.flush()
    found = _findings(s, app.id, "faculty")
    total = app.metrics.get("faculty", 0)
    return _state_for(found), (f"{total} tokens, 0 collisions" if not hits
                               else f"{len({c['token'] for c in hits})} of {total} tokens collide")


def h_norms(s: Session, app: Application, inst: Institution) -> tuple[str, str]:
    results = policy.evaluate(app.metrics, policy.load_policy())
    failed = [r for r in results if r["passed"] is False]
    for r in failed:
        _finding(s, app.id, "norms", r["severity"], f"{r['id']}: {r['title']}",
                 f"Measured {r['measured']} {r['unit']}, required {'≤' if r['op'] == '<=' else '≥'} {r['value']}. {r['ref']}.",
                 {"rule": r["id"], "measured": r["measured"], "required": r["value"], "op": r["op"]})
    sig = dict(app.signals)
    sig["norms"] = results
    sig["plan"] = policy.remediation(app.metrics, results)
    app.signals = sig
    s.flush()
    return _state_for(_findings(s, app.id, "norms")), f"{len(results) - len(failed)}/{len(results)} rules pass"


def h_decision(s: Session, app: Application, inst: Institution) -> tuple[str, str]:
    crit = [f for f in _findings(s, app.id) if f.severity == "critical"]
    if crit:
        app.status = "awaiting_review"
        inst.status = "under_review"
        s.add(inst)
        raise_alert(s, kind="escalated", severity="warn", institution_id=inst.id, application_id=app.id,
                    title=f"Low-risk case escalated: {inst.name}",
                    message=f"{len(crit)} critical finding(s) blocked auto-ratification.")
        return "waiting", f"Escalated: {len(crit)} critical finding(s) need a regulator"
    app.status, app.decided_at, app.decided_by = "ratified", now(), "auto:batch-ratification"
    inst.status = "approved"
    s.add(inst)
    raise_alert(s, kind="approved", severity="info", institution_id=inst.id, application_id=app.id,
                title=f"{inst.name}: approval granted",
                message=f"Batch-ratified for {app.academic_year} with no human bottleneck.")
    return "passed", "All checks clean → ratified automatically"


def h_inspection(s: Session, app: Application, inst: Institution) -> tuple[str, str]:
    date = (now() + timedelta(days=5)).date().isoformat()
    app.inspection_date = date
    raise_alert(s, kind="inspection", severity="warn", institution_id=inst.id, application_id=app.id,
                title="Physical inspection scheduled",
                message=f"Expert visit committee assigned for {date}; geo-fenced app capture required.")
    return "passed", f"Expert visit on {date}"


def h_review(s: Session, app: Application, inst: Institution) -> tuple[str, str]:
    app.status = "awaiting_review"
    if inst.status != "lockdown":
        inst.status = "under_review"
        s.add(inst)
    n = len([f for f in _findings(s, app.id) if f.severity == "critical"])
    return "waiting", f"In regulator queue · {n} critical finding(s) attached"


def h_seal(s: Session, app: Application, inst: Institution) -> tuple[str, str]:
    entry = audit.append(s, "system", "case.sealed", f"application:{app.id}",
                         {"status": app.status, "tier": app.tier, "risk": app.risk_score,
                          "findings": len(_findings(s, app.id))})
    s.flush()
    cp = audit.latest_root(s)
    return "passed", f"Leaf #{entry.id} · signed root {cp.root[:16]}…"


HANDLERS = {
    "ingest": h_ingest, "risk": h_risk, "lockdown": h_lockdown, "geo": h_geo,
    "finance": h_finance, "faculty": h_faculty, "norms": h_norms, "decision": h_decision,
    "inspection": h_inspection, "review": h_review, "seal": h_seal,
}


# --- Runner ---------------------------------------------------------------------------

def _ready(nodes: list[WorkflowNode]) -> list[WorkflowNode]:
    state = {n.key: n.state for n in nodes}
    return [n for n in nodes if n.state == "pending" and all(state.get(d) in DONE for d in n.depends_on)]


def _duration(node: WorkflowNode, delay: float) -> float:
    """Each step takes delay * 0.7..1.3, fixed per node so every poll agrees."""
    return delay * (0.7 + 0.6 * ((node.id * 7919) % 100) / 100)


def _claim(s: Session, node_id: int, src: str, dst: str, **values) -> bool:
    """Move a node between states only if no one else did first."""
    res = s.execute(update(WorkflowNode).where(WorkflowNode.id == node_id)
                    .where(WorkflowNode.state == src).values(state=dst, **values))
    return res.rowcount == 1


def _execute(node_id: int) -> None:
    with session() as s:
        if not _claim(s, node_id, "running", "executing"):
            return
        node = s.get(WorkflowNode, node_id)
        s.refresh(node)
        app = s.get(Application, node.application_id)
        inst = s.get(Institution, app.institution_id)
        try:
            state, detail = HANDLERS[node.key](s, app, inst)
        except Exception as exc:          # a broken node must not kill the case
            state, detail = "failed", f"error: {exc}"
        node.state, node.detail = state, detail
        if state != "waiting":
            node.finished_at = now()
        s.add_all([node, app])
        audit.append(s, "workflow", f"node.{state}", f"application:{app.id}/{node.key}",
                     {"detail": detail})
        s.commit()


def advance(app_id: int, delay: float | None = None) -> None:
    """Finish the steps whose time is up, start the steps that are now ready.

    With no delay it loops until the case finishes or waits on a human.
    """
    delay = config.STEP_DELAY if delay is None else delay
    while True:
        with session() as s:
            nodes = _nodes(s, app_id)
        t = now()
        due = [n for n in nodes if n.state == "running"
               and (t - _aware(n.started_at)).total_seconds() >= _duration(n, delay)]
        for n in due:
            _execute(n.id)
        with session() as s:
            ready = _ready(_nodes(s, app_id))
            started = [n for n in ready if _claim(s, n.id, "pending", "running", started_at=now())]
            s.commit()
        if delay or not (due or started):
            return


def _aware(ts):
    from datetime import timezone
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def run_sync(app_id: int) -> None:
    """Run a case to completion (or to a human step) with no delays: seeding, scripts."""
    advance(app_id, delay=0)


def advance_active() -> None:
    """Advance every case that still has work in flight."""
    with session() as s:
        ids = s.exec(select(WorkflowNode.application_id)
                     .where(WorkflowNode.state.in_(["pending", "running"])).distinct()).all()
    for app_id in ids:
        advance(app_id)


def decide(s: Session, app: Application, approve: bool, actor: str, note: str = "") -> None:
    """A regulator's verdict on a case waiting in review (or escalated from batch)."""
    node = s.exec(select(WorkflowNode).where(WorkflowNode.application_id == app.id)
                  .where(WorkflowNode.state == "waiting")).first()
    if node is None:
        raise ValueError("case is not waiting for a decision")
    inst = s.get(Institution, app.institution_id)
    node.state = "passed" if approve else "failed"
    node.detail = f"{'Approved' if approve else 'Rejected'} by {actor}" + (f": {note}" if note else "")
    node.finished_at = now()
    app.status = "approved" if approve else "rejected"
    app.decided_at, app.decided_by, app.decision_note = now(), actor, note
    inst.status = "approved" if approve else "rejected"
    s.add_all([node, app, inst])
    audit.append(s, actor, "case.decided", f"application:{app.id}",
                 {"decision": app.status, "note": note})
    raise_alert(s, kind="decision", severity="info" if approve else "warn", institution_id=inst.id,
                application_id=app.id, title=f"{inst.name}: application {app.status}",
                message=note or f"Regulator decision recorded for {app.academic_year}.", actor=actor)
    s.commit()
