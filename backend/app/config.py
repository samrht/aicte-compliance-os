"""Paths and tunables. Everything a demo operator might change lives here."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("ACOS_DATA", BACKEND / "data"))
UPLOADS = DATA / "uploads"
DB_URL = f"sqlite:///{DATA / 'app.db'}"
MODEL_PATH = DATA / "risk_model.txt"
AUDIT_KEY_PATH = DATA / "audit_ed25519.pem"

# Pepper for faculty identity tokens. In production this lives in a KMS and
# never leaves it; the prototype reads it from the environment.
FACULTY_HMAC_KEY = os.environ.get("FACULTY_HMAC_KEY", "acos-demo-pepper-rotate-me").encode()

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
    UPLOADS.mkdir(parents=True, exist_ok=True)
