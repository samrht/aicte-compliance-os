"""Alerts, always written together with their audit entry."""
from __future__ import annotations

from sqlmodel import Session

from app import audit
from app.models import Alert


def raise_alert(s: Session, *, kind: str, severity: str, title: str, message: str,
                institution_id: int | None = None, application_id: int | None = None,
                actor: str = "system") -> Alert:
    alert = Alert(kind=kind, severity=severity, title=title, message=message,
                  institution_id=institution_id, application_id=application_id)
    s.add(alert)
    s.flush()
    audit.append(s, actor, "alert.raised", f"alert:{alert.id}",
                 {"kind": kind, "severity": severity, "title": title,
                  "institution_id": institution_id, "application_id": application_id})
    return alert
