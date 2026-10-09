"""Stage 2: hybrid layer + every experiment report (spec section 5.3).

Writes ``reports/*.json`` (read by the Trust panel and the README tables),
``reports/figures/*.png``, the production model ``artifacts/hybrid_cgmacros.pkl`` and the
audit manifest ``artifacts/manifest.json``. Run after ``nemotwins.eval.stage1``:

    python -m nemotwins.eval.experiments            # everything
    python -m nemotwins.eval.experiments --check    # verify manifest vs artifacts + no leakage

Nested outer-fold protocol. For outer fold ``f`` every learned dependency of the hybrid
excludes fold ``f``: its training rows are stage-1 replays of patients ``p`` (fold ``g != f``)
whose population prior was fitted on people outside ``{f, g}`` (stage-1 tag ``x<fg>``); the
residual models, conformal quantiles, stacked classifiers, isotonic calibrators, abstain
statistics (inner folds grouped by person), the sparse LightGBM baseline and the time-of-day
curve are fitted on those rows only. Outer-test patients are replayed with a prior fitted on
people outside fold ``f`` (tag ``x<f>``). Every component's training membership is recorded in
the manifest and asserted disjoint from the fold's test people.
"""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from nemotwins.config import MODELS_DIR, REPORTS_DIR
from nemotwins.eval import metrics as MT
from nemotwins.eval import stage1 as S
from nemotwins.twin import hybrid as HY
from nemotwins.twin import prior as P
from nemotwins.twin.runner import HORIZONS, LADDER_LEVELS

LADDER_CFGS = [f"ladder_{lvl}" for lvl in LADDER_LEVELS]
CG_CFGS = LADDER_CFGS + ["calib_1", "calib_3", "calib_5", "calib_7", "nbp_random", "nbp_twin"]
SH_IN = ["sh_in_2", "sh_in_cbg"]
TRANSFER_CFGS = ["sh_from_cg_2", "sh_from_cg_cbg", "cg_from_sh_2"]
LADDER_LABEL = {"full": "Full CGM", "4": "4 pricks/day", "2": "2 pricks/day", "1": "1 prick/day", "0": "No glucose data"}
XH = S.XH
VALIDATED_HORIZON_MIN = max(HORIZONS)
MANIFEST = MODELS_DIR / "manifest.json"
OLD_HEADLINE = REPORTS_DIR / "archive" / "pre_nested_protocol" / "headline.json"
N_BOOT = 500

Frame = tuple[pd.DataFrame, np.ndarray, np.ndarray]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean(x: Any) -> Any:
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, list | tuple | set):
        return [_clean(v) for v in (sorted(x) if isinstance(x, set) else x)]
    if isinstance(x, np.ndarray):
        return _clean(x.tolist())
    if isinstance(x, np.generic):
        x = x.item()
    if isinstance(x, float) and not np.isfinite(x):
        return None
    return x


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    tmp.write_text(text)
    os.replace(tmp, path)


def atomic_pickle(obj: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    with open(tmp, "wb") as fh:
        pickle.dump(obj, fh)
    os.replace(tmp, path)


def write_report(name: str, payload: dict) -> None:
    payload = {"generated_at": _now(), "generated_by": "nemotwins.eval.experiments", **payload}
    atomic_write_text(REPORTS_DIR / f"{name}.json", json.dumps(_clean(payload), indent=1, ensure_ascii=False))
    print(f"  wrote reports/{name}.json", flush=True)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ----------------------------------------------------------------------------- collect
@dataclass
class Data:
    """Stage-1 replays as (origins, pmax, pmin) frames, plus reconstruction frames."""

    ts: pd.DataFrame
    cov: pd.DataFrame
    folds: dict[str, int]
    person: dict[str, str]
    test: dict[str, Frame]  # config -> outer-test (or transfer) replays, one per patient
    recon: dict[str, pd.DataFrame]  # config -> reconstruction of the test replays
    test_prior_people: dict[str, dict[str, list[str]]]  # config -> pid -> prior membership
    runs: dict[str, dict[str, dict[str, S.Stage1Run]]]  # nested/production replays: config -> tag -> pid

    def train_frame(self, cfgs: Iterable[str], outer_fold: int) -> tuple[Frame, set[str]]:
        """Training rows of the outer-fold hybrid (nested tags) and the union of their priors' people."""
        parts, prior_people = [], set()
        for c in cfgs:
            for tag, runs in self.runs[c].items():
                for pid, r in runs.items():
                    g = self.folds[pid]
                    if g == outer_fold or tag != S.train_tag(g, outer_fold):
                        continue
                    parts.append(_run_frame(r, c, self.person))
                    prior_people |= set(r.meta["prior_people"])
        return _cat(parts), prior_people

    def prod_frame(self, cfgs: Iterable[str]) -> tuple[Frame, set[str]]:
        parts, prior_people = [], set()
        for c in cfgs:
            for tag, runs in self.runs[c].items():
                for pid, r in runs.items():
                    if tag == S.prod_tag(self.folds[pid]):
                        parts.append(_run_frame(r, c, self.person))
                        prior_people |= set(r.meta["prior_people"])
        return _cat(parts), prior_people


def _run_frame(r: S.Stage1Run, name: str, person: dict[str, str]) -> Frame | None:
    res = r.result
    if len(res.origins) == 0:
        return None
    o = res.origins.copy()
    o["cfg"] = name
    o["person"] = o["pid"].map(person)
    return o, res.pmax, res.pmin


def _cat(parts: Iterable[Frame | None]) -> Frame:
    ps = [p for p in parts if p is not None]
    return (pd.concat([p[0] for p in ps], ignore_index=True), np.concatenate([p[1] for p in ps]),
            np.concatenate([p[2] for p in ps]))


def _subset(fr: Frame, mask: np.ndarray) -> Frame:
    o, x, n = fr
    return o[mask].reset_index(drop=True), x[mask], n[mask]


def load_data(test_cfgs: Iterable[str] = (*CG_CFGS, *SH_IN, *TRANSFER_CFGS),
              nested_cfgs: Iterable[str] = (*LADDER_CFGS, *SH_IN)) -> Data:
    ts, cov = S.load()
    folds = S.assign_folds(cov)
    person = S.person_of(cov)
    test: dict[str, Frame] = {}
    recon: dict[str, pd.DataFrame] = {}
    tpp: dict[str, dict[str, list[str]]] = {}
    for name in test_cfgs:
        runs = S.load_test_runs(S.config_by_name(name))
        if not runs:
            raise SystemExit(f"no stage-1 results for {name}; run python -m nemotwins.eval.stage1 first")
        test[name] = _cat(_run_frame(r, name, person) for _, r in sorted(runs.items()))
        rcs = []
        for pid, r in sorted(runs.items()):
            rc = r.result.recon.copy()
            rc["pid"], rc["person"], rc["cfg"] = pid, person[pid], name
            rcs.append(rc)
        recon[name] = pd.concat(rcs, ignore_index=True)
        tpp[name] = {pid: list(r.meta["prior_people"]) for pid, r in runs.items()}
    nested: dict[str, dict[str, dict[str, S.Stage1Run]]] = {}
    for name in nested_cfgs:
        cfg = S.config_by_name(name)
        test_tags = {S.test_tag(f) for f in range(S.N_FOLDS)}
        nested[name] = {t: rs for t, rs in S.load_runs(cfg).items() if t not in test_tags}
        for rs in nested[name].values():
            for r in rs.values():  # training rows never need the per-step reconstruction
                r.result.recon = r.result.recon.iloc[:0]
    return Data(ts, cov, folds, person, test, recon, tpp, nested)


# ----------------------------------------------------------------------------- metrics
def counts(o: pd.DataFrame) -> dict[str, int]:
    return {"n_people": int(o["person"].nunique()) if "person" in o else int(o.pid.nunique()),
            "n_recordings": int(o.pid.nunique()), "n_forecast_windows": int(len(o))}


def summarise(o: pd.DataFrame, pred_prefix: str = "pred_", with_bands: bool = True,
              p_high: str = "p_high", p_low: str = "p_low", boot: bool = False) -> dict:
    c = counts(o)
    out: dict[str, Any] = {"n_patients": c["n_people"], **c, "n_forecasts": c["n_forecast_windows"]}
    out["rmse"] = {str(h): MT.rmse(o[f"true_{h}"].to_numpy(), o[f"{pred_prefix}{h}"].to_numpy()) for h in HORIZONS}
    out["mard_60"] = MT.mard(o["true_60"].to_numpy(), o[f"{pred_prefix}60"].to_numpy())
    if with_bands and "lo_60" in o:
        out["coverage90"], out["width90"] = {}, {}
        for h in HORIZONS:
            cv, w = MT.coverage(o[f"true_{h}"].to_numpy(), o[f"lo_{h}"].to_numpy(), o[f"hi_{h}"].to_numpy())
            out["coverage90"][str(h)], out["width90"][str(h)] = cv, w
    if p_high in o:
        yh, yl = o["ev_high"].to_numpy(float), o["ev_low"].to_numpy(float)
        out["auroc_high"] = MT.auroc(yh, o[p_high].to_numpy())
        out["auprc_high"] = MT.auprc(yh, o[p_high].to_numpy())
        out["brier_high"] = MT.brier(yh, o[p_high].to_numpy())
        out["ece_high"] = MT.reliability(yh, o[p_high].to_numpy())[1]
        out["prevalence_high"] = float(np.nanmean(yh))
        if p_low in o:
            out["auroc_low"] = MT.auroc(yl, o[p_low].to_numpy())
            out["auprc_low"] = MT.auprc(yl, o[p_low].to_numpy())
            out["ece_low"] = MT.reliability(yl, o[p_low].to_numpy())[1]
            out["prevalence_low"] = float(np.nanmean(yl))
    if "abstain" in o:
        out["abstain_rate"] = float(o["abstain"].mean())
    if boot:
        col = f"{pred_prefix}60"
        out["rmse60_ci"] = MT.bootstrap_by_person(
            o, lambda d: MT.rmse(d["true_60"].to_numpy(), d[col].to_numpy()), n_boot=N_BOOT)
        if p_high in o:
            out["auroc_high_ci"] = MT.bootstrap_by_person(
                o, lambda d: MT.auroc(d["ev_high"].to_numpy(float), d[p_high].to_numpy()), n_boot=N_BOOT)
        if with_bands and "lo_60" in o:
            out["coverage90_60_ci"] = MT.bootstrap_by_person(
                o, lambda d: MT.coverage(d["true_60"].to_numpy(), d["lo_60"].to_numpy(), d["hi_60"].to_numpy())[0],
                n_boot=N_BOOT)
    return out


def recon_summary(rc: pd.DataFrame) -> dict:
    m = rc[rc.phase == "maint"]
    y, p = m["true"].to_numpy(), m["mu"].to_numpy()
    cv, width = MT.coverage(y, m["q05"].to_numpy(), m["q95"].to_numpy())
    return {"rmse": MT.rmse(y, p), "mard": MT.mard(y, p), "particle_band_coverage90": cv,
            "particle_band_width90": width, "clarke": MT.clarke_summary(y, p)}


def exploratory_columns(a: pd.DataFrame) -> pd.DataFrame:
    """180/240-min forecasts exactly as the app extends them: the 120-min learned residual is held
    and the particle band is widened by the 120-min conformal/particle ratio."""
    if f"xmed_{XH[0]}" not in a:
        return a
    a = a.copy()
    ratio = np.maximum(1.0, ((a[f"hi_{VALIDATED_HORIZON_MIN}"] - a[f"lo_{VALIDATED_HORIZON_MIN}"]) / 2).to_numpy()
                       / np.maximum(((a[f"q95_{VALIDATED_HORIZON_MIN}"] - a[f"q05_{VALIDATED_HORIZON_MIN}"]) / 2)
                                    .to_numpy(), 1.0))
    res = a[f"res_{VALIDATED_HORIZON_MIN}"].to_numpy()
    for h in XH:
        med = a[f"xmed_{h}"].to_numpy()
        pred = med + res
        a[f"pred_{h}"] = pred
        a[f"med_{h}"] = med
        a[f"lo_{h}"] = np.clip(pred - (med - a[f"xq05_{h}"].to_numpy()) * ratio, 30, 500)
        a[f"hi_{h}"] = np.clip(pred + (a[f"xq95_{h}"].to_numpy() - med) * ratio, 30, 500)
    return a


def _rmse_at(h: int, pfx: str = "pred_") -> Callable[[pd.DataFrame], float]:
    def fn(d: pd.DataFrame) -> float:
        return MT.rmse(d[f"true_{h}"].to_numpy(), d[f"{pfx}{h}"].to_numpy())
    return fn


def exploratory_summary(a: pd.DataFrame) -> dict:
    a = exploratory_columns(a)
    out: dict[str, Any] = {
        "status": "exploratory",
        "validated_horizon_min": VALIDATED_HORIZON_MIN,
        "note": ("Beyond 120 min the learned residual and the conformal band are NOT trained or calibrated: the "
                 "120-min residual is held and the particle band is widened by the 120-min conformal ratio, exactly "
                 "as the app draws its 4-hour curve. Later meals are unknown to the forecast. Exploratory only."),
        "horizons": {}}
    for h in XH:
        if f"pred_{h}" not in a:
            continue
        y = a[f"true_{h}"].to_numpy()
        cv, w = MT.coverage(y, a[f"lo_{h}"].to_numpy(), a[f"hi_{h}"].to_numpy())
        ok = np.isfinite(y)
        out["horizons"][str(h)] = {
            "rmse": MT.rmse(y, a[f"pred_{h}"].to_numpy()), "rmse_mechanistic_only": MT.rmse(y, a[f"med_{h}"].to_numpy()),
            "coverage90": cv, "width90": w, "n_forecast_windows": int(ok.sum()),
            "n_people": int(a.loc[ok, "person"].nunique()),
            "rmse_ci": MT.bootstrap_by_person(a, _rmse_at(h), n_boot=N_BOOT),
            "status": "exploratory"}
    return out


# ----------------------------------------------------------------------------- baselines
SPARSE_FEATS = ["hs_cap", "last_or_mean", "hour_sin", "hour_cos", "carbs_now", "carbs_2h", "carbs_4h",
                "mets_1h", "ladder_num", "calib_mean", "calib_sd", "age", "bmi", "hba1c"]
BASELINE_METHODS = {"persistence": "persist_", "population_time_of_day": "popavg_", "personal_average": "pmean_",
                    "lightgbm_sparse_only": "sparse_", "mechanistic_only": "med_"}


def _sparse_x(o: pd.DataFrame) -> np.ndarray:
    o = o.copy()
    o["last_or_mean"] = o["last_obs"].where(np.isfinite(o["last_obs"]), o["calib_mean"])
    return o[SPARSE_FEATS].to_numpy(float)


def fit_sparse_baseline(o: pd.DataFrame) -> dict:
    x = _sparse_x(o)
    out: dict[Any, Any] = {}
    for h in HORIZONS:
        y = o[f"true_{h}"].to_numpy(float)
        m = np.isfinite(y)
        out[h] = lgb.LGBMRegressor(random_state=0, **HY.LGB_PARAMS).fit(x[m], y[m])
    y = o["ev_high"].to_numpy(float)
    m = np.isfinite(y)
    out["clf_high"] = lgb.LGBMClassifier(random_state=0, **HY.LGB_PARAMS).fit(x[m], y[m].astype(int))
    return out


def time_of_day_curve(ts: pd.DataFrame) -> np.ndarray:
    t = pd.to_datetime(ts["t"])
    b = (t.dt.hour * 2 + t.dt.minute // 30).to_numpy()
    s = pd.Series(ts["cgm"].to_numpy(float)).groupby(b).mean()
    return s.reindex(range(48)).interpolate().to_numpy()


def add_baselines(a: pd.DataFrame, sparse: dict, tod: np.ndarray) -> pd.DataFrame:
    x = _sparse_x(a)
    for h in HORIZONS:
        a[f"persist_{h}"] = a["last_obs"].where(np.isfinite(a["last_obs"]), a["calib_mean"])
        hh = (a["hour"] + h / 60.0) % 24
        a[f"popavg_{h}"] = tod[(hh * 2).astype(int) % 48]
        a[f"pmean_{h}"] = a["calib_mean"]
        a[f"sparse_{h}"] = sparse[h].predict(x)
    a["sparse_p_high"] = sparse["clf_high"].predict_proba(x)[:, 1]
    return a


# ----------------------------------------------------------------------------- outer folds
@dataclass
class FoldModels:
    fold: int
    bundle: HY.HybridBundle
    sparse: dict | None
    tod: np.ndarray | None
    membership: dict[str, Any]


def _fold_cache_dir(scope: str) -> Path:
    h = hashlib.sha256()
    h.update(S.fingerprint().encode())
    for f in (Path(HY.__file__), Path(__file__)):
        h.update(f.read_bytes())
    return S.CACHE / f"outer_hybrid_{scope}-{h.hexdigest()[:10]}"


class _FoldUnpickler(pickle.Unpickler):
    """Resolve ``FoldModels`` to this module even when the cache was written by ``python -m``
    (pickle then records ``__main__``) and is read from another entry point."""

    def find_class(self, module: str, name: str):  # type: ignore[no-untyped-def]
        if name == "FoldModels" and module in {"__main__", "__mp_main__"}:
            return FoldModels
        return super().find_class(module, name)


def fit_outer_fold(d: Data, f: int, scope: str = "cgmacros") -> FoldModels:
    """Hybrid (+ baselines for CGMacros) for outer fold ``f`` on nested training replays; cached."""
    path = _fold_cache_dir(scope) / f"fold{f}.pkl"
    if path.exists():
        with open(path, "rb") as fh:
            fm: FoldModels = _FoldUnpickler(fh).load()
        return fm
    cfgs = LADDER_CFGS if scope == "cgmacros" else SH_IN
    (tro, trx, trn), train_priors = d.train_frame(cfgs, f)
    bundle = HY.fit_hybrid(tro, trx, trn, seed=f)
    train_people = sorted(set(tro.person))
    train_pids = set(tro.pid)
    sparse = tod = None
    if scope == "cgmacros":
        sparse = fit_sparse_baseline(HY.add_features(tro))
        tod = time_of_day_curve(d.ts[d.ts.pid.isin(train_pids)])
    ds = "cgmacros" if scope == "cgmacros" else "shanghai"
    test_people = sorted({d.person[p] for p in d.cov.loc[d.cov.dataset == ds, "pid"] if d.folds[p] == f})
    deps: dict[str, list[str]] = {"train_replay_priors": sorted(train_priors), "hybrid_training_rows": train_people}
    for k, v in bundle.membership.items():
        if k == "inner_folds":
            for inner in v:
                deps[f"hybrid.inner_fold_{inner['k']}.trained_on"] = inner["trained_on"]
        elif v is not None:
            deps[f"hybrid.{k}"] = v
    if scope == "cgmacros":
        deps["sparse_lightgbm_baseline"] = train_people
        deps["population_time_of_day_curve"] = sorted({d.person[p] for p in train_pids})
    membership = {"test_people": test_people, "training_dependencies": deps,
                  "n_training_people": len(train_people), "n_training_rows": int(len(tro))}
    fm = FoldModels(f, bundle, sparse, tod, membership)
    atomic_pickle(fm, path)
    return fm


def apply_outer(d: Data, cfgs: Iterable[str], scope: str = "cgmacros") -> tuple[dict[str, pd.DataFrame], dict]:
    applied: dict[str, list[pd.DataFrame]] = {c: [] for c in cfgs}
    fold_records: dict[str, Any] = {}
    for f in range(S.N_FOLDS):
        fm = fit_outer_fold(d, f, scope)
        test_priors: set[str] = set()
        for c in applied:
            o, pmx, pmn = d.test[c]
            m = (o.pid.map(d.folds) == f).to_numpy()
            if not m.any():
                continue
            a = fm.bundle.apply(o[m].reset_index(drop=True), pmx[m], pmn[m])
            if fm.sparse is not None and fm.tod is not None:
                a = add_baselines(a, fm.sparse, fm.tod)
            applied[c].append(a)
            for pid in set(o.pid[m]):
                test_priors |= set(d.test_prior_people[c][pid])
        rec = json.loads(json.dumps(fm.membership))
        rec["training_dependencies"]["outer_test_replay_priors"] = sorted(test_priors)
        fold_records[str(f)] = rec
        print(f"  {scope} outer fold {f}: trained on {fm.membership['n_training_people']} people, "
              f"{fm.membership['n_training_rows']} rows", flush=True)
    return {c: pd.concat(v, ignore_index=True) for c, v in applied.items() if v}, fold_records


# ----------------------------------------------------------------------------- leakage audit
def assert_no_leakage(manifest: dict) -> list[str]:
    """Raise AssertionError if any outer-test person (or demo persona, for the production model)
    appears in a training dependency. Returns the list of checks performed."""
    checks = []
    mem = manifest["membership"]
    for scope, rec in mem["outer_folds"].items():
        for f, fr in rec.items():
            test = set(fr["test_people"])
            assert test, f"{scope} fold {f}: empty test set"
            for dep, people in fr["training_dependencies"].items():
                overlap = test & set(people)
                assert not overlap, f"LEAK {scope} fold {f}: {sorted(overlap)} in {dep}"
                checks.append(f"{scope}/fold{f}/{dep}")
    prod = mem["production"]
    held = set(prod["held_out_people"])
    for dep, people in prod["training_dependencies"].items():
        overlap = held & set(people)
        assert not overlap, f"LEAK production: held-out persona sources {sorted(overlap)} in {dep}"
        checks.append(f"production/{dep}")
    for arm, rec in mem.get("transfer", {}).items():
        target = set(rec["test_people"])
        for dep, people in rec["training_dependencies"].items():
            overlap = target & set(people)
            assert not overlap, f"LEAK transfer {arm}: {sorted(overlap)} in {dep}"
            checks.append(f"transfer/{arm}/{dep}")
    return checks


def check_manifest(manifest: dict | None = None) -> dict:
    """Artifact compatibility: manifest hashes vs files on disk, data hash, leakage audit."""
    manifest = manifest or json.loads(MANIFEST.read_text())
    out: dict[str, Any] = {"artifacts": {}}
    for name, h in manifest["artifacts"].items():
        p = MODELS_DIR / name
        out["artifacts"][name] = p.exists() and sha256_file(p) == h
    out["data_hash_matches"] = S.data_hash()[0] == manifest["data_hash"]
    out["code_hash_matches"] = S.code_hash()[0] == manifest["code_hash"]
    out["stage1_code_hash_matches"] = S.stage1_code_hash() == manifest["stage1_code_hash"]
    out["leakage_checks"] = len(assert_no_leakage(manifest))
    out["ok"] = all(out["artifacts"].values()) and out["data_hash_matches"]
    return out


# ----------------------------------------------------------------------------- main
def main() -> None:
    old = json.loads(OLD_HEADLINE.read_text()) if OLD_HEADLINE.exists() else None
    d = load_data()
    print("collected", {k: len(v[0]) for k, v in d.test.items()}, flush=True)
    membership: dict[str, Any] = {"outer_folds": {}, "transfer": {}}

    # ---- in-domain CGMacros hybrid, nested outer person-wise folds
    res, membership["outer_folds"]["cgmacros"] = apply_outer(d, CG_CFGS, "cgmacros")
    for c in res:
        res[c]["group"] = res[c].pid.map(dict(zip(d.cov.pid, d.cov.group, strict=True)))

    # ---- production bundle for the app: CGMacros minus the demo-persona source participants
    (tro, trx, trn), prod_priors = d.prod_frame(LADDER_CFGS)
    prod = HY.fit_hybrid(tro, trx, trn, seed=0)
    held_out = list(S.PERSONA_PIDS)
    assert not set(held_out) & set(tro.person), "persona sources in production training rows"
    prior_people = P.production_people(d.cov, "cgmacros")
    prod_deps = {"train_replay_priors": sorted(prod_priors), "hybrid_training_rows": sorted(set(tro.person)),
                 "production_prior_cgmacros": prior_people}
    for k, v in prod.membership.items():
        if k == "inner_folds":
            for inner in v:
                prod_deps[f"hybrid.inner_fold_{inner['k']}.trained_on"] = inner["trained_on"]
        elif v is not None:
            prod_deps[f"hybrid.{k}"] = v
    membership["production"] = {"held_out_people": held_out, "training_dependencies": prod_deps}
    atomic_pickle(prod, MODELS_DIR / "hybrid_cgmacros.pkl")
    print(f"  production hybrid: {len(set(tro.person))} people (held out {held_out})", flush=True)

    # ---- Exp 1: sensor ladder (headline)
    ladder_rows = []
    for lvl in LADDER_LEVELS:
        a = res[f"ladder_{lvl}"]
        rc = d.recon[f"ladder_{lvl}"]
        row = {"level": lvl, "label": LADDER_LABEL[lvl], **summarise(a, boot=True),
               "mechanistic_only": summarise(a, "med_", with_bands=False, p_high="p_high_raw", p_low="p_low_raw"),
               "reconstruction": recon_summary(rc),
               "t2d_only": summarise(a[a.group == "T2D"]),
               "meal_anchored": summarise(a[a.meal_origin]),
               "abstain_vs_not": {
                   "rmse60_abstained": MT.rmse(a.loc[a.abstain, "true_60"].to_numpy(), a.loc[a.abstain, "pred_60"].to_numpy()),
                   "rmse60_confident": MT.rmse(a.loc[~a.abstain, "true_60"].to_numpy(), a.loc[~a.abstain, "pred_60"].to_numpy()),
               },
               "exploratory_horizons": exploratory_summary(a)}
        yl = a["ev_low"].to_numpy(float)
        row["low_events"] = {"positive_windows": int(np.nansum(yl)), "prevalence": float(np.nanmean(yl)),
                             "patients_with_lows": int(a.loc[a.ev_low == 1, "person"].nunique()),
                             "validated": False,
                             "note": ("Too few low-glucose events in CGMacros (participants are mostly not on "
                                      "glucose-lowering drugs) to train or validate P(<70). Shown in the app "
                                      "with a 'not validated' label.")}
        ladder_rows.append(row)
    a2, a0 = res["ladder_2"], res["ladder_0"]
    write_report("sensor_ladder", {
        "recent_prick_value": recent_prick_value(a2, a0),
        "paired_band_width": paired_band_width(a2, a0),
        "by_hours_since_reading": by_hours_since_reading(a2),
        "by_hours_since_reading_note": (
            "Descriptive only and confounded by clock time: in the 2 pricks/day arm the readings are at 07:00 and "
            "22:00, so 'hours since the last reading' is almost a function of the time of day (and of meals). Use "
            "paired_band_width (same origins, with vs without pricks) for the controlled comparison."),
        "title": "Sensor-ladder ablation (Experiment 1)",
        "dataset": "CGMacros v1.0.0 (PhysioNet), 45 adults (14 T2D, 16 prediabetes, 15 healthy)",
        "protocol": ("Calibrate on the first 5 days of CGM (a 5-day CGM calibration wear), then hide the CGM. The twin "
                     "sees only k simulated finger-pricks per day (fasting 07:00, 11:00, 16:00, post-dinner 22:00; "
                     "glucometer error 5% sd) plus logged meals and activity. Forecasts every 30 min and at every "
                     "meal; scored against the hidden CGM. Nested person-wise 5-fold cross-validation (every learned "
                     "dependency of a fold's model, including the population priors behind its training rows, "
                     "excludes that fold's people); 95% CIs bootstrap over people."),
        "validated_horizon_min": VALIDATED_HORIZON_MIN,
        "levels": ladder_rows,
    })

    # ---- calibration curves (held-out reliability bins with counts + Wilson CIs, read by the backend)
    curves = {}
    for lvl in LADDER_LEVELS:
        a = res[f"ladder_{lvl}"]
        g = a["person"].to_numpy()
        hi_bins, hi_ece = MT.reliability(a["ev_high"].to_numpy(float), a["p_high"].to_numpy(), groups=g)
        lo_bins, lo_ece = MT.reliability(a["ev_low"].to_numpy(float), a["p_low"].to_numpy(), groups=g)
        raw_bins, raw_ece = MT.reliability(a["ev_high"].to_numpy(float), a["p_high_raw"].to_numpy(), groups=g)
        curves[lvl] = {"high": hi_bins, "ece_high": hi_ece, "validated_high": True,
                       "low": lo_bins, "ece_low": lo_ece, "validated_low": False,
                       "high_uncalibrated": raw_bins, "ece_high_uncalibrated": raw_ece,
                       **counts(a)}
    write_report("calibration_curve", {
        "title": "Reliability of P(>180 in 2 h) and P(<70 in 2 h)",
        "protocol": ("Held-out (nested outer-fold) predictions on CGMacros, 10 equal-width probability bins. Per bin: "
                     "edges pred_lo/pred_hi, mean predicted probability, observed frequency, n forecast windows, "
                     "n_people, and a Wilson 95% interval of the observed frequency."),
        "ci_note": ("The Wilson interval treats forecast windows as independent; windows from one person overlap and "
                    "are correlated, so the true uncertainty of each bin is wider than shown. P(<70) is not "
                    "validated (too few low events)."),
        "levels": curves})

    # ---- Exp 2: calibration length
    rows = []
    for dd in (1, 3, 5, 7):
        a = res[f"calib_{dd}"]
        rc = d.recon[f"calib_{dd}"]
        rc = rc[rc.t >= rc.groupby("pid").t.transform("min") + pd.Timedelta(days=7)]
        rows.append({"cgm_days": dd, **summarise(a, boot=True), "reconstruction": recon_summary(rc)})
    write_report("calibration_length", {
        "title": "Calibration-length ablation (Experiment 2)",
        "protocol": ("CGM for the first 1/3/5/7 days, then 2 finger-pricks a day. All variants scored on the same "
                     "window (day 7 onward). CGMacros records span ~10 days, so 3/7/10/14 days from the spec was not "
                     "possible. Test patients use a prior fitted on other folds; the hybrid is the nested outer-fold "
                     "model of the patient's fold."),
        "rows": rows,
    })

    # ---- Exp 3: baselines (+ paired person-level differences at 60 min)
    brows = []
    for lvl in ("full", "2", "0"):
        a = res[f"ladder_{lvl}"]
        brows.append({"level": lvl, "label": LADDER_LABEL[lvl], **counts(a), "methods": {
            "persistence": summarise(a, "persist_", with_bands=False, p_high="__none"),
            "population_time_of_day": summarise(a, "popavg_", with_bands=False, p_high="__none"),
            "personal_average": summarise(a, "pmean_", with_bands=False, p_high="__none"),
            "lightgbm_sparse_only": summarise(a, "sparse_", with_bands=False, p_high="sparse_p_high", p_low="__none"),
            "mechanistic_only": summarise(a, "med_", with_bands=False, p_high="p_high_raw", p_low="p_low_raw"),
            "full_hybrid": summarise(a),
        }, "paired_vs_full_hybrid_60min": paired_baselines(a)})
    write_report("baselines", {
        "title": "Baselines (Experiment 3)", "rows": brows,
        "notes": ("Same forecast origins and people for every method; nested person-wise CV (the sparse LightGBM "
                  "baseline and the population time-of-day curve are fitted on each fold's training people only). "
                  "paired_vs_full_hybrid_60min: RMSE(full_hybrid) - RMSE(baseline) at 60 min on the same windows; "
                  "negative = hybrid better; 95% CI by bootstrap over people.")})

    # ---- Exp 4: next-best-prick value
    write_report("nbp_value", nbp_value(res, d))

    # ---- Exp 5: transfer (+ in-domain Shanghai, nested)
    tr, sh_folds, tr_membership = transfer(d, res)
    membership["outer_folds"]["shanghai"] = sh_folds
    membership["transfer"] = tr_membership
    write_report("transfer", tr)

    # ---- Exp 6: subgroups
    write_report("subgroups", subgroups(res["ladder_2"], d.cov))

    # ---- Exp 8: error grid
    eg = {}
    for lvl in LADDER_LEVELS:
        a = res[f"ladder_{lvl}"]
        eg[lvl] = {"label": LADDER_LABEL[lvl],
                   "virtual_cgm": recon_summary(d.recon[f"ladder_{lvl}"])["clarke"],
                   "forecast_60": MT.clarke_summary(a["true_60"].to_numpy(), a["pred_60"].to_numpy())}
    write_report("error_grid", {"title": "Clarke error grid (Experiment 8)", "levels": eg,
                                "note": "Zones A+B are clinically acceptable. Reference = hidden Dexcom CGM."})

    # ---- manifest (+ leakage assertion) before the summary so the summary can cite it
    manifest = build_manifest(membership, d, len(set(tro.person)))
    checks = assert_no_leakage(manifest)
    manifest["leakage_audit"] = {"passed": True, "n_checks": len(checks), "at": _now()}
    atomic_write_text(MANIFEST, json.dumps(_clean(manifest), indent=1))
    print(f"  wrote artifacts/manifest.json ({len(checks)} leakage checks passed)", flush=True)

    # ---- summary for the trust panel headline
    lad = json.loads((REPORTS_DIR / "sensor_ladder.json").read_text())["levels"]
    write_report("summary", {
        "dataset": "CGMacros v1.0.0", "n_patients_eval": int(res["ladder_2"].person.nunique()),
        **counts(res["ladder_2"]),
        "evaluation_protocol": ("Nested person-wise 5-fold cross-validation: for each outer fold every learned "
                                "dependency (population priors behind the training rows, residual models, conformal "
                                "quantiles, classifiers, isotonic calibrators, baselines) excludes that fold's people; "
                                "membership recorded and asserted in artifacts/manifest.json. 95% CIs bootstrap over "
                                "people. Setting: 5-day CGM calibration wear, then finger-pricks only."),
        "validated_horizon_min": VALIDATED_HORIZON_MIN,
        "ladder": [{"level": r["level"], "label": r["label"], "rmse": r["rmse"], "rmse60_ci": r.get("rmse60_ci"),
                    "auroc_high": r.get("auroc_high"), "auroc_high_ci": r.get("auroc_high_ci"),
                    "auprc_high": r.get("auprc_high"), "auroc_low": r.get("auroc_low"),
                    "coverage90": r.get("coverage90", {}).get("60"), "width90": r.get("width90", {}).get("60"),
                    "recon_rmse": r["reconstruction"]["rmse"],
                    "exploratory": {h: {"rmse": v["rmse"], "coverage90": v["coverage90"], "width90": v["width90"]}
                                    for h, v in r["exploratory_horizons"]["horizons"].items()}} for r in lad],
        "protocol_change": protocol_change(old, lad, tr),
        "manifest": {"path": "artifacts/manifest.json", "model_version": manifest["model_version"],
                     "leakage_checks_passed": len(checks)},
        "limitations": LIMITATIONS,
    })
    make_figures()


LIMITATIONS = [
    "No open Indian CGM dataset exists; the twin was trained and tested on US (CGMacros) and Chinese (ShanghaiT2DM) adults. Indian meals are handled through an Indian food composition table, not Indian training data.",
    "Every CGMacros result assumes a 5-day CGM calibration wear before the finger-prick-only phase; the twin is not sensor-free.",
    "Finger-pricks in the CGMacros experiments are simulated from the hidden CGM with 5% glucometer error; only the ShanghaiT2DM transfer arm uses real capillary readings.",
    "CGMacros records last about 10 days, so calibration windows of 1-7 days were tested instead of the 3-14 days in the plan.",
    "Most CGMacros participants are not on glucose-lowering drugs; 51% of ShanghaiT2DM patients use insulin, which the model does not represent explicitly.",
    "Forecasts are validated up to 120 minutes; 180-240 minute points are exploratory (residual and band extrapolated).",
    "P(<70 in 2 h) is not validated (too few low events). Next-best-prick timing is experimental (paired CIs cross zero).",
    "What-if scenarios are model simulations, not proven causal effects. The 90-day outlook is a projection from the twin's daily profile, not a validated HbA1c prediction.",
    "This is decision support, not a medical device, and it has not been clinically validated.",
]


# ----------------------------------------------------------------------------- analyses
def _pair(a2: pd.DataFrame, a0: pd.DataFrame) -> pd.DataFrame:
    return a2.merge(a0.drop(columns=["person"]), on=["pid", "t"], suffixes=("", "_none"))


def recent_prick_value(a2: pd.DataFrame, a0: pd.DataFrame) -> dict:
    pair = _pair(a2, a0)
    near = pair[pair.hours_since_obs < 1.5]
    rp: dict[str, Any] = {
        "definition": ("Forecast origins within 90 minutes after a finger-prick (2 pricks/day arm) compared with the same "
                       "people and clock times when the twin had no glucose data after calibration."),
        **counts(near), "n_forecasts": int(len(near)), "n_patients": int(near.person.nunique()),
        "rmse_with_prick": {}, "rmse_without": {}}
    for h in HORIZONS:
        rp["rmse_with_prick"][str(h)] = MT.rmse(near[f"true_{h}"].to_numpy(), near[f"pred_{h}"].to_numpy())
        rp["rmse_without"][str(h)] = MT.rmse(near[f"true_{h}_none"].to_numpy(), near[f"pred_{h}_none"].to_numpy())
    rp["rmse60_difference_ci"] = MT.bootstrap_by_person(
        near, lambda d: MT.rmse(d["true_60"].to_numpy(), d["pred_60"].to_numpy())
        - MT.rmse(d["true_60_none"].to_numpy(), d["pred_60_none"].to_numpy()), n_boot=N_BOOT)
    return rp


def _width_block(sub: pd.DataFrame, label: str) -> dict:
    out: dict[str, Any] = {"subset": label, **counts(sub), "by_horizon": {}}
    for h in HORIZONS:
        lo, hi, lo0, hi0 = (sub[c].to_numpy() for c in (f"lo_{h}", f"hi_{h}", f"lo_{h}_none", f"hi_{h}_none"))
        y = sub[f"true_{h}"].to_numpy()
        ok = np.isfinite(lo) & np.isfinite(hi) & np.isfinite(lo0) & np.isfinite(hi0)
        cw, _ = MT.coverage(y, lo, hi)
        c0, _ = MT.coverage(y, lo0, hi0)
        def width_diff(d: pd.DataFrame, h: int = h) -> float:
            return float(np.mean((d[f"hi_{h}"] - d[f"lo_{h}"]).to_numpy()
                                 - (d[f"hi_{h}_none"] - d[f"lo_{h}_none"]).to_numpy()))

        diff = MT.bootstrap_by_person(sub[ok], width_diff, n_boot=N_BOOT)
        out["by_horizon"][str(h)] = {
            "mean_width_with_pricks": float(np.mean(hi[ok] - lo[ok])),
            "mean_width_without_glucose": float(np.mean(hi0[ok] - lo0[ok])),
            "paired_difference": diff[0], "paired_difference_ci95": [diff[1], diff[2]],
            "coverage90_with_pricks": cw, "coverage90_without_glucose": c0}
    return out


def paired_band_width(a2: pd.DataFrame, a0: pd.DataFrame) -> dict:
    """Controlled 'living uncertainty' evidence: the SAME forecast origins (person, time) with the
    2 pricks/day schedule vs with no glucose data after calibration."""
    pair = _pair(a2, a0)
    return {
        "definition": ("Paired at identical forecast origins (same person, same time): band width of the 90% "
                       "forecast band with 2 finger-pricks/day vs with no glucose data after the 5-day CGM "
                       "calibration. paired_difference = with - without (negative = narrower with pricks); "
                       "95% CI by bootstrap over people."),
        "recent_prick": _width_block(pair[pair.hours_since_obs < 1.5], "origins within 90 min after a prick"),
        "control_far_from_prick": _width_block(pair[pair.hours_since_obs >= 8], "origins >= 8 h after a prick"),
    }


def by_hours_since_reading(a2: pd.DataFrame) -> list[dict]:
    out = []
    for lo, hi in [(0, 1.5), (1.5, 4), (4, 8), (8, 99)]:
        g = a2[(a2.hours_since_obs >= lo) & (a2.hours_since_obs < hi)]
        cv, w = MT.coverage(g["true_60"].to_numpy(), g["lo_60"].to_numpy(), g["hi_60"].to_numpy())
        out.append({"hours_since_reading": f"{lo}-{hi if hi < 99 else '+'}", "n": int(len(g)), **counts(g),
                    "rmse60": MT.rmse(g["true_60"].to_numpy(), g["pred_60"].to_numpy()),
                    "coverage90_60": cv, "width90_60": w})
    return out


def paired_baselines(a: pd.DataFrame) -> dict:
    out = {}
    for name, pfx in BASELINE_METHODS.items():
        col = f"{pfx}60"
        ok = np.isfinite(a["true_60"]) & np.isfinite(a["pred_60"]) & np.isfinite(a[col])
        sub = a[ok]

        def fn(dd: pd.DataFrame, col: str = col) -> float:
            y = dd["true_60"].to_numpy()
            return MT.rmse(y, dd["pred_60"].to_numpy()) - MT.rmse(y, dd[col].to_numpy())

        diff = MT.bootstrap_by_person(sub, fn, n_boot=N_BOOT)
        out[name] = {"rmse60_full_hybrid": MT.rmse(sub["true_60"].to_numpy(), sub["pred_60"].to_numpy()),
                     "rmse60_baseline": MT.rmse(sub["true_60"].to_numpy(), sub[col].to_numpy()),
                     "difference": diff[0], "difference_ci95": [diff[1], diff[2]],
                     "ci_excludes_zero": bool(diff[2] < 0 or diff[1] > 0), **counts(sub)}
    return out


def nbp_value(res: dict[str, pd.DataFrame], d: Data) -> dict:
    nb = {}
    per_person = {}
    for name, cfg in (("fixed (07:00 & 22:00)", "ladder_2"), ("random", "nbp_random"), ("twin-recommended", "nbp_twin")):
        a = res[cfg]
        rc = d.recon[cfg]
        nb[name] = {**summarise(a, boot=True), "reconstruction": recon_summary(rc),
                    "meal_anchored": summarise(a[a.meal_origin])}
        mm = rc[rc.phase == "maint"]
        per_person[name] = pd.Series({k: MT.rmse(g["true"].to_numpy(), g["mu"].to_numpy())
                                      for k, g in mm.groupby("person")})
    diffs = {}
    for other in ("fixed (07:00 & 22:00)", "random"):
        dd = (per_person["twin-recommended"] - per_person[other]).dropna()
        rng = np.random.default_rng(1)
        boots = [rng.choice(dd.to_numpy(), len(dd)).mean() for _ in range(2000)]
        diffs[f"twin_minus_{other.split(' ')[0]}"] = {
            "mean_recon_rmse_change": float(dd.mean()),
            "ci95": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
            "patients_improved": int((dd < 0).sum()), "n_patients": int(len(dd)), "n_people": int(len(dd))}
    return {"title": "Value of next-best-prick placement (Experiment 4)",
            "status": "experimental",
            "protocol": ("2 finger-pricks per day in every arm; only their timing differs. Negative change = twin better. "
                         "Per-person reconstruction RMSE; 95% CI by bootstrap over people."),
            "arms": nb, "paired_differences": diffs}


def transfer(d: Data, res: dict[str, pd.DataFrame]) -> tuple[dict, dict, dict]:
    out: dict[str, Any] = {
        "title": "Cross-population transfer (Experiment 5)",
        "protocol": ("In-domain = nested person-wise 5-fold CV within the dataset (prior, residual model, conformal and "
                     "calibrators fitted on other folds' people; training rows replayed with priors that also exclude "
                     "the test fold). Transfer = prior, hybrid and calibrators fitted on ALL people of the other dataset "
                     "only (no target-dataset person in any training dependency; asserted in artifacts/manifest.json). "
                     "ShanghaiT2DM 'real finger-pricks' uses the dataset's own capillary blood glucose readings in the "
                     "maintenance phase. CIs bootstrap over people (repeat Shanghai recordings resampled together)."),
        "rows": []}
    sh_res, sh_folds = apply_outer(d, SH_IN, "shanghai")
    # CGMacros -> Shanghai: hybrid on every CGMacros person's outer-test replays (priors: CGMacros only)
    cg_tr = _cat([d.test[c] for c in LADDER_CFGS])
    b_cg = HY.fit_hybrid(*cg_tr, seed=0)
    sh_tr = _cat([d.test[c] for c in SH_IN])
    b_sh = HY.fit_hybrid(*sh_tr, seed=0)
    cg_people = sorted(set(d.cov.loc[d.cov.dataset == "cgmacros", "person"]))
    sh_people = sorted(set(d.cov.loc[d.cov.dataset == "shanghai", "person"]))

    def deps(bundle: HY.HybridBundle, rows: pd.DataFrame, cfgs: Iterable[str]) -> dict[str, list[str]]:
        priors: set[str] = set()
        for c in cfgs:
            for v in d.test_prior_people[c].values():
                priors |= set(v)
        out_d = {"hybrid_training_rows": sorted(set(rows.person)), "train_replay_priors": sorted(priors)}
        for k, v in bundle.membership.items():
            if k != "inner_folds" and v is not None:
                out_d[f"hybrid.{k}"] = v
        return out_d

    def test_priors(cfg: str) -> list[str]:
        s: set[str] = set()
        for v in d.test_prior_people[cfg].values():
            s |= set(v)
        return sorted(s)

    tr_mem = {
        "cgmacros_to_shanghai": {"test_people": sh_people, "training_dependencies": {
            **deps(b_cg, cg_tr[0], LADDER_CFGS), "test_replay_priors": test_priors("sh_from_cg_2")}},
        "shanghai_to_cgmacros": {"test_people": cg_people, "training_dependencies": {
            **deps(b_sh, sh_tr[0], SH_IN), "test_replay_priors": test_priors("cg_from_sh_2")}},
    }

    def row(test: str, train: str, setting: str, frame: pd.DataFrame, rc: pd.DataFrame) -> dict:
        return {"test": test, "train": train, "setting": setting, **summarise(frame, boot=True),
                "reconstruction": recon_summary(rc)}

    sh_x2 = b_cg.apply(*d.test["sh_from_cg_2"])
    sh_xcbg = b_cg.apply(*d.test["sh_from_cg_cbg"])
    cg_x = b_sh.apply(*d.test["cg_from_sh_2"])
    out["rows"] = [
        row("ShanghaiT2DM", "ShanghaiT2DM (in-domain)", "2 simulated pricks/day", sh_res["sh_in_2"], d.recon["sh_in_2"]),
        row("ShanghaiT2DM", "CGMacros (transfer)", "2 simulated pricks/day", sh_x2, d.recon["sh_from_cg_2"]),
        row("ShanghaiT2DM", "ShanghaiT2DM (in-domain)", "real finger-pricks", sh_res["sh_in_cbg"], d.recon["sh_in_cbg"]),
        row("ShanghaiT2DM", "CGMacros (transfer)", "real finger-pricks", sh_xcbg, d.recon["sh_from_cg_cbg"]),
        row("CGMacros", "CGMacros (in-domain)", "2 simulated pricks/day", res["ladder_2"], d.recon["ladder_2"]),
        row("CGMacros", "ShanghaiT2DM (transfer)", "2 simulated pricks/day", cg_x, d.recon["cg_from_sh_2"]),
    ]
    ins = dict(zip(d.cov.pid, d.cov.insulin_user, strict=True))
    sh_x2["insulin"] = sh_x2.pid.map(ins)
    out["shanghai_by_insulin"] = {
        "insulin_users": summarise(sh_x2[sh_x2.insulin == True]),  # noqa: E712
        "no_insulin": summarise(sh_x2[sh_x2.insulin == False]),  # noqa: E712
    }
    rp = {r["setting"] + " | " + r["train"]: r["rmse"]["60"] for r in out["rows"]}
    out["gap_rmse60"] = {
        "shanghai_2pricks": rp["2 simulated pricks/day | CGMacros (transfer)"] - rp["2 simulated pricks/day | ShanghaiT2DM (in-domain)"],
        "shanghai_real_pricks": rp["real finger-pricks | CGMacros (transfer)"] - rp["real finger-pricks | ShanghaiT2DM (in-domain)"],
        "cgmacros_2pricks": rp["2 simulated pricks/day | ShanghaiT2DM (transfer)"] - rp["2 simulated pricks/day | CGMacros (in-domain)"],
    }
    return out, sh_folds, tr_mem


def subgroups(a: pd.DataFrame, cov: pd.DataFrame) -> dict:
    c = cov.set_index("pid")
    a = a.copy()
    a["sex"] = a.pid.map(c["sex"])
    a["age_band"] = pd.cut(a.pid.map(c["age"]), [0, 40, 55, 120], labels=["<40", "40-54", "55+"]).astype(str)
    a["bmi_band"] = pd.cut(a.pid.map(c["bmi"]), [0, 23, 25, 100], right=False,
                           labels=["<23", "23-24.9", ">=25"]).astype(str)
    a["hba1c_band"] = pd.cut(a.pid.map(c["hba1c"]), [0, 5.7, 6.5, 20], right=False,
                             labels=["<5.7 (normal)", "5.7-6.4 (prediabetes)", ">=6.5 (diabetes)"]).astype(str)
    overall = summarise(a)
    rows = []
    for col, title in (("sex", "Sex"), ("age_band", "Age"), ("bmi_band", "BMI (Asian cut-offs)"), ("hba1c_band", "HbA1c")):
        for val, g in a.groupby(col):
            s = summarise(g)
            cov60 = s.get("coverage90", {}).get("60")
            ece = s.get("ece_high")
            flagged = bool((cov60 is not None and cov60 < 0.82) or
                           (ece is not None and np.isfinite(ece) and ece > 2 * overall["ece_high"] + 0.02))
            rows.append({"dimension": title, "group": str(val), "n_patients": s["n_patients"], "n_people": s["n_people"],
                         "n_forecast_windows": s["n_forecast_windows"],
                         "rmse60": s["rmse"]["60"], "coverage90_60": cov60, "auroc_high": s.get("auroc_high"),
                         "ece_high": ece, "flagged": flagged})
    return {"title": "Subgroup audit (Experiment 6), 2 pricks/day", "overall": {
        "rmse60": overall["rmse"]["60"], "coverage90_60": overall["coverage90"]["60"], "ece_high": overall["ece_high"]},
        "flag_rule": "coverage of the 90% band below 82% at 60 min, or ECE more than twice overall + 0.02",
        "rows": rows}


def protocol_change(old: dict | None, lad: list[dict], tr: dict) -> dict:
    """Old (pre-nested) vs new headline numbers."""
    new_l = {r["level"]: r for r in lad}
    new = {"ladder_2": {"rmse60": new_l["2"]["rmse"]["60"], "auroc_high": new_l["2"].get("auroc_high"),
                        "coverage90_60": new_l["2"]["coverage90"]["60"], "width90_60": new_l["2"]["width90"]["60"]},
           "full": {"rmse60": new_l["full"]["rmse"]["60"]},
           "transfer_gap_rmse60_shanghai_2pricks": tr["gap_rmse60"]["shanghai_2pricks"]}
    out: dict[str, Any] = {
        "description": ("Before: Stage-1 replays were fitted once per patient with a prior that excluded only that "
                        "patient's own fold, and the same replays were reused as training rows for every outer fold, "
                        "so the population prior behind a training row could include the outer-test people "
                        "(indirect leakage through feature construction). Hybrid inner folds and bootstrap CIs were "
                        "grouped by recording. After: nested outer-fold protocol, inner folds and CIs by person, "
                        "deterministic parameter fits (stable seeds), LightGBM deterministic mode."),
        "new": new}
    if old is None:
        out["old"] = None
        out["note"] = "pre-nested headline archive not found"
        return out
    ol = old["ladder"]
    old_v = {"ladder_2": {"rmse60": ol["2"]["rmse60"], "auroc_high": ol["2"]["auroc_high"],
                          "coverage90_60": ol["2"]["coverage90_60"], "width90_60": ol["2"]["width90_60"]},
             "full": {"rmse60": ol["full"]["rmse60"]},
             "transfer_gap_rmse60_shanghai_2pricks": old["transfer_gap_rmse60"]["shanghai_2pricks"]}
    out["old"] = old_v
    out["old_source"] = "reports/archive/pre_nested_protocol/headline.json"
    out["delta_new_minus_old"] = {
        "ladder_2": {k: (new["ladder_2"][k] - v) if v is not None and new["ladder_2"][k] is not None else None
                     for k, v in old_v["ladder_2"].items()},
        "full": {"rmse60": new["full"]["rmse60"] - old_v["full"]["rmse60"]},
        "transfer_gap_rmse60_shanghai_2pricks": new["transfer_gap_rmse60_shanghai_2pricks"]
        - old_v["transfer_gap_rmse60_shanghai_2pricks"]}
    return out


# ----------------------------------------------------------------------------- manifest
def build_manifest(membership: dict, d: Data, n_prod_people: int) -> dict:
    code, code_files = S.code_hash()
    data, data_files = S.data_hash()
    art_names = ["prior_cgmacros.json", "prior_shanghai.json", "param_fits.parquet", "hybrid_cgmacros.pkl"]
    arts = {n: sha256_file(MODELS_DIR / n) for n in art_names}
    model_version = "pf-" + hashlib.sha256((arts["prior_cgmacros.json"] + arts["hybrid_cgmacros.pkl"]).encode()
                                           ).hexdigest()[:12]
    prod_prior = P.production_people(d.cov, "cgmacros")
    summary = {}
    for scope, rec in membership["outer_folds"].items():
        summary[scope] = {f: {"n_test_people": len(r["test_people"]),
                              "n_people_per_dependency": {k: len(v) for k, v in r["training_dependencies"].items()}}
                          for f, r in rec.items()}
    return {
        "generated_at": _now(), "generated_by": "nemotwins.eval.experiments",
        "model_version": model_version,
        "code_hash": code, "code_hash_scope": "sha256 over nemotwins/twin/*.py + nemotwins/eval/*.py",
        "code_files": code_files,
        "stage1_code_hash": S.stage1_code_hash(),
        "stage1_fingerprint": S.fingerprint(),
        "data_hash": data, "data_files": data_files, "data_scope": "sha256 over data/processed/*.parquet",
        "artifacts": arts,
        "hybrid_trained_on": {
            "dataset": "CGMacros v1.0.0", "n_people": n_prod_people,
            "excluded_people": list(S.PERSONA_PIDS),
            "reason": ("The three demo personas are built on these CGMacros participants; excluding them makes the "
                       "personas people the production prior and hybrid never saw."),
            "training_rows": ("stage-1 replays of every other CGMacros participant at all sensor-ladder levels, each "
                              "with a prior fitted on people outside its own fold and outside the persona sources")},
        "prior_cgmacros_trained_on": {"n_people": len(prod_prior), "people": prod_prior,
                                      "excluded_people": list(S.PERSONA_PIDS)},
        "config": {
            "n_folds": S.N_FOLDS, "seed": S.SEED, "fold_unit": "person",
            "folds": {pid: f for pid, f in sorted(d.folds.items())},
            "stage1_configs": [{"name": c.name, "key": c.key(), "dataset": c.dataset, "prior": c.prior,
                                "kwargs": c.kwargs, "policy": c.policy, "nested": c.nested,
                                "production": c.production, "extended": c.extended} for c in S.all_configs()],
            "hybrid": {"lgb_params": HY.LGB_PARAMS, "clf_params": HY.CLF_PARAMS, "alpha": HY.ALPHA,
                       "inner_folds": 3, "inner_fold_unit": "person"},
            "horizons_validated": list(HORIZONS), "horizons_exploratory": list(XH),
        },
        "membership": membership,
        "membership_summary": summary,
    }


# ----------------------------------------------------------------------------- figures
def make_figures() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir = REPORTS_DIR / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    def save(name: str) -> None:
        tmp = fig_dir / f".{name}.tmp.png"
        plt.savefig(tmp, dpi=160)
        plt.close()
        os.replace(tmp, fig_dir / name)

    lad = json.loads((REPORTS_DIR / "sensor_ladder.json").read_text())["levels"]
    plt.figure(figsize=(6.4, 3.6))
    for r in lad:
        hs = [int(h) for h in r["rmse"]]
        plt.plot(hs, list(r["rmse"].values()), marker="o", label=r["label"])
    plt.xlabel("Forecast horizon (min)")
    plt.ylabel("RMSE (mg/dL)")
    plt.title("Sensor ladder: accuracy vs glucose data available (held-out people)")
    plt.legend(fontsize=8)
    plt.grid(alpha=0.3)
    plt.tight_layout()
    save("sensor_ladder.png")
    cc = json.loads((REPORTS_DIR / "calibration_curve.json").read_text())["levels"]
    plt.figure(figsize=(4, 4))
    plt.plot([0, 1], [0, 1], "k--", lw=1)
    for lvl in ("full", "2", "0"):
        b = cc[lvl]["high"]
        x = np.array([v["mean_pred"] for v in b])
        y = np.array([v["observed"] for v in b])
        err = np.array([[v["observed"] - v["ci_lo"] for v in b], [v["ci_hi"] - v["observed"] for v in b]])
        plt.errorbar(x, y, yerr=err, marker="o", capsize=2, label=f"{lvl}")
    plt.xlabel("Predicted P(>180 in 2 h)")
    plt.ylabel("Observed frequency (Wilson 95%)")
    plt.legend(title="ladder", fontsize=8)
    plt.tight_layout()
    save("calibration_high.png")
    sl = json.loads((REPORTS_DIR / "sensor_ladder.json").read_text())
    pb = sl["paired_band_width"]
    plt.figure(figsize=(5.6, 3.6))
    for key, ls in (("recent_prick", "-"), ("control_far_from_prick", ":")):
        blk = pb[key]["by_horizon"]
        hs = [int(h) for h in blk]
        plt.plot(hs, [blk[h]["mean_width_with_pricks"] for h in blk], marker="o", ls=ls, color="#2a78d6",
                 label=f"2 pricks/day - {pb[key]['subset']}")
        plt.plot(hs, [blk[h]["mean_width_without_glucose"] for h in blk], marker="s", ls=ls, color="#c0392b",
                 label="no glucose data - same origins")
    plt.xlabel("Forecast horizon (min)")
    plt.ylabel("Mean 90% band width (mg/dL)")
    plt.title("Paired band width at identical forecast origins", fontsize=9.5)
    plt.legend(fontsize=7)
    plt.grid(alpha=0.3)
    plt.tight_layout()
    save("paired_band_width.png")
    print("  wrote reports/figures/*.png", flush=True)


def _cli(argv: list[str]) -> None:
    if "--check" in argv:
        res = check_manifest()
        print(json.dumps(res, indent=1))
        if not res["ok"]:
            raise SystemExit(1)
        return
    main()


if __name__ == "__main__":
    _cli(sys.argv[1:])
