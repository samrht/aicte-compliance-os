"""Compliance-failure risk scorer.

A LightGBM classifier trained on synthetic past institutions (real AICTE
outcome data is not public). Monotone constraints keep the model honest:
more students per faculty can never lower risk, more land can never raise
it. Per-case explanations are exact TreeSHAP values.

Training needs LightGBM and runs locally (`python -m app.risk.train`); it
exports the trees to `model.json`, which `trees.py` evaluates with no native
code so the scorer also runs on serverless hosts.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app import config
from app.risk.trees import TreeEnsemble

MODEL_JSON = Path(__file__).with_name("model.json")

FEATURES = [
    "students_per_faculty",
    "land_acres",
    "builtup_sqm_per_student",
    "labs_per_100",
    "deficit_pct",
    "phd_pct",
    "photo_flags",
    "faculty_collisions",
    "geo_mismatch_km",
    "prior_violations",
    "years_operating",
]

LABELS = {
    "students_per_faculty": "Students per faculty",
    "land_acres": "Land (acres)",
    "builtup_sqm_per_student": "Built-up m² per student",
    "labs_per_100": "Labs per 100 students",
    "deficit_pct": "Financial deficit %",
    "phd_pct": "PhD faculty %",
    "photo_flags": "Recycled campus photos",
    "faculty_collisions": "Faculty shared with other colleges",
    "geo_mismatch_km": "Photo GPS distance from campus (km)",
    "prior_violations": "Prior violations",
    "years_operating": "Years operating",
}

# +1: higher value can only raise risk; -1: can only lower it.
MONOTONE = [1, -1, -1, -1, 1, -1, 1, 1, 1, 1, -1]


def synthetic_history(n: int = 2400, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """Plausible institutions and whether they later failed inspection."""
    rng = np.random.default_rng(seed)
    spf = rng.normal(18, 5, n).clip(8, 45)
    land = rng.gamma(4, 2.2, n).clip(0.5, 60)
    builtup = rng.normal(8, 2.5, n).clip(1.5, 18)
    labs = rng.normal(2.6, 0.9, n).clip(0.3, 6)
    deficit = (rng.normal(2, 8, n)).clip(-20, 45)
    phd = rng.normal(22, 10, n).clip(0, 70)
    fraud = rng.random(n) < 0.12
    photo_flags = np.where(fraud, rng.poisson(1.6, n), rng.poisson(0.05, n))
    collisions = np.where(fraud, rng.poisson(2.5, n), rng.poisson(0.08, n))
    geo = np.where(fraud & (rng.random(n) < 0.6), rng.gamma(2, 15, n), rng.exponential(0.2, n))
    prior = rng.poisson(0.4, n) + fraud * rng.poisson(1.0, n)
    years = rng.integers(1, 60, n)

    z = (
        -3.2
        + 0.16 * (spf - 20).clip(0)
        + 0.35 * (2.5 - land).clip(0)
        + 0.30 * (6 - builtup).clip(0)
        + 0.8 * (2 - labs).clip(0)
        + 0.13 * (deficit - 5).clip(0)
        + 0.05 * (10 - phd).clip(0)
        + 1.3 * photo_flags
        + 1.1 * collisions
        + 0.9 * np.log1p(geo)
        + 0.6 * prior
        - 0.01 * years
    )
    y = rng.random(n) < 1 / (1 + np.exp(-z))
    X = np.column_stack([spf, land, builtup, labs, deficit, phd, photo_flags,
                         collisions, geo, prior, years]).astype(float)
    return X, y.astype(int)


@dataclass
class RiskResult:
    probability: float
    tier: str
    contributions: list[dict]     # [{feature, label, value, impact}] sorted by |impact|
    base: float                   # model log-odds before any feature


def tier_for(p: float) -> str:
    if p < config.LOW_MAX:
        return "low"
    if p < config.MEDIUM_MAX:
        return "medium"
    return "high"


def auc(y: np.ndarray, p: np.ndarray) -> float:
    """Area under the ROC curve via the rank-sum identity."""
    order = np.argsort(p)
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    pos = y == 1
    n1, n0 = pos.sum(), (~pos).sum()
    return float((ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def train(seed: int = 7) -> dict:
    """Fit on synthetic history; returns {"auc", "model"} with the tree dump. Needs lightgbm."""
    import lightgbm as lgb

    X, y = synthetic_history(seed=seed)
    split = int(len(y) * 0.8)
    params = dict(objective="binary", learning_rate=0.05, num_leaves=15,
                  min_data_in_leaf=25, monotone_constraints=MONOTONE,
                  feature_fraction=0.9, verbose=-1, seed=seed)
    booster = lgb.train(params, lgb.Dataset(X[:split], y[:split], feature_name=FEATURES),
                        num_boost_round=250)
    return {"auc": round(auc(y[split:], booster.predict(X[split:])), 4), "model": booster.dump_model()}


class RiskModel:
    def __init__(self, ensemble: TreeEnsemble, auc: float | None = None):
        self.ensemble = ensemble
        self.auc = auc

    @classmethod
    def load(cls, path: Path = MODEL_JSON) -> "RiskModel":
        if not path.exists():
            path.write_text(json.dumps(train()))
        data = json.loads(path.read_text())
        return cls(TreeEnsemble(data["model"]), data.get("auc"))

    def score(self, features: dict[str, float]) -> RiskResult:
        row = [float(features.get(f, 0.0)) for f in FEATURES]
        p = self.ensemble.probability(row)
        contrib = self.ensemble.contributions(row)
        items = [
            {"feature": f, "label": LABELS[f], "value": round(row[i], 2), "impact": round(contrib[i], 4)}
            for i, f in enumerate(FEATURES)
        ]
        items.sort(key=lambda d: abs(d["impact"]), reverse=True)
        return RiskResult(p, tier_for(p), items, contrib[-1])

    def importance(self) -> list[dict]:
        gains = self.ensemble.gain
        total = sum(gains) or 1.0
        out = [{"feature": f, "label": LABELS[f], "share": round(g / total, 4)}
               for f, g in zip(FEATURES, gains)]
        return sorted(out, key=lambda d: d["share"], reverse=True)


def features_from(metrics: dict, signals: dict, prior_violations: int, established: int,
                  year: int = 2026) -> dict[str, float]:
    return {
        "students_per_faculty": metrics.get("students_per_faculty", 20.0),
        "land_acres": metrics.get("land_acres", 5.0),
        "builtup_sqm_per_student": metrics.get("builtup_sqm_per_student", 8.0),
        "labs_per_100": metrics.get("labs_per_100", 2.5),
        "deficit_pct": metrics.get("deficit_pct", 0.0),
        "phd_pct": metrics.get("phd_pct", 20.0),
        "photo_flags": float(signals.get("photo_flags", 0)),
        "faculty_collisions": float(signals.get("faculty_collisions", 0)),
        "geo_mismatch_km": float(signals.get("geo_max_km", 0.0)),
        "prior_violations": float(prior_violations),
        "years_operating": float(max(1, year - established)),
    }


_model: RiskModel | None = None


def model() -> RiskModel:
    global _model
    if _model is None:
        _model = RiskModel.load()
    return _model


def logistic(x: float) -> float:
    return 1 / (1 + math.exp(-x))
