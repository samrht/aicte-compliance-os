"""End to end: seed, submit both demo upload sets, decide, then attack the audit log."""
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

ASSETS = Path(os.environ["ACOS_DEMO_ASSETS"])


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _inst(client, code):
    return next(i for i in client.get("/api/institutions").json() if i["code"] == code)


def _submit(client, code, folder):
    inst = _inst(client, code)
    d = ASSETS / folder
    declared = json.loads((d / "declared.json").read_text())
    files = [("photos", (p.name, p.read_bytes(), "image/jpeg")) for p in sorted((d / "photos").glob("*.jpg"))]
    files += [("faculty_csv", ("faculty.csv", (d / "faculty.csv").read_bytes(), "text/csv")),
              ("financials", ("financials.pdf", (d / "financials.pdf").read_bytes(), "application/pdf"))]
    r = client.post("/api/applications", data={"institution_id": inst["id"], **declared}, files=files)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _settle(client, app_id, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        a = client.get(f"/api/applications/{app_id}").json()
        if a["status"] != "running":
            return a
        time.sleep(0.1)
    raise AssertionError(f"case {app_id} still running")


def test_seeded_world(client):
    d = client.get("/api/dashboard").json()
    assert d["institutions"] == 23 and d["awaiting_review"] >= 2
    assert set(d["tiers"]) == {"low", "medium", "high"}


def test_clean_college_is_auto_ratified(client):
    a = _settle(client, _submit(client, "IIER-PNQ", "1-clean-indrayani-pune"))
    assert a["tier"] == "low" and a["status"] == "ratified", a
    assert not [f for f in a["findings"] if f["severity"] == "critical"]
    states = {n["key"]: n["state"] for n in a["nodes"]}
    assert states["decision"] == "passed" and states["seal"] == "passed"


def test_shady_college_is_locked_down_with_evidence(client):
    a = _settle(client, _submit(client, "TDC-JPR", "2-shady-thar-jaipur"))
    assert a["tier"] == "high" and a["status"] == "awaiting_review"
    assert a["institution"]["status"] == "lockdown"
    cats = {f["category"] for f in a["findings"] if f["severity"] == "critical"}
    assert {"faculty", "photo", "geo", "finance"} <= cats
    faculty = [f for f in a["findings"] if f["category"] == "faculty"]
    assert {f["evidence"]["institution"] for f in faculty} == {
        "Aravalli Institute of Technology", "Malwa Institute of Technology & Management"}
    keys = [n["key"] for n in a["nodes"]]
    assert keys.index("lockdown") < keys.index("geo") < keys.index("review")

    radar = client.get("/api/collisions").json()
    assert any(n["code"] == "TDC-JPR" for n in radar["nodes"])

    r = client.post(f"/api/applications/{a['id']}/decision", json={"approve": False, "note": "Ghost faculty"})
    assert r.status_code == 200
    for _ in range(50):
        a = client.get(f"/api/applications/{a['id']}").json()
        if all(n["state"] in ("passed", "flagged", "failed") for n in a["nodes"]):
            break
        time.sleep(0.1)
    assert a["status"] == "rejected"
    assert {n["key"]: n["state"] for n in a["nodes"]}["seal"] == "passed"


def test_audit_log_detects_and_survives_tampering(client):
    assert client.post("/api/audit/verify").json()["ok"]
    entries = client.get("/api/audit").json()["entries"]
    target = next(e for e in entries if e["action"] == "case.decided")
    proof = client.get(f"/api/audit/proof/{target['id']}").json()
    assert proof["verified"]

    client.post(f"/api/audit/tamper/{target['id']}")
    report = client.post("/api/audit/verify").json()
    assert not report["ok"] and report["tampered"] == [target["id"]]
    assert not client.get(f"/api/audit/proof/{target['id']}").json()["verified"]

    client.post("/api/audit/restore")
    assert client.post("/api/audit/verify").json()["ok"]


def test_sandbox_and_sweep(client):
    out = client.post("/api/sandbox/simulate", json={"overrides": {"FAC-RATIO": 15}}).json()
    assert out["compliant_after"] < out["compliant_before"] and out["flips"]
    assert client.post("/api/monitor/sweep").status_code == 200


def _admin(client):
    r = client.post("/api/admin/login", json={"username": "admin", "password": "aicte-admin-2026"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_second_reset_is_refused_while_one_runs(client):
    from app.admin import _release_reset_lock, _take_reset_lock
    headers = _admin(client)
    assert _take_reset_lock()
    try:
        r = client.post("/api/admin/reset", headers=headers)
        assert r.status_code == 409
    finally:
        _release_reset_lock()


def test_admin_routes_need_a_valid_token(client):
    assert client.post("/api/admin/login", json={"username": "admin", "password": "nope"}).status_code == 401
    for path in ("/api/admin/stats", "/api/admin/documents"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer forged.token"}).status_code == 401
    assert client.post("/api/admin/reset").status_code == 401


def test_admin_stats_and_document_review(client):
    h = _admin(client)
    st = client.get("/api/admin/stats", headers=h).json()
    assert st["documents"]["pending"] > 0 and st["system"]["audit_ok"]
    docs = client.get("/api/admin/documents", headers=h).json()
    roster = next(d for d in docs if d["kind"] == "roster")
    body = client.get(f"/api/admin/documents/{roster['id']}/file", headers=h).text
    assert body.startswith("faculty_token,designation,qualification")   # names and PANs gone
    photo = next(d for d in docs if d["kind"] == "photo")
    assert client.post(f"/api/admin/documents/{photo['id']}/review", headers=h,
                       json={"status": "rejected", "note": ""}).status_code == 422
    assert client.post(f"/api/admin/documents/{photo['id']}/review", headers=h,
                       json={"status": "rejected", "note": "Blurred; retake on site"}).status_code == 200
    rejected = client.get("/api/admin/documents?status=rejected", headers=h).json()
    assert any(d["id"] == photo["id"] for d in rejected)
    after = client.get("/api/admin/stats", headers=h).json()
    assert after["documents"]["rejected"] == st["documents"]["rejected"] + 1
    assert client.post("/api/audit/verify").json()["ok"]
