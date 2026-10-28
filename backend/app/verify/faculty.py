"""Faculty Collision Radar: find one person on two payrolls without storing who.

Each faculty identity (PAN + date of birth) is normalised and turned into
HMAC-SHA256 with a server-held pepper. Equal people give equal tokens, so a
token appearing under two institutions is a ghost-faculty signal, but the
token alone cannot be reversed or brute-forced without the pepper. Only
tokens are written to the database.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import re
from dataclasses import dataclass

from app import config


@dataclass
class FacultyRow:
    token: str
    designation: str
    qualification: str


def normalise(pan: str, dob: str) -> str:
    pan = re.sub(r"[^A-Z0-9]", "", pan.upper())
    digits = re.sub(r"\D", "", dob)
    if len(digits) == 8 and int(digits[:4]) > 1900:      # YYYYMMDD -> DDMMYYYY
        digits = digits[6:] + digits[4:6] + digits[:4]
    return f"{pan}|{digits}"


def token(pan: str, dob: str, key: bytes | None = None) -> str:
    key = key or config.FACULTY_HMAC_KEY
    return hmac.new(key, normalise(pan, dob).encode(), hashlib.sha256).hexdigest()


def parse_csv(data: bytes) -> list[FacultyRow]:
    """Tokenise a faculty roster. Columns: name, pan, dob, designation, qualification.

    The name is read and dropped on the spot; it is never returned.
    """
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    rows = []
    for r in reader:
        r = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k}
        if not r.get("pan"):
            continue
        rows.append(FacultyRow(token(r["pan"], r.get("dob", "")),
                               r.get("designation", ""), r.get("qualification", "")))
    return rows
