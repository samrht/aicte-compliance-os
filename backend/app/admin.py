"""Administrator API: sign-in, live operating stats, document verification, demo reset.

Everything except sign-in requires a token from POST /api/admin/login.
"""
from __future__ import annotations

import re
import time
from collections import Counter
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, or_, text, update
from sqlmodel import Session, select

from app import audit, auth, config, dag
from app.db import get_session, rebuild, session
from app.events import raise_alert
from app.models import (AdminAccount, Alert, Application, AuditEntry, DemoLock, DocumentReview,
                        Institution, Upload, now)

router = APIRouter(prefix="/api/admin")

KIND_LABEL = {"photo": "Campus photo", "roster": "Faculty roster", "financials": "Financial statement"}


# --- Sign-in ------------------------------------------------------------------------

class Login(BaseModel):
    username: str
    password: str


@router.get("/config")
def admin_config() -> dict:
    """What the sign-in page may show: the demo account, only while it is in use."""
    return {"demo_account": {"username": auth.DEMO_USER, "password": auth.DEMO_PASSWORD}
            if auth.USING_DEMO_ACCOUNT else None}


@router.post("/login")
def login(body: Login) -> dict:
    username = body.username.strip().lower()
    who = None
    if auth.check_password(username, body.password):
        who = auth.ADMIN_USER
    else:
        with session() as s:
            acct = s.exec(select(AdminAccount).where(AdminAccount.username == username)).first()
        if acct and auth.verify_password(body.password, acct.password_hash):
            if acct.status == "pending":
                raise HTTPException(403, "Your account is waiting for an administrator to approve it.")
            if acct.status != "active":
                raise HTTPException(403, "This account has been disabled. Ask an administrator.")
            who = acct.username
    if who is None:
        time.sleep(0.5)                  # blunt password guessing a little
        raise HTTPException(401, "That username and password don't match an administrator.")
    token, exp = auth.issue_token(who)
    with session() as s:
        audit.append(s, f"admin:{who}", "admin.login", "admin", {})
        s.commit()
    return {"token": token, "expires": exp, "username": who}


class Signup(BaseModel):
    name: str
    username: str
    email: str
    password: str


USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.post("/signup")
def signup(body: Signup) -> dict:
    """Request an admin account. It stays pending until an active admin approves it."""
    username, name, email = body.username.strip().lower(), body.name.strip(), body.email.strip().lower()
    if not name:
        raise HTTPException(422, "Enter your full name.")
    if not USERNAME.match(username):
        raise HTTPException(422, "Usernames are 3 to 32 characters: lowercase letters, digits, dot, dash or underscore.")
    if not EMAIL.match(email):
        raise HTTPException(422, "Enter a valid email address.")
    pw = body.password
    if len(pw) < 8 or not re.search(r"[A-Za-z]", pw) or not re.search(r"[^A-Za-z]", pw):
        raise HTTPException(422, "Use at least 8 characters, with a letter and a number or symbol.")
    if auth.is_owner(username):
        raise HTTPException(409, "That username is taken.")
    with session() as s:
        if s.exec(select(AdminAccount).where(AdminAccount.username == username)).first():
            raise HTTPException(409, "That username is taken.")
        s.add(AdminAccount(username=username, name=name, email=email,
                           password_hash=auth.hash_password(pw)))
        audit.append(s, f"signup:{username}", "admin.signup_requested", f"admin:{username}", {"name": name})
        s.commit()
    return {"ok": True, "status": "pending"}


@router.get("/accounts")
def accounts(_: str = Depends(auth.require_admin), s: Session = Depends(get_session)) -> dict:
    rows = s.exec(select(AdminAccount).order_by(AdminAccount.created_at.desc())).all()
    return {
        "owner": auth.ADMIN_USER,
        "accounts": [{"id": a.id, "username": a.username, "name": a.name, "email": a.email,
                      "status": a.status, "created_at": a.created_at, "approved_by": a.approved_by,
                      "approved_at": a.approved_at} for a in rows],
    }


@router.post("/accounts/{account_id}/{action}")
def account_action(account_id: int, action: str, who: str = Depends(auth.require_admin)) -> dict:
    if action not in ("approve", "disable"):
        raise HTTPException(404, "Unknown action.")
    with session() as s:
        acct = s.get(AdminAccount, account_id)
        if acct is None:
            raise HTTPException(404, "No such account.")
        if acct.username == who and action == "disable":
            raise HTTPException(409, "You can't disable your own account.")
        acct.status = "active" if action == "approve" else "disabled"
        if action == "approve":
            acct.approved_by, acct.approved_at = who, now()
        s.add(acct)
        audit.append(s, f"admin:{who}", f"admin.account_{action}d", f"admin:{acct.username}", {})
        s.commit()
    return {"ok": True}


@router.get("/me")
def me(who: str = Depends(auth.require_admin)) -> dict:
    return {"username": who}


# --- Document checks ------------------------------------------------------------------

def checks_for(kind: str, filename: str, app: Application) -> list[dict]:
    """What the pipeline found about one document; `ok` None = not measured yet."""
    sig = app.signals or {}
    out: list[dict] = []
    if not sig:
        return [{"label": "Automatic checks", "ok": None, "detail": "Still being processed"}]
    if kind == "photo":
        p = next((x for x in sig.get("photos", []) if x["file"] == filename), None)
        if p is None:
            return [{"label": "Photo", "ok": None, "detail": "Not processed"}]
        if p["distance_km"] is None:
            out.append({"label": "Location", "ok": False, "detail": "No GPS in the photo"})
        else:
            near = p["distance_km"] <= config.GEO_TOLERANCE_KM
            out.append({"label": "Location", "ok": near,
                        "detail": f"Taken {p['distance_km']} km from the registered campus"})
        dupes = [m for m in sig.get("photo_matches", []) if m["file"] == filename]
        out.append({"label": "Originality", "ok": not dupes,
                    "detail": (f"Same image as {dupes[0]['their_file']} from {dupes[0]['institution']}"
                               if dupes else "Not seen in any other institution's submission")})
    elif kind == "roster":
        hits = sig.get("collisions", [])
        others = sorted({c["institution"] for c in hits})
        out.append({"label": "Faculty", "ok": True,
                    "detail": f"{app.metrics.get('faculty', 0)} faculty, {app.metrics.get('phd_pct', 0)}% PhD"})
        out.append({"label": "Shared faculty", "ok": not hits,
                    "detail": (f"{len({c['token'] for c in hits})} also on rosters of " + ", ".join(others))
                    if hits else "No faculty appear at another institution"})
        out.append({"label": "Privacy", "ok": True,
                    "detail": "Names and PANs were replaced by blinded tokens on arrival"})
    elif kind == "financials":
        doc = sig.get("doc", {})
        fields = doc.get("fields", {})
        conf = doc.get("confidence")
        out.append({"label": "Extraction", "ok": bool(fields) and (conf or 0) >= 0.75,
                    "detail": f"{len(fields)} figures read, confidence {int((conf or 0) * 100)}%"})
        d = fields.get("deficit_pct")
        if d is not None:
            out.append({"label": "Operating result", "ok": d <= 10,
                        "detail": f"{'Deficit' if d > 0 else 'Surplus'} of {abs(d):.1f}% of revenue (norm: deficit ≤ 10%)"})
        if "corpus_lakh" in fields:
            out.append({"label": "Corpus fund", "ok": fields["corpus_lakh"] >= 50,
                        "detail": f"₹{fields['corpus_lakh']:,.0f} lakh (norm ≥ ₹50 lakh)"})
    return out


def _verdict(checks: list[dict]) -> str:
    if any(c["ok"] is None for c in checks):
        return "processing"
    return "flagged" if any(c["ok"] is False for c in checks) else "clear"


def _doc_rows(s: Session) -> list[dict]:
    rows = s.exec(select(Upload.id, Upload.application_id, Upload.kind, Upload.filename,
                         func.length(Upload.data))).all()
    apps = {a.id: a for a in s.exec(select(Application)).all()}
    insts = {i.id: i for i in s.exec(select(Institution)).all()}
    reviews = {r.upload_id: r for r in s.exec(select(DocumentReview)).all()}
    out = []
    for up_id, app_id, kind, filename, size in rows:
        a = apps[app_id]
        inst = insts[a.institution_id]
        checks = checks_for(kind, filename, a)
        r = reviews.get(up_id)
        out.append({
            "id": up_id, "application_id": app_id, "kind": kind, "kind_label": KIND_LABEL.get(kind, kind),
            "filename": filename, "size": int(size or 0),
            "institution": {"id": inst.id, "name": inst.name, "code": inst.code, "city": inst.city},
            "application_status": a.status, "tier": a.tier, "submitted_at": a.submitted_at,
            "auto": _verdict(checks), "checks": checks,
            "review": None if r is None else {"status": r.status, "note": r.note,
                                              "reviewer": r.reviewer, "reviewed_at": r.reviewed_at},
        })
    out.sort(key=lambda d: (d["review"] is not None, d["auto"] != "flagged", -d["application_id"], d["id"]))
    return out


# --- Live stats -----------------------------------------------------------------------

@router.get("/stats")
def stats(_: str = Depends(auth.require_admin), s: Session = Depends(get_session)) -> dict:
    dag.advance_active()
    apps = s.exec(select(Application)).all()
    alerts = s.exec(select(Alert)).all()
    docs = _doc_rows(s)
    t = now()
    day0 = t.replace(hour=0, minute=0, second=0, microsecond=0)

    def aware(ts):
        from datetime import timezone
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)

    decided = [a for a in apps if a.decided_at]
    hours = [(aware(a.decided_at) - aware(a.submitted_at)).total_seconds() / 3600 for a in decided]
    per_day = Counter(aware(a.submitted_at).date().isoformat() for a in apps
                      if aware(a.submitted_at) >= day0 - timedelta(days=29))
    series = [{"day": (day0 - timedelta(days=i)).date().isoformat(),
               "count": per_day.get((day0 - timedelta(days=i)).date().isoformat(), 0)}
              for i in range(29, -1, -1)]

    t0 = time.perf_counter()
    for _ in range(3):
        s.execute(text("SELECT 1"))
    db_ms = round((time.perf_counter() - t0) * 1000 / 3, 1)
    log = audit.verify_log(s)
    recent = s.exec(select(AuditEntry).order_by(AuditEntry.id.desc()).limit(14)).all()

    pending = [d for d in docs if d["review"] is None]
    return {
        "generated_at": t,
        "applications": {
            "total": len(apps),
            "in_flight": sum(a.status == "running" for a in apps),
            "awaiting_review": sum(a.status == "awaiting_review" for a in apps),
            "submitted_today": sum(aware(a.submitted_at) >= day0 for a in apps),
            "decided_today": sum(aware(a.decided_at) >= day0 for a in decided),
            "avg_decision_hours": round(sum(hours) / len(hours), 1) if hours else None,
            "tiers": Counter(a.tier for a in apps if a.tier),
            "per_day": series,
        },
        "documents": {
            "total": len(docs),
            "pending": len(pending),
            "pending_flagged": sum(d["auto"] == "flagged" for d in pending),
            "verified": sum(d["review"] is not None and d["review"]["status"] == "verified" for d in docs),
            "rejected": sum(d["review"] is not None and d["review"]["status"] == "rejected" for d in docs),
            "by_kind": Counter(d["kind"] for d in pending),
        },
        "pending_accounts": len(s.exec(select(AdminAccount).where(AdminAccount.status == "pending")).all()),
        "alerts": {"open": sum(not a.acknowledged for a in alerts),
                   "critical": sum(not a.acknowledged and a.severity == "critical" for a in alerts)},
        "system": {"db_ms": db_ms, "region": __import__("os").environ.get("VERCEL_REGION") or "local",
                   "database": s.get_bind().dialect.name,
                   "audit_ok": log["ok"], "audit_size": log["size"],
                   "signed_root": log["signed_root"]},
        "activity": [{"id": e.id, "ts": e.ts, "actor": e.actor, "action": e.action, "entity": e.entity}
                     for e in recent],
    }


# --- Documents ------------------------------------------------------------------------

@router.get("/documents")
def documents(status: str = "pending", kind: Optional[str] = None,
              _: str = Depends(auth.require_admin), s: Session = Depends(get_session)) -> list[dict]:
    dag.advance_active()
    docs = _doc_rows(s)
    if status == "pending":
        docs = [d for d in docs if d["review"] is None]
    elif status in ("verified", "rejected"):
        docs = [d for d in docs if d["review"] and d["review"]["status"] == status]
    if kind:
        docs = [d for d in docs if d["kind"] == kind]
    return docs


@router.get("/documents/{upload_id}/file")
def document_file(upload_id: int, _: str = Depends(auth.require_admin),
                  s: Session = Depends(get_session)) -> Response:
    up = s.get(Upload, upload_id)
    if up is None:
        raise HTTPException(404, "No such document.")
    media = {"photo": "image/jpeg", "financials": "application/pdf", "roster": "text/csv"}.get(up.kind)
    if up.kind == "photo" and up.filename.lower().endswith(".png"):
        media = "image/png"
    # Headers must be Latin-1: send an ASCII fallback name plus the real one
    # percent-encoded (RFC 6266 / 5987), so names like "परिसर.jpg" don't crash.
    from urllib.parse import quote
    fallback = up.filename.encode("ascii", "ignore").decode().replace('"', "").replace("\\", "") or "document"
    disposition = f"inline; filename=\"{fallback}\"; filename*=UTF-8''{quote(up.filename, safe='')}"
    return Response(content=up.data, media_type=media or "application/octet-stream",
                    headers={"Cache-Control": "private, max-age=300", "Content-Disposition": disposition})


class Review(BaseModel):
    status: str          # verified | rejected
    note: str = ""


@router.post("/documents/{upload_id}/review")
def review_document(upload_id: int, body: Review, who: str = Depends(auth.require_admin)) -> dict:
    if body.status not in ("verified", "rejected"):
        raise HTTPException(422, "Status must be verified or rejected.")
    if body.status == "rejected" and not body.note.strip():
        raise HTTPException(422, "Say why the document is rejected; the institution sees this note.")
    with session() as s:
        up = s.get(Upload, upload_id)
        if up is None:
            raise HTTPException(404, "No such document.")
        app = s.get(Application, up.application_id)
        r = s.get(DocumentReview, upload_id) or DocumentReview(upload_id=upload_id, status=body.status,
                                                               reviewer=who)
        r.status, r.note, r.reviewer, r.reviewed_at = body.status, body.note.strip(), who, now()
        s.add(r)
        audit.append(s, f"admin:{who}", f"document.{body.status}", f"upload:{upload_id}",
                     {"application_id": app.id, "kind": up.kind, "file": up.filename, "note": r.note})
        if body.status == "rejected":
            raise_alert(s, kind="document", severity="warn", institution_id=app.institution_id,
                        application_id=app.id, actor=f"admin:{who}",
                        title=f"Document rejected: {up.filename}",
                        message=r.note or "Re-upload this document.")
        s.commit()
    return {"ok": True}


# --- Demo reset -------------------------------------------------------------------------

def _take_reset_lock() -> bool:
    """Claim the single DemoLock row for 5 minutes; False if a reset already holds it."""
    with session() as s:
        if s.get(DemoLock, 1) is None:
            s.add(DemoLock(id=1))
            try:
                s.commit()
            except Exception:
                s.rollback()
        t = now()
        res = s.execute(update(DemoLock).where(DemoLock.id == 1)
                        .where(or_(DemoLock.held_until.is_(None), DemoLock.held_until < t))
                        .values(held_until=t + timedelta(minutes=5)))
        s.commit()
        return res.rowcount == 1


def _release_reset_lock() -> None:
    with session() as s:
        lock = s.get(DemoLock, 1)
        if lock:
            lock.held_until = None
            s.add(lock)
            s.commit()


@router.post("/reset")
def reset_demo(who: str = Depends(auth.require_admin)) -> dict:
    """Empty the database and reseed the demo world. One at a time."""
    from app.seed import seed
    if not _take_reset_lock():
        raise HTTPException(409, "A reset is already running; it takes about 20 seconds.")
    try:
        rebuild(seed)
    finally:
        _release_reset_lock()
    with session() as s:
        audit.append(s, f"admin:{who}", "demo.reset", "database", {})
        s.commit()
    return {"ok": True}
