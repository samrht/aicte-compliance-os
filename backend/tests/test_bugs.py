"""Regression tests for bugs found by probing the API with bad input."""
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

ASSETS = Path(os.environ["ACOS_DEMO_ASSETS"])
CLEAN = ASSETS / "1-clean-indrayani-pune"
FIGURES = {"students": 1440, "land_acres": 12.5, "builtup_sqm": 13680, "labs": 42}


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def admin_headers(client):
    tok = client.post("/api/admin/login", json={"username": "admin", "password": "Test@123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _inst(client, code):
    return next(i for i in client.get("/api/institutions").json() if i["code"] == code)


def _settle(client, app_id):
    for _ in range(200):
        a = client.get(f"/api/applications/{app_id}").json()
        if a["status"] != "running":
            return a
        time.sleep(0.05)
    return a


def test_failed_step_sends_case_to_a_human_instead_of_approving(client):
    """A PDF uploaded as a photo crashes ingestion; the case must not be auto-ratified."""
    inst = _inst(client, "KNK-BBS")
    files = [("photos", ("campus.jpg", (CLEAN / "financials.pdf").read_bytes(), "image/jpeg")),
             ("faculty_csv", ("faculty.csv", (CLEAN / "faculty.csv").read_bytes(), "text/csv")),
             ("financials", ("financials.pdf", (CLEAN / "financials.pdf").read_bytes(), "application/pdf"))]
    r = client.post("/api/applications", data={"institution_id": inst["id"], **FIGURES}, files=files)
    a = _settle(client, r.json()["id"])
    states = {n["key"]: n["state"] for n in a["nodes"]}
    assert states["ingest"] == "failed"
    assert a["status"] == "awaiting_review", a["status"]
    assert "waiting" in states.values()
    assert any(al["kind"] == "processing_error" for al in a["alerts"])
    # A regulator can still close it, and the case is sealed.
    assert client.post(f"/api/applications/{a['id']}/decision", json={"approve": False, "note": "Re-upload"}).status_code == 200
    a = _settle(client, a["id"])
    for _ in range(50):
        a = client.get(f"/api/applications/{a['id']}").json()
        if {n["key"]: n["state"] for n in a["nodes"]}.get("seal") == "passed":
            break
        time.sleep(0.05)
    assert a["status"] == "rejected"
    assert {n["key"]: n["state"] for n in a["nodes"]}["seal"] == "passed"


def test_non_ascii_filename_downloads(client, admin_headers):
    inst = _inst(client, "DPI-HYD")
    photo = next((ASSETS / "2-shady-thar-jaipur" / "photos").glob("*.jpg")).read_bytes()
    r = client.post("/api/applications", data={"institution_id": inst["id"], **FIGURES},
                    files=[("photos", ('परिसर "main".jpg', photo, "image/jpeg"))])
    _settle(client, r.json()["id"])
    docs = client.get("/api/admin/documents?status=all", headers=admin_headers).json()
    doc = next(d for d in docs if d["filename"].startswith("परिसर"))
    f = client.get(f"/api/admin/documents/{doc['id']}/file", headers=admin_headers)
    assert f.status_code == 200
    assert f.content == photo


@pytest.mark.parametrize("code", ["GIE-LKO", "CNC-RNC"])   # under review; in lockdown
def test_no_second_application_while_one_is_open(client, code):
    inst = _inst(client, code)
    before = inst["status"]
    r = client.post("/api/applications", data={"institution_id": inst["id"], **FIGURES})
    assert r.status_code == 409
    assert _inst(client, code)["status"] == before


@pytest.mark.parametrize("field,value", [("students", 0), ("students", -100), ("land_acres", -5),
                                         ("builtup_sqm", -1), ("labs", -3)])
def test_impossible_figures_rejected(client, field, value):
    inst = _inst(client, "SIT-AMD")
    r = client.post("/api/applications", data={"institution_id": inst["id"], **(FIGURES | {field: value})})
    assert r.status_code == 422
