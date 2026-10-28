"""Financial statement extraction.

The prototype reads the PDF's text layer and pulls labelled figures with
patterns. The interface (PDF in, named fields with provenance out) is the
one a LayoutLMv3 key-value model plugs into for scanned statements.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from pypdf import PdfReader

FIELDS = {
    "revenue_lakh": r"total\s+(?:revenue|income|receipts)",
    "expenditure_lakh": r"total\s+(?:expenditure|expenses|payments)",
    "corpus_lakh": r"corpus\s+fund",
    "salary_lakh": r"salar(?:y|ies)",
}
NUMBER = r"[^\d\n]{0,40}?([\d,]+(?:\.\d+)?)"


def extract_text(src: Path | bytes) -> str:
    reader = PdfReader(io.BytesIO(src) if isinstance(src, bytes) else str(src))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract(src: Path | bytes) -> dict:
    text = extract_text(src)
    out: dict = {"fields": {}, "provenance": {}}
    for name, label in FIELDS.items():
        m = re.search(label + NUMBER, text, flags=re.IGNORECASE)
        if m:
            out["fields"][name] = float(m.group(1).replace(",", ""))
            out["provenance"][name] = m.group(0).strip().replace("\n", " ")
    f = out["fields"]
    if f.get("revenue_lakh") and "expenditure_lakh" in f:
        f["deficit_pct"] = round((f["expenditure_lakh"] - f["revenue_lakh"]) / f["revenue_lakh"] * 100, 2)
    out["confidence"] = round(len([k for k in FIELDS if k in f]) / len(FIELDS), 2)
    return out
