"""Database tables. JSON columns hold the parts whose shape varies by case."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Column, LargeBinary
from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.now(timezone.utc)


class Institution(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(index=True, unique=True)
    name: str
    city: str
    state: str
    lat: float
    lon: float
    kind: str = "Engineering"
    established: int = 2005
    prior_violations: int = 0
    # approved | pending | under_review | lockdown | rejected | new
    status: str = "new"
    risk_score: Optional[float] = None
    risk_tier: Optional[str] = None
    # Latest declared + verified metrics; what the policy engine evaluates.
    metrics: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class Application(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key="institution.id", index=True)
    kind: str = "Extension of Approval"
    academic_year: str = "2027-28"
    # running | awaiting_review | ratified | approved | rejected
    status: str = "running"
    tier: Optional[str] = None
    risk_score: Optional[float] = None
    submitted_at: datetime = Field(default_factory=now)
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None
    decision_note: Optional[str] = None
    inspection_date: Optional[str] = None
    metrics: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    signals: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    contributions: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))


class WorkflowNode(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)
    key: str
    label: str
    seq: int = 0
    lane: int = 0
    # pending | running | passed | flagged | failed | waiting | skipped
    state: str = "pending"
    depends_on: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    detail: str = ""
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class Finding(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)
    category: str       # geo | photo | finance | faculty | norms
    severity: str       # info | warn | critical
    title: str
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class Alert(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: Optional[int] = Field(default=None, foreign_key="institution.id", index=True)
    application_id: Optional[int] = Field(default=None, foreign_key="application.id")
    kind: str
    severity: str       # info | warn | critical
    title: str
    message: str
    created_at: datetime = Field(default_factory=now)
    acknowledged: bool = False


class FacultyToken(SQLModel, table=True):
    """A blinded faculty identity. The raw ID never reaches this table."""
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key="institution.id", index=True)
    application_id: Optional[int] = Field(default=None, foreign_key="application.id")
    token: str = Field(index=True)
    designation: str = ""
    qualification: str = ""


class PhotoHash(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key="institution.id", index=True)
    application_id: Optional[int] = Field(default=None, foreign_key="application.id")
    filename: str
    phash: str
    lat: Optional[float] = None
    lon: Optional[float] = None


class AuditEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=now)
    actor: str
    action: str
    entity: str
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    leaf_hash: str = ""


class SignedRoot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tree_size: int = Field(index=True)
    root: str
    signature: str
    ts: datetime = Field(default_factory=now)


class Upload(SQLModel, table=True):
    """Evidence files, kept in the database so any server instance can process them."""
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)
    kind: str           # photo | roster | financials
    filename: str
    data: bytes = Field(sa_column=Column(LargeBinary, nullable=False))


class TamperBackup(SQLModel, table=True):
    """Demo only: the original payload of an audit row the tamper button edited."""
    entry_id: int = Field(primary_key=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
