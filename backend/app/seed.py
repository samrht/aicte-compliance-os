"""Builds the demo world: 21 institutions with a processed history, two fresh
applicants, and the upload sets the demo video uses for those applicants.

Every seeded case goes through the real pipeline (ingestion, model, checks,
policy) with no delays, so nothing on screen is hand-written. Only the
regulator verdicts on review-tier cases, and the timestamps, are filled in.
"""
from __future__ import annotations

import json
import os
import random
import shutil
from datetime import timedelta
from pathlib import Path

from sqlmodel import select

from app import audit, config, dag, demo_data as dd
from app.db import init_db, session
from app.events import raise_alert
from app.models import (Alert, Application, AuditEntry, DocumentReview, Institution, Upload,
                        WorkflowNode, now)

DEMO_ASSETS = Path(os.environ.get("ACOS_DEMO_ASSETS", config.DATA / "demo-assets" if config.ON_VERCEL
                                  else config.BACKEND.parent / "demo-assets"))

PROFILES = {
    #             spf        phd    land       builtup     labs        deficit     corpus      prior
    "good":       ((14, 18), 0.32, (8, 25),   (8, 11),    (2.6, 3.4), (-8, 2),    (80, 200),  0),
    "borderline": ((20, 24), 0.10, (2.6, 4.5), (5.4, 6.8), (1.8, 2.3), (7, 12.5),  (40, 70),   2),
    "weak":       ((24, 28), 0.06, (2.0, 2.6), (4.5, 5.8), (1.5, 1.9), (12, 20),  (20, 40),   2),
}

# code, name, city, state, lat, lon, established, profile, extras
INSTITUTIONS = [
    ("AIT-JPR", "Aravalli Institute of Technology", "Jaipur", "Rajasthan", 26.9124, 75.7873, 1998, "good", {}),
    ("KNK-BBS", "Konark College of Engineering", "Bhubaneswar", "Odisha", 20.2961, 85.8245, 2001, "good", {}),
    ("NVC-BPL", "Narmada Valley College of Engineering", "Bhopal", "Madhya Pradesh", 23.2599, 77.4126, 2008, "borderline", {}),
    ("DPI-HYD", "Deccan Plateau Institute of Technology", "Hyderabad", "Telangana", 17.3850, 78.4867, 1995, "good", {}),
    ("KIE-CBE", "Kaveri Institute of Engineering Sciences", "Coimbatore", "Tamil Nadu", 11.0168, 76.9558, 1999, "good", {}),
    ("MIT-IDR", "Malwa Institute of Technology & Management", "Indore", "Madhya Pradesh", 22.7196, 75.8577, 2011, "borderline",
     {"borrow_from": "NVC-BPL", "borrow": 7, "geo_km": 24, "hold": True}),
    ("GIE-LKO", "Gomti Institute of Engineering", "Lucknow", "Uttar Pradesh", 26.8467, 80.9462, 2006, "borderline", {"hold": True}),
    ("BIT-GHY", "Brahmaputra Institute of Technology", "Guwahati", "Assam", 26.1445, 91.7362, 2003, "good", {}),
    ("VIE-RPR", "Vindhya Institute of Engineering", "Raipur", "Chhattisgarh", 21.2514, 81.6296, 2009, "weak", {}),
    ("WGI-COK", "Western Ghats Institute of Technology", "Kochi", "Kerala", 9.9312, 76.2673, 2000, "good", {}),
    ("SIE-DDN", "Shivalik Institute of Engineering", "Dehradun", "Uttarakhand", 30.3165, 78.0322, 2007, "borderline", {}),
    ("SIT-AMD", "Sabarmati Institute of Technology", "Ahmedabad", "Gujarat", 23.0225, 72.5714, 1997, "good", {}),
    ("GDI-KOL", "Ganga Delta Institute of Technology", "Kolkata", "West Bengal", 22.5726, 88.3639, 2004, "borderline", {}),
    ("OCI-NGP", "Orange City Institute of Engineering", "Nagpur", "Maharashtra", 21.1458, 79.0882, 2002, "good", {}),
    ("CIE-MYS", "Chamundi Institute of Engineering", "Mysuru", "Karnataka", 12.2958, 76.6394, 1996, "good", {}),
    ("CIT-MAA", "Coromandel Institute of Technology", "Chennai", "Tamil Nadu", 13.0827, 80.2707, 1994, "good", {}),
    ("MIE-PAT", "Magadh Institute of Engineering", "Patna", "Bihar", 25.5941, 85.1376, 2012, "weak",
     {"recycle_from": "KNK-BBS", "geo_km": 31}),
    ("CNC-RNC", "Chota Nagpur College of Engineering", "Ranchi", "Jharkhand", 23.3441, 85.3096, 2010, "weak", {"hold": True}),
    ("WIT-VTZ", "Waltair Institute of Technology", "Visakhapatnam", "Andhra Pradesh", 17.6868, 83.2185, 1999, "good", {}),
    ("TIE-IXC", "Tricity Institute of Engineering", "Chandigarh", "Chandigarh", 30.7333, 76.7794, 2005, "good", {}),
    ("MHI-BDQ", "Mahi Institute of Technology", "Vadodara", "Gujarat", 22.3072, 73.1812, 2006, "borderline", {}),
]

# Fresh applicants driven live in the demo video.
DEMO_APPLICANTS = [
    ("IIER-PNQ", "Indrayani Institute of Engineering & Research", "Pune", "Maharashtra", 18.5204, 73.8567, 2004),
    ("TDC-JPR", "Thar Desert College of Engineering & Technology", "Jaipur", "Rajasthan", 26.8500, 75.8000, 2014),
]
PREFILL = {
    "IIER-PNQ": {"students": 1440, "land_acres": 12.5, "builtup_sqm": 13680, "labs": 42},
    "TDC-JPR": {"students": 1320, "land_acres": 2.2, "builtup_sqm": 6900, "labs": 22},
}

_rosters: dict[str, list[dict]] = {}
_photos: dict[str, list[Path]] = {}


def _u(rng: random.Random, lo_hi: tuple[float, float]) -> float:
    return rng.uniform(*lo_hi)


def _evidence(rng: random.Random, code: str, name: str, lat: float, lon: float, profile: str, extras: dict,
              folder: Path) -> dict:
    spf, phd, land, builtup, labs, deficit, corpus, _ = PROFILES[profile]
    students = rng.choice([600, 720, 900, 1080, 1200, 1440, 1800, 2160])
    n_fac = max(12, round(students / _u(rng, spf)))
    borrowed = []
    if extras.get("borrow_from"):
        borrowed = rng.sample(_rosters[extras["borrow_from"]], extras["borrow"])
    rows = dd.roster(rng, n_fac, phd, borrowed)
    _rosters[code] = rows
    (folder / "faculty.csv").parent.mkdir(parents=True, exist_ok=True)
    (folder / "faculty.csv").write_bytes(dd.roster_csv(rows))

    paths = []
    for k in range(3):
        p = folder / "photos" / f"{code.lower()}_campus_{k + 1}.jpg"
        if k == 1 and extras.get("recycle_from"):
            src = _photos[extras["recycle_from"]][1]
            plat, plon = dd.offset_point(lat, lon, rng.uniform(0.05, 0.3), rng.uniform(0, 360))
            dd.recycle(src, p, plat, plon)
        else:
            km = extras["geo_km"] if (extras.get("geo_km") and k == 2) else rng.uniform(0.02, 0.4)
            plat, plon = dd.offset_point(lat, lon, km, rng.uniform(0, 360))
            dd.save_photo(dd.campus_photo(rng), p, plat, plon)
        paths.append(p)
    _photos[code] = paths

    revenue = round(students * rng.uniform(0.95, 1.25), 2)
    expenditure = round(revenue * (1 + _u(rng, deficit) / 100), 2)
    dd.financial_pdf(folder / "financials.pdf", name, revenue, expenditure, round(_u(rng, corpus), 2))
    return {"students": students, "land_acres": round(_u(rng, land), 2),
            "builtup_sqm": round(students * _u(rng, builtup)), "labs": round(students * _u(rng, labs) / 100)}


def seed(rng_seed: int = 2026) -> None:
    init_db()
    shutil.rmtree(config.SCRATCH, ignore_errors=True)
    config.ensure_dirs()
    rng = random.Random(rng_seed)
    _rosters.clear()
    _photos.clear()
    pending: list[tuple[int, str, dict]] = []
    with session() as s:
        audit.append(s, "system", "log.genesis", "audit", {"note": "AICTE Compliance OS audit log opened"})
        s.commit()

    for code, name, city, state, lat, lon, est, profile, extras in INSTITUTIONS:
        with session() as s:
            inst = Institution(code=code, name=name, city=city, state=state, lat=lat, lon=lon,
                               established=est, prior_violations=PROFILES[profile][7], status="pending")
            s.add(inst)
            s.flush()
            app = Application(institution_id=inst.id)
            s.add(app)
            s.flush()
            folder = config.SCRATCH / code
            declared = _evidence(rng, code, name, lat, lon, profile, extras, folder)
            for f in sorted((folder / "photos").glob("*.jpg")):
                s.add(Upload(application_id=app.id, kind="photo", filename=f.name, data=f.read_bytes()))
            s.add(Upload(application_id=app.id, kind="roster", filename="faculty.csv",
                         data=(folder / "faculty.csv").read_bytes()))
            s.add(Upload(application_id=app.id, kind="financials", filename="financials.pdf",
                         data=(folder / "financials.pdf").read_bytes()))
            app.metrics = declared
            dag.create_nodes(s, app)
            audit.append(s, f"institution:{code}", "application.submitted", f"application:{app.id}",
                         {"kind": app.kind, "photos": 3, "has_roster": True, "has_financials": True})
            s.commit()
            pending.append((app.id, profile, extras))
        dag.run_sync(app.id)

    # Regulator verdicts for review-tier cases, and plausible timestamps.
    for app_id, profile, extras in pending:
        with session() as s:
            app = s.get(Application, app_id)
            days_ago = rng.uniform(4, 75)
            app.submitted_at = now() - timedelta(days=days_ago)
            if app.status == "awaiting_review" and not extras.get("hold"):
                dag.decide(s, app, profile != "weak", "aicte:regional-officer",
                           "Inspection report reviewed." if profile != "weak"
                           else "Deficiencies not cured within the notice period.")
                app = s.get(Application, app_id)
            if app.decided_at:
                hours = {"low": rng.uniform(1.5, 30), "medium": rng.uniform(60, 260),
                         "high": rng.uniform(320, 900)}[app.tier]
                app.decided_at = app.submitted_at + timedelta(hours=hours)
            s.add(app)
            s.commit()
        dag.run_sync(app_id)          # seals cases that were just decided

    # Documents on cases already decided were verified along the way; the
    # three cases still in review leave theirs in the admin's queue.
    with session() as s:
        for app in s.exec(select(Application).where(Application.decided_at.is_not(None))).all():
            reviewer = "auto:batch-ratification" if app.status == "ratified" else "admin"
            for up in s.exec(select(Upload).where(Upload.application_id == app.id)).all():
                s.add(DocumentReview(upload_id=up.id, status="verified", reviewer=reviewer,
                                     reviewed_at=app.decided_at, note=""))
        s.commit()

    with session() as s:
        for code, name, city, state, lat, lon, est in DEMO_APPLICANTS:
            s.add(Institution(code=code, name=name, city=city, state=state, lat=lat, lon=lon,
                              established=est, status="new"))
        approved = s.exec(select(Institution).where(Institution.status == "approved")).all()
        for inst in approved[:3]:
            raise_alert(s, kind="deadline", severity="warn", institution_id=inst.id,
                        title="Annual compliance return due in 5 days",
                        message="Upload the mandatory disclosure and faculty roster update for 2026-27.",
                        actor="monitor:calendar")
        s.commit()
    build_demo_assets()


def build_demo_assets(root: Path = DEMO_ASSETS) -> None:
    """Upload sets for the two live applicants."""
    rng = random.Random(99)
    shutil.rmtree(root, ignore_errors=True)

    # Clean: on-campus photos, its own faculty, healthy books.
    code, name, _, _, lat, lon, _ = DEMO_APPLICANTS[0]
    clean = root / "1-clean-indrayani-pune"
    rows = dd.roster(rng, 88, 0.3)
    (clean / "faculty.csv").parent.mkdir(parents=True, exist_ok=True)
    (clean / "faculty.csv").write_bytes(dd.roster_csv(rows))
    for k in range(3):
        plat, plon = dd.offset_point(lat, lon, rng.uniform(0.05, 0.3), rng.uniform(0, 360))
        dd.save_photo(dd.campus_photo(rng), clean / "photos" / f"indrayani_campus_{k + 1}.jpg", plat, plon)
    dd.financial_pdf(clean / "financials.pdf", name, 1712.40, 1598.75, 140.00)
    (clean / "declared.json").write_text(json.dumps(PREFILL[code], indent=2))

    # Shady: borrowed faculty, a recycled lab photo, a photo shot 38 km away, a deficit.
    code, name, _, _, lat, lon, _ = DEMO_APPLICANTS[1]
    shady = root / "2-shady-thar-jaipur"
    borrowed = rng.sample(_rosters["AIT-JPR"], 4) + rng.sample(_rosters["MIT-IDR"], 2)
    rows = dd.roster(rng, 52, 0.05, borrowed)
    (shady / "faculty.csv").parent.mkdir(parents=True, exist_ok=True)
    (shady / "faculty.csv").write_bytes(dd.roster_csv(rows))
    plat, plon = dd.offset_point(lat, lon, 0.2, 40)
    dd.save_photo(dd.campus_photo(rng), shady / "photos" / "thar_campus_1.jpg", plat, plon)
    plat, plon = dd.offset_point(lat, lon, 0.1, 200)
    dd.recycle(_photos["AIT-JPR"][1], shady / "photos" / "thar_lab_2.jpg", plat, plon)
    plat, plon = dd.offset_point(lat, lon, 38, 120)
    dd.save_photo(dd.campus_photo(rng), shady / "photos" / "thar_building_3.jpg", plat, plon)
    dd.financial_pdf(shady / "financials.pdf", name, 1180.00, 1392.40, 22.50)
    (shady / "declared.json").write_text(json.dumps(PREFILL[code], indent=2))

    (root / "README.txt").write_text(
        "Demo upload sets (all data fictional).\n\n"
        "1-clean-indrayani-pune  -> log in as Indrayani Institute; expect LOW risk, parallel checks, auto-ratified.\n"
        "2-shady-thar-jaipur     -> log in as Thar Desert College; expect HIGH risk, lockdown, ghost faculty\n"
        "                           (shared with Aravalli + Malwa), recycled lab photo, 38 km GPS mismatch, deficit.\n"
        "Declared figures for the wizard are in each folder's declared.json (the form pre-fills them).\n")


if __name__ == "__main__":
    from app.db import reset_db
    init_db()
    reset_db()
    seed()
    with session() as s:
        for i in s.exec(select(Institution)).all():
            print(f"{i.code:9s} {i.status:13s} {i.risk_tier or '-':7s} {i.risk_score or 0:.2f}  {i.name}")
        print("audit entries:", len(s.exec(select(AuditEntry)).all()),
              "alerts:", len(s.exec(select(Alert)).all()),
              "waiting:", len(s.exec(select(WorkflowNode).where(WorkflowNode.state == "waiting")).all()))
