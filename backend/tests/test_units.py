import random

import pytest

from app import audit, policy, risk
from app.demo_data import campus_photo, offset_point, recycle, save_photo
from app.verify import faculty, photos


# --- Merkle log -------------------------------------------------------------------

@pytest.mark.parametrize("n", [1, 2, 3, 5, 8, 13, 21])
def test_every_inclusion_proof_verifies(n):
    leaves = [audit.leaf_hash(f"entry-{i}".encode()) for i in range(n)]
    r = audit.root(leaves)
    for i in range(n):
        assert audit.verify_inclusion(i, n, leaves[i], audit.inclusion_proof(i, leaves), r)


def test_proof_fails_for_altered_leaf():
    leaves = [audit.leaf_hash(f"entry-{i}".encode()) for i in range(7)]
    r = audit.root(leaves)
    forged = audit.leaf_hash(b"entry-3-forged")
    assert not audit.verify_inclusion(3, 7, forged, audit.inclusion_proof(3, leaves), r)


# --- Faculty tokens -----------------------------------------------------------------

def test_token_ignores_formatting_but_not_identity():
    a = faculty.token("abcpd1234x", "05-03-1980")
    assert a == faculty.token("ABCPD 1234 X", "05/03/1980")
    assert a == faculty.token("ABCPD1234X", "1980-03-05")
    assert a != faculty.token("ABCPD1234Y", "05-03-1980")


def test_token_depends_on_pepper():
    assert faculty.token("ABCPD1234X", "05-03-1980", b"k1") != faculty.token("ABCPD1234X", "05-03-1980", b"k2")


def test_roster_parsing_keeps_no_names():
    csv = b"name,pan,dob,designation,qualification\nRavi Kumar,ABCPD1234X,05-03-1980,Professor,PhD\n"
    rows = faculty.parse_csv(csv)
    assert len(rows) == 1 and "Ravi" not in repr(rows[0]) and len(rows[0].token) == 64


# --- Photos -------------------------------------------------------------------------

def test_gps_round_trip_and_distance(tmp_path):
    lat, lon = 26.9124, 75.7873
    p = tmp_path / "a.jpg"
    save_photo(campus_photo(random.Random(1)), p, *offset_point(lat, lon, 5.0, 90))
    info = photos.inspect(p)
    assert info.lat is not None
    assert photos.haversine_km(lat, lon, info.lat, info.lon) == pytest.approx(5.0, abs=0.1)


def test_recycled_photo_matches_and_distinct_photos_do_not(tmp_path):
    rng = random.Random(3)
    hashes = []
    for i in range(12):
        p = tmp_path / f"p{i}.jpg"
        save_photo(campus_photo(rng), p, None, None)
        hashes.append(photos.inspect(p).phash)
    pairs = [photos.hamming(a, b) for i, a in enumerate(hashes) for b in hashes[i + 1:]]
    assert min(pairs) > 8, "independent campus photos must not collide"
    recycle(tmp_path / "p0.jpg", tmp_path / "copy.jpg", 10.0, 70.0)
    assert photos.hamming(hashes[0], photos.inspect(tmp_path / "copy.jpg").phash) <= 8


# --- Policy -----------------------------------------------------------------------------

GOOD = {"students": 1200, "faculty": 80, "phd_count": 20, "students_per_faculty": 15, "phd_pct": 25,
        "land_acres": 10, "builtup_sqm_per_student": 9, "labs_per_100": 3, "labs": 36,
        "deficit_pct": -2, "corpus_lakh": 120, "revenue_lakh": 1300}


def test_good_institution_is_compliant():
    assert policy.compliant(policy.evaluate(GOOD, policy.load_policy()))


def test_ratio_breach_gets_cheapest_plan():
    m = GOOD | {"faculty": 50, "students_per_faculty": 24}
    res = policy.evaluate(m, policy.load_policy())
    assert not policy.compliant(res)
    plan = policy.remediation(m, res)
    fix = next(p for p in plan if p["rule"] == "FAC-RATIO")
    assert fix["best"]["cost_lakh"] == min(o["cost_lakh"] for o in fix["options"])
    assert "Recruit 10 faculty" in [o["action"] for o in fix["options"]]


def test_sandbox_reports_flips():
    insts = [{"id": 1, "name": "A", "code": "A", "state": "X", "metrics": GOOD | {"students_per_faculty": 18}}]
    out = policy.simulate(insts, {"FAC-RATIO": 15})
    assert out["compliant_before"] == 1 and out["compliant_after"] == 0
    assert out["flips"][0]["flip"] == "newly_non_compliant"
    assert "deny contains msg" in out["rego"]


# --- Risk model ---------------------------------------------------------------------------

def test_model_separates_clean_from_fraud():
    m = risk.model()
    assert m.auc is None or m.auc > 0.75
    clean = risk.features_from(GOOD, {}, 0, 2000)
    fraud = risk.features_from(GOOD | {"students_per_faculty": 26, "deficit_pct": 18},
                               {"photo_flags": 1, "faculty_collisions": 6, "geo_max_km": 38}, 1, 2014)
    a, b = m.score(clean), m.score(fraud)
    assert a.tier == "low" and b.tier == "high"
    assert b.contributions[0]["impact"] > 0


def test_more_collisions_never_lower_risk():
    m = risk.model()
    base = risk.features_from(GOOD, {}, 0, 2000)
    ps = [m.score(base | {"faculty_collisions": k}).probability for k in range(6)]
    assert ps == sorted(ps)
