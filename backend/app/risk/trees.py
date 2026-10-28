"""Inference for an exported LightGBM model in plain Python.

LightGBM's native library needs OpenMP, which serverless runtimes don't
ship. Prediction is just a walk down each tree, and exact per-feature
explanations are TreeSHAP (Lundberg et al., 2018, Algorithm 2), so both run
here from `booster.dump_model()` with no native code. `tests/test_trees.py`
checks both against LightGBM itself.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class _Node:
    feature: int = -1          # -1 marks a leaf
    threshold: float = 0.0
    default_left: bool = True
    left: "_Node | None" = None
    right: "_Node | None" = None
    value: float = 0.0         # leaf value
    cover: float = 0.0         # training rows reaching this node


def _build(d: dict) -> _Node:
    if "leaf_value" in d:
        return _Node(value=float(d["leaf_value"]), cover=float(d.get("leaf_count", 0)))
    if d.get("decision_type", "<=") != "<=":
        raise ValueError(f"unsupported split {d['decision_type']}")
    return _Node(feature=int(d["split_feature"]), threshold=float(d["threshold"]),
                 default_left=bool(d.get("default_left", True)),
                 left=_build(d["left_child"]), right=_build(d["right_child"]),
                 cover=float(d.get("internal_count", 0)))


def _goes_left(n: _Node, x: list[float]) -> bool:
    v = x[n.feature]
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return n.default_left
    return v <= n.threshold


def _expected(n: _Node) -> float:
    if n.feature < 0:
        return n.value
    return (n.left.cover * _expected(n.left) + n.right.cover * _expected(n.right)) / n.cover


# --- TreeSHAP path bookkeeping ------------------------------------------------------

@dataclass
class _P:
    d: int       # feature index (-1 for the root placeholder)
    z: float     # fraction of zero (cold) paths
    o: float     # fraction of one (hot) paths
    w: float     # permutation weight


def _extend(m: list[_P], pz: float, po: float, pi: int) -> list[_P]:
    m = [_P(e.d, e.z, e.o, e.w) for e in m]
    l = len(m)
    m.append(_P(pi, pz, po, 1.0 if l == 0 else 0.0))
    for i in range(l - 1, -1, -1):
        m[i + 1].w += po * m[i].w * (i + 1) / (l + 1)
        m[i].w = pz * m[i].w * (l - i) / (l + 1)
    return m


def _unwind(m: list[_P], i: int) -> list[_P]:
    m = [_P(e.d, e.z, e.o, e.w) for e in m]
    l = len(m) - 1
    n = m[l].w
    for j in range(l - 1, -1, -1):
        if m[i].o != 0:
            t = m[j].w
            m[j].w = n * (l + 1) / ((j + 1) * m[i].o)
            n = t - m[j].w * m[i].z * (l - j) / (l + 1)
        else:
            m[j].w = m[j].w * (l + 1) / (m[i].z * (l - j))
    for j in range(i, l):
        m[j].d, m[j].z, m[j].o = m[j + 1].d, m[j + 1].z, m[j + 1].o
    return m[:l]


def _shap(n: _Node, x: list[float], phi: list[float], m: list[_P], pz: float, po: float, pi: int) -> None:
    m = _extend(m, pz, po, pi)
    if n.feature < 0:
        for i in range(1, len(m)):
            w = sum(e.w for e in _unwind(m, i))
            phi[m[i].d] += w * (m[i].o - m[i].z) * n.value
        return
    hot, cold = (n.left, n.right) if _goes_left(n, x) else (n.right, n.left)
    iz = io = 1.0
    k = next((k for k in range(1, len(m)) if m[k].d == n.feature), None)
    if k is not None:
        iz, io = m[k].z, m[k].o
        m = _unwind(m, k)
    _shap(hot, x, phi, m, iz * hot.cover / n.cover, io, n.feature)
    _shap(cold, x, phi, m, iz * cold.cover / n.cover, 0.0, n.feature)


class TreeEnsemble:
    def __init__(self, dump: dict):
        self.n_features = int(dump["max_feature_idx"]) + 1
        self.trees = [_build(t["tree_structure"]) for t in dump["tree_info"]]
        self.gain = [0.0] * self.n_features
        for t in dump["tree_info"]:
            self._add_gain(t["tree_structure"])

    def _add_gain(self, d: dict) -> None:
        if "leaf_value" in d:
            return
        self.gain[int(d["split_feature"])] += float(d.get("split_gain", 0.0))
        self._add_gain(d["left_child"])
        self._add_gain(d["right_child"])

    def raw(self, x: list[float]) -> float:
        total = 0.0
        for n in self.trees:
            while n.feature >= 0:
                n = n.left if _goes_left(n, x) else n.right
            total += n.value
        return total

    def probability(self, x: list[float]) -> float:
        return 1.0 / (1.0 + math.exp(-self.raw(x)))

    def contributions(self, x: list[float]) -> list[float]:
        """Per-feature SHAP values in log-odds, then the expected value last (LightGBM's layout)."""
        phi = [0.0] * (self.n_features + 1)
        for t in self.trees:
            _shap(t, x, phi, [], 1.0, 1.0, -1)
            phi[-1] += _expected(t)
        return phi
