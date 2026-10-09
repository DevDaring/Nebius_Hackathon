"""Evaluation integrity: nested outer-fold boundary, person grouping, membership manifest.

* No outer-test person may enter ANY training dependency of its fold (population priors behind
  the hybrid's training rows, residual models, conformal, classifiers, calibrators, baselines).
* The production model (``artifacts/manifest.json``) never saw the demo-persona source people.
* Inner folds and bootstrap CIs group repeat recordings by person.
* Stage-1 cache keys change when the code/data fingerprint changes.
"""

from __future__ import annotations

import copy
import hashlib
import json
import pickle

import numpy as np
import pandas as pd
import pytest
from conftest import HAS_PROCESSED

from nemotwins.config import MODELS_DIR
from nemotwins.eval import experiments as E
from nemotwins.eval import metrics as MT
from nemotwins.eval import stage1 as S
from nemotwins.twin import hybrid as HY

MANIFEST = MODELS_DIR / "manifest.json"
needs_data = pytest.mark.skipif(not HAS_PROCESSED, reason="processed data not built")


@pytest.fixture(scope="module")
def manifest() -> dict:
    assert MANIFEST.exists(), "artifacts/manifest.json missing: run python -m nemotwins.eval.experiments"
    return json.loads(MANIFEST.read_text())


@pytest.fixture(scope="module")
def cov_folds() -> tuple[pd.DataFrame, dict[str, int]]:
    _, cov = S.load()
    return cov, S.assign_folds(cov)


# ----------------------------------------------------------------------------- manifest audit
def test_manifest_has_no_leakage(manifest: dict) -> None:
    checks = E.assert_no_leakage(manifest)
    scopes = manifest["membership"]["outer_folds"]
    assert set(scopes) == {"cgmacros", "shanghai"}
    for rec in scopes.values():
        assert set(rec) == {str(f) for f in range(S.N_FOLDS)}
        for fr in rec.values():
            deps = fr["training_dependencies"]
            # every learned component is covered by the audit
            for k in ("train_replay_priors", "hybrid_training_rows", "hybrid.residual_models", "hybrid.conformal",
                      "hybrid.iso_high", "outer_test_replay_priors"):
                assert k in deps, k
    assert len(checks) > 100
    assert manifest["leakage_audit"]["passed"] is True


def test_leak_is_detected(manifest: dict) -> None:
    bad = copy.deepcopy(manifest)
    fr = bad["membership"]["outer_folds"]["cgmacros"]["0"]
    fr["training_dependencies"]["train_replay_priors"].append(fr["test_people"][0])
    with pytest.raises(AssertionError, match="LEAK"):
        E.assert_no_leakage(bad)
    bad = copy.deepcopy(manifest)
    bad["membership"]["production"]["training_dependencies"]["hybrid.residual_models"].append(S.PERSONA_PIDS[0])
    with pytest.raises(AssertionError, match="LEAK production"):
        E.assert_no_leakage(bad)


def test_production_model_excludes_personas(manifest: dict) -> None:
    held = set(S.PERSONA_PIDS)
    assert held == {"cgm005", "cgm038", "cgm046"}
    assert set(manifest["hybrid_trained_on"]["excluded_people"]) == held
    assert not held & set(manifest["prior_cgmacros_trained_on"]["people"])
    for people in manifest["membership"]["production"]["training_dependencies"].values():
        assert not held & set(people)
    with open(MODELS_DIR / "hybrid_cgmacros.pkl", "rb") as f:
        bundle: HY.HybridBundle = pickle.load(f)
    assert bundle.membership, "production hybrid carries no membership record"
    for k, v in bundle.membership.items():
        if k == "inner_folds":
            for inner in v:
                assert not held & set(inner["trained_on"]) and not held & set(inner["predicted"])
        elif v is not None:
            assert not held & set(v), k


def test_manifest_matches_artifacts_and_data(manifest: dict) -> None:
    for name, h in manifest["artifacts"].items():
        assert hashlib.sha256((MODELS_DIR / name).read_bytes()).hexdigest() == h, f"{name} changed since manifest"
    if HAS_PROCESSED:
        assert S.data_hash()[0] == manifest["data_hash"]
    assert manifest["config"]["fold_unit"] == "person"
    assert manifest["config"]["hybrid"]["inner_fold_unit"] == "person"


# ----------------------------------------------------------------------------- nested tags
@needs_data
def test_nested_prior_membership(cov_folds: tuple[pd.DataFrame, dict[str, int]]) -> None:
    cov, folds = cov_folds
    fold_people = {f: set(cov.loc[cov.pid.map(folds) == f, "person"]) for f in range(S.N_FOLDS)}
    for name in ("ladder_2", "sh_in_2"):
        cfg = S.config_by_name(name)
        for pid in cov.loc[cov.dataset == cfg.dataset, "pid"]:
            g = folds[pid]
            tags = S.replay_tags(cfg, pid, folds)
            assert tags[0] == S.test_tag(g)
            test_people = set(S.prior_people(cfg, S.test_tag(g), cov, folds))
            assert not test_people & fold_people[g]
            for f in range(S.N_FOLDS):
                if f == g:
                    with pytest.raises(ValueError):
                        S.train_tag(g, f)
                    continue
                tag = S.train_tag(g, f)
                assert tag in tags
                people = set(S.prior_people(cfg, tag, cov, folds))
                assert not people & (fold_people[f] | fold_people[g]), (name, pid, f)
                assert people  # never an empty prior
            if cfg.production and pid not in S.PERSONA_PIDS:
                people = set(S.prior_people(cfg, S.prod_tag(g), cov, folds))
                assert not people & set(S.PERSONA_PIDS) and not people & fold_people[g]
            if pid in S.PERSONA_PIDS:
                assert S.prod_tag(g) not in tags


@needs_data
def test_folds_group_repeat_recordings(cov_folds: tuple[pd.DataFrame, dict[str, int]]) -> None:
    cov, folds = cov_folds
    per_person = cov.assign(fold=cov.pid.map(folds)).groupby("person").fold.nunique()
    assert (per_person == 1).all()
    assert (cov.groupby("person").pid.size() > 1).any(), "expected repeat recordings (ShanghaiT2DM)"


# ----------------------------------------------------------------------------- person grouping
def _frame_with_repeats(n_people: int = 12, recs: int = 3) -> pd.DataFrame:
    rows = []
    for p in range(n_people):
        for r in range(recs):
            for k in range(5):
                rows.append({"person": f"p{p}", "pid": f"p{p}-r{r}", "k": k})
    return pd.DataFrame(rows)


def test_inner_folds_group_by_person() -> None:
    o = _frame_with_repeats()
    inner = HY.inner_fold_of(o, 3, seed=4)
    by_person = pd.Series(inner).groupby(o.person.to_numpy()).nunique()
    assert (by_person == 1).all()
    assert len(set(inner)) == 3
    # deterministic
    assert np.array_equal(inner, HY.inner_fold_of(o, 3, seed=4))


def test_bootstrap_resamples_people() -> None:
    o = _frame_with_repeats(8, 3)
    sizes: list[int] = []

    def fn(d: pd.DataFrame) -> float:
        # every person drawn brings all 15 of its rows (3 recordings x 5 windows)
        counts = d.groupby("person").size()
        sizes.extend(counts.tolist())
        return float(len(d))

    MT.bootstrap_by_person(o, fn, n_boot=50, seed=1)
    assert sizes and all(s % 15 == 0 for s in sizes)


def test_wilson_and_reliability_bins() -> None:
    lo, hi = MT.wilson_ci(6, 10)
    assert 0.29 < lo < 0.32 and 0.82 < hi < 0.85
    rng = np.random.default_rng(0)
    p = rng.uniform(0, 1, 2000)
    y = (rng.uniform(0, 1, 2000) < p).astype(float)
    bins, ece = MT.reliability(y, p, groups=np.repeat(np.arange(20), 100))
    assert ece < 0.05
    for b in bins:
        assert b["pred_lo"] <= b["mean_pred"] <= b["pred_hi"]
        assert b["ci_lo"] <= b["observed"] <= b["ci_hi"]
        assert b["n"] > 0 and b["n_people"] > 0


# ----------------------------------------------------------------------------- cache versioning
def test_cache_key_tracks_fingerprint(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = S.Config("ladder_2", "cgmacros", "cv", {"ladder": "2"})
    monkeypatch.setattr(S, "fingerprint", lambda: "a" * 16)
    k1 = cfg.key()
    monkeypatch.setattr(S, "fingerprint", lambda: "b" * 16)
    assert cfg.key() != k1 and cfg.key().startswith("ladder_2-")


def test_calibration_curve_report_has_counts() -> None:
    from nemotwins.config import REPORTS_DIR

    cc = json.loads((REPORTS_DIR / "calibration_curve.json").read_text())["levels"]
    for lvl in ("full", "4", "2", "1", "0"):
        for b in cc[lvl]["high"]:
            for k in ("pred_lo", "pred_hi", "mean_pred", "observed", "n", "ci_lo", "ci_hi"):
                assert k in b, (lvl, k)
