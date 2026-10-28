"""The pure-Python scorer must agree with LightGBM on predictions and SHAP values."""
import numpy as np
import pytest

lgb = pytest.importorskip("lightgbm")

from app.risk import FEATURES, MONOTONE, synthetic_history  # noqa: E402
from app.risk.trees import TreeEnsemble  # noqa: E402


@pytest.fixture(scope="module")
def pair():
    X, y = synthetic_history(n=1500, seed=3)
    params = dict(objective="binary", learning_rate=0.08, num_leaves=15, min_data_in_leaf=20,
                  monotone_constraints=MONOTONE, verbose=-1, seed=3)
    booster = lgb.train(params, lgb.Dataset(X, y, feature_name=FEATURES), num_boost_round=60)
    return booster, TreeEnsemble(booster.dump_model()), X


def test_predictions_match(pair):
    booster, ours, X = pair
    rows = X[:200]
    ref = booster.predict(rows)
    got = np.array([ours.probability(list(r)) for r in rows])
    assert np.allclose(got, ref, atol=1e-9)


def test_shap_matches_pred_contrib(pair):
    booster, ours, X = pair
    rows = X[:60]
    ref = booster.predict(rows, pred_contrib=True)
    got = np.array([ours.contributions(list(r)) for r in rows])
    assert np.allclose(got, ref, atol=1e-6)
    # SHAP values plus the expected value add up to the raw score.
    assert np.allclose(got.sum(axis=1), booster.predict(rows, raw_score=True), atol=1e-6)
