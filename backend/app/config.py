"""Paths and tunables. Everything a demo operator might change lives here."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ON_VERCEL = bool(os.environ.get("VERCEL"))

# Serverless file systems are read-only apart from the temp dir.
_default_data = Path(tempfile.gettempdir()) / "acos" if ON_VERCEL else BACKEND / "data"
DATA = Path(os.environ.get("ACOS_DATA", _default_data))
SCRATCH = DATA / "scratch"
AUDIT_KEY_PATH = DATA / "audit_ed25519.pem"


def _db_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if not url:
        return f"sqlite:///{DATA / 'app.db'}"
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DB_URL = _db_url()

# Pepper for faculty identity tokens. In production this lives in a KMS and
# never leaves it; the prototype reads it from the environment.
FACULTY_HMAC_KEY = os.environ.get("FACULTY_HMAC_KEY", "acos-demo-pepper-rotate-me").encode()

# Ed25519 audit signing key as 64 hex chars (32-byte seed). Unset: a key file in DATA.
AUDIT_SIGNING_KEY = os.environ.get("AUDIT_SIGNING_KEY")

# Seconds each workflow node takes, so the DAG visibly advances on screen.
STEP_DELAY = float(os.environ.get("DAG_STEP_DELAY", "1.4"))

# Risk tiers on the model's failure probability.
LOW_MAX = 0.30
MEDIUM_MAX = 0.60

# Verification thresholds.
GEO_TOLERANCE_KM = 1.0       # photo further than this from campus is a mismatch
PHASH_MAX_DISTANCE = 8       # Hamming distance at or below = same photo


def ensure_dirs() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
