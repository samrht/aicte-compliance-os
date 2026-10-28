"""Compliance-failure risk scorer.

A LightGBM classifier trained on synthetic past institutions (real AICTE
outcome data is not public). Monotone constraints keep the model honest:
more students per faculty can never lower risk, more land can never raise
it. Per-case explanations are exact TreeSHAP values from `pred_contrib`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
from sklearn.metrics import roc_auc_score

from app import config

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


class RiskModel:
    def __init__(self, booster: lgb.Booster, auc: float | None = None):
        self.booster = booster
        self.auc = auc

    @classmethod
    def train(cls, seed: int = 7) -> "RiskModel":
        X, y = synthetic_history(seed=seed)
        split = int(len(y) * 0.8)
        params = dict(objective="binary", learning_rate=0.05, num_leaves=15,
                      min_data_in_leaf=25, monotone_constraints=MONOTONE,
                      feature_fraction=0.9, verbose=-1, seed=seed)
        train = lgb.Dataset(X[:split], y[:split], feature_name=FEATURES)
        booster = lgb.train(params, train, num_boost_round=250)
        auc = float(roc_auc_score(y[split:], booster.predict(X[split:])))
        return cls(booster, auc)

    @classmethod
    def load_or_train(cls) -> "RiskModel":
        path = config.MODEL_PATH
        if path.exists():
            booster = lgb.Booster(model_file=str(path))
            auc = None
            meta = path.with_suffix(".auc")
            if meta.exists():
                auc = float(meta.read_text())
            return cls(booster, auc)
        model = cls.train()
        config.ensure_dirs()
        model.booster.save_model(str(path))
        path.with_suffix(".auc").write_text(f"{model.auc:.4f}")
        return model

    def score(self, features: dict[str, float]) -> RiskResult:
        row = np.array([[float(features.get(f, 0.0)) for f in FEATURES]])
        p = float(self.booster.predict(row)[0])
        contrib = self.booster.predict(row, pred_contrib=True)[0]
        items = [
            {"feature": f, "label": LABELS[f], "value": round(float(row[0, i]), 2),
             "impact": round(float(contrib[i]), 4)}
            for i, f in enumerate(FEATURES)
        ]
        items.sort(key=lambda d: abs(d["impact"]), reverse=True)
        return RiskResult(p, tier_for(p), items, float(contrib[-1]))

    def importance(self) -> list[dict]:
        gains = self.booster.feature_importance(importance_type="gain")
        total = float(gains.sum()) or 1.0
        out = [{"feature": f, "label": LABELS[f], "share": round(float(g) / total, 4)}
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
        _model = RiskModel.load_or_train()
    return _model


def logistic(x: float) -> float:
    return 1 / (1 + math.exp(-x))
