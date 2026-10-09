"""Stage 1 of every experiment: replay patients through the twin (cached, parallel).

Each job = (config, replay tag, patient). The *tag* names the population prior the
replay used, i.e. which people that prior was fitted on:

* ``x<g>``        prior fitted on the dataset's people outside fold ``g`` (the patient's own
                  fold). Used for the patient's OUTER-TEST replay.
* ``x<f><g>``     prior fitted on people outside folds ``f`` and ``g``. Used when the patient
                  (fold ``g``) is a TRAINING row of the outer-fold-``f`` hybrid, so no learned
                  dependency of the fold-``f`` hybrid has seen a fold-``f`` person
                  (nested outer-fold protocol; ``Config.nested``).
* ``x<g>-np``     as ``x<g>`` but also without the demo-persona source participants; training
                  rows of the production (app) hybrid (``Config.production``).
* ``all``         prior fitted on every person of the other dataset (transfer arms).

Results are cached in ``data/cache/<config key>/<tag>/<pid>.pkl``. The config key includes a
fingerprint of the stage-1 source code, the processed data and the parameter fits, so a stale
cache is never reused after the code or the data change. Folds are assigned per PERSON.
"""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import multiprocessing as mp
import os
import pickle
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from nemotwins.config import DATA_DIR, PROCESSED_DIR
from nemotwins.twin import filter as PF
from nemotwins.twin import model as M
from nemotwins.twin import nbp
from nemotwins.twin import prior as P
from nemotwins.twin.personas import PERSONAS
from nemotwins.twin.runner import LADDER_LEVELS, REST, RunResult, build_timeline, run_patient

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
CACHE = DATA_DIR / "cache"
N_FOLDS = 5
SEED = 2026
PERSONA_PIDS = tuple(sorted(p["source_pid"] for p in PERSONAS))
XH = (180, 240)  # exploratory horizons (beyond the validated 120 min)
TWIN_DIR = Path(P.__file__).parent
EVAL_DIR = Path(__file__).parent
# Source files stage 1 actually executes; their hash is part of every cache key (personas.py
# matters only through PERSONA_PIDS, which is hashed directly).
STAGE1_SOURCES = tuple(TWIN_DIR / f for f in (
    "model.py", "filter.py", "calibrate.py", "runner.py", "prior.py", "nbp.py")) + (
    EVAL_DIR / "stage1.py",)


# ----------------------------------------------------------------------------- fingerprints
def sha256_files(paths: Iterable[Path], root: Path | None = None) -> tuple[str, dict[str, str]]:
    h = hashlib.sha256()
    per: dict[str, str] = {}
    for p in sorted(paths):
        b = p.read_bytes()
        name = str(p.relative_to(root)) if root else p.name
        per[name] = hashlib.sha256(b).hexdigest()
        h.update(name.encode() + b"\0" + b)
    return h.hexdigest(), per


def code_hash() -> tuple[str, dict[str, str]]:
    """sha256 over ``twin/*.py`` + ``eval/*.py`` (recorded in the manifest)."""
    files = [*TWIN_DIR.glob("*.py"), *EVAL_DIR.glob("*.py")]
    return sha256_files(files, TWIN_DIR.parent)


def stage1_code_hash() -> str:
    return sha256_files(STAGE1_SOURCES, TWIN_DIR.parent)[0]


def data_hash() -> tuple[str, dict[str, str]]:
    return sha256_files(sorted(PROCESSED_DIR.glob("*.parquet")))


@cache
def fingerprint() -> str:
    """Stage-1 cache version: stage-1 code + processed data + parameter fits."""
    h = hashlib.sha256()
    h.update(stage1_code_hash().encode())
    h.update(data_hash()[0].encode())
    h.update(hashlib.sha256(P.PARAM_FITS.read_bytes()).hexdigest().encode())
    h.update(repr((PERSONA_PIDS, N_FOLDS, SEED)).encode())
    return h.hexdigest()[:16]


# ----------------------------------------------------------------------------- data, folds
def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    ts = pd.read_parquet(PROCESSED_DIR / "timeseries.parquet")
    cov = pd.read_parquet(PROCESSED_DIR / "covariates.parquet")
    if "person" not in cov:
        cov = cov.assign(person=cov["pid"])
    return ts, cov


def person_of(cov: pd.DataFrame) -> dict[str, str]:
    return dict(zip(cov.pid.astype(str), cov.person.astype(str), strict=True))


def assign_folds(cov: pd.DataFrame) -> dict[str, int]:
    """Deterministic patient-wise folds, stratified by dataset and glycaemic group."""
    folds: dict[str, int] = {}
    rng = np.random.default_rng(SEED)
    person = cov["person"] if "person" in cov else cov["pid"]
    cov = cov.assign(person=person)
    for _, g in cov.groupby(["dataset", "group"]):
        # Folds are assigned per PERSON so repeat recordings never straddle train/test.
        people = sorted(g.person.unique())
        rng.shuffle(people)
        fold_of = {p: k % N_FOLDS for k, p in enumerate(people)}
        for pid, per in zip(g.pid, g.person, strict=True):
            folds[pid] = fold_of[per]
    return folds


# ----------------------------------------------------------------------------- policies
def policy_random(pf: PF.ParticleFilter, ctx: dict, i: int) -> list[float]:  # noqa: ARG001
    rng = ctx["rng"]
    while True:
        a, b = sorted(rng.uniform(7.0, 22.5, 2))
        if b - a >= 3.0:
            return [float(a), float(b)]


def policy_twin(pf: PF.ParticleFilter, ctx: dict, i: int) -> list[float]:
    tl = ctx["tl"]
    return nbp.plan(pf.snapshot(150), float(tl.hour[i]), ctx["meal_profile"], k=2, rng=ctx["rng"])


POLICIES: dict[str, Callable[[PF.ParticleFilter, dict, int], list[float]]] = {
    "random": policy_random, "twin": policy_twin}


# ----------------------------------------------------------------------------- configs
@dataclass
class Config:
    name: str
    dataset: str  # patients to run
    prior: str  # "cv" (other folds, same dataset) or "cgmacros"/"shanghai" (all of that dataset)
    kwargs: dict = field(default_factory=dict)
    policy: str | None = None
    nested: bool = False  # also replay with priors excluding each other outer fold (hybrid training rows)
    production: bool = False  # also replay with a prior excluding the demo personas (app hybrid rows)
    extended: bool = False  # capture exploratory 180/240-min forecasts on outer-test replays

    def key(self) -> str:
        h = hashlib.md5(repr((self.dataset, self.prior, sorted(self.kwargs.items()), self.policy,
                              fingerprint())).encode())
        return f"{self.name}-{h.hexdigest()[:8]}"


def all_configs() -> list[Config]:
    cfgs = []
    for lvl in LADDER_LEVELS:  # Exp. 1 (headline)
        cfgs.append(Config(f"ladder_{lvl}", "cgmacros", "cv", {"ladder": lvl, "calib_days": 5.0},
                           nested=True, production=True, extended=True))
    for d in (1.0, 3.0, 5.0, 7.0):  # Exp. 2 (dataset spans ~10 days, so 1/3/5/7 instead of 3/7/10/14)
        cfgs.append(Config(f"calib_{int(d)}", "cgmacros", "cv",
                           {"ladder": "2", "calib_days": d, "eval_from_days": 7.0}))
    for pol in ("random", "twin"):  # Exp. 4 ("fixed" == ladder_2)
        cfgs.append(Config(f"nbp_{pol}", "cgmacros", "cv", {"ladder": "2", "calib_days": 5.0}, pol))
    # Exp. 5 transfer. Shanghai CGM is 15-min native, so no extra thinning.
    sh = {"calib_thin": 1}
    cfgs.append(Config("sh_in_2", "shanghai", "cv", {"ladder": "2", **sh}, nested=True))
    cfgs.append(Config("sh_in_cbg", "shanghai", "cv", {"ladder": "2", "use_real_cbg": True, **sh}, nested=True))
    cfgs.append(Config("sh_from_cg_2", "shanghai", "cgmacros", {"ladder": "2", **sh}))
    cfgs.append(Config("sh_from_cg_cbg", "shanghai", "cgmacros", {"ladder": "2", "use_real_cbg": True, **sh}))
    cfgs.append(Config("cg_from_sh_2", "cgmacros", "shanghai", {"ladder": "2", "calib_days": 5.0}))
    return cfgs


def config_by_name(name: str) -> Config:
    return next(c for c in all_configs() if c.name == name)


# ----------------------------------------------------------------------------- replay tags
ALL_TAG = "all"


def test_tag(fold: int) -> str:
    """Outer-test replay of a fold-``fold`` patient: prior excludes its own fold."""
    return f"x{fold}"


def train_tag(own_fold: int, outer_fold: int) -> str:
    """Training-row replay of a fold-``own_fold`` patient for the outer-fold-``outer_fold`` hybrid."""
    if own_fold == outer_fold:
        raise ValueError("an outer-test patient cannot be a training row of its own fold")
    return "x" + "".join(str(k) for k in sorted({own_fold, outer_fold}))


def prod_tag(fold: int) -> str:
    return f"x{fold}-np"


def parse_tag(tag: str) -> tuple[set[int], bool]:
    """(excluded folds, personas excluded) for a ``x..`` tag."""
    body, _, suffix = tag.partition("-")
    return {int(c) for c in body[1:]}, suffix == "np"


def replay_tags(cfg: Config, pid: str, folds: dict[str, int]) -> list[str]:
    if cfg.prior != "cv":
        return [ALL_TAG]
    g = folds[pid]
    tags = [test_tag(g)]
    if cfg.nested:
        tags += [train_tag(g, f) for f in range(N_FOLDS) if f != g]
    if cfg.production and pid not in PERSONA_PIDS:
        tags.append(prod_tag(g))
    return tags


def prior_people(cfg: Config, tag: str, cov: pd.DataFrame, folds: dict[str, int]) -> list[str]:
    """People whose parameter fits train the prior used by a replay with this tag."""
    if tag == ALL_TAG:
        return sorted(set(cov.loc[cov.dataset == cfg.prior, "person"].astype(str)))
    excl, no_personas = parse_tag(tag)
    sub = cov[cov.dataset == cfg.dataset]
    keep = ~sub.pid.map(folds).isin(excl)
    if no_personas:
        keep &= ~sub.person.isin(PERSONA_PIDS)
    return sorted(set(sub.loc[keep, "person"].astype(str)))


def fit_prior_for(people: Iterable[str], fits: pd.DataFrame, cov: pd.DataFrame) -> P.PopulationPrior:
    pids = cov.loc[cov.person.isin(set(people)), "pid"]
    return P.fit_prior(fits[fits.pid.isin(pids)], cov)


# ----------------------------------------------------------------------------- results
@dataclass
class Stage1Run:
    result: RunResult
    meta: dict[str, Any]


def run_path(cfg: Config, tag: str, pid: str) -> Path:
    return CACHE / cfg.key() / tag / f"{pid}.pkl"


def _atomic_pickle(obj: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    with open(tmp, "wb") as f:
        pickle.dump(obj, f)
    os.replace(tmp, path)


# ----------------------------------------------------------------------------- exploratory horizons
class ExtendedCapture:
    """While active, every ``filter.forecast_batch`` call made by ``run_patient`` ALSO runs an
    independent 4-hour propagation (own RNG, so the 2-hour forecasts, and thus every validated
    result, are bit-identical to a normal run) and keeps the 180/240-min summaries.

    Inputs beyond the runner's 2-hour window: no new meals (only the origin meal is known, as
    in the runner), activity at rest, the last slow-absorption factor held. Used only inside
    stage-1 worker processes."""

    def __init__(self, seed: int) -> None:
        self.rng = np.random.default_rng([seed, 180, 240])
        self.parts: list[dict[str, np.ndarray]] = []
        self.steps = max(XH) // int(M.DT)
        self._orig: Callable[..., np.ndarray] | None = None

    def __enter__(self) -> ExtendedCapture:
        self._orig = PF.forecast_batch
        PF.forecast_batch = self._wrapped  # type: ignore[assignment]
        return self

    def __exit__(self, *exc: object) -> None:
        if self._orig is not None:
            PF.forecast_batch = self._orig  # type: ignore[assignment]

    def _wrapped(self, snaps: list, carbs: np.ndarray, slow: np.ndarray, mets: np.ndarray, hour: np.ndarray,
                 rng: np.random.Generator, process_noise: bool = True) -> np.ndarray:
        assert self._orig is not None
        out = self._orig(snaps, carbs, slow, mets, hour, rng, process_noise)
        h, n = carbs.shape
        extra = self.steps - h
        if extra > 0:
            k = np.arange(1, extra + 1)[:, None]
            carbs = np.vstack([carbs, np.zeros((extra, n))])
            slow = np.vstack([slow, np.repeat(slow[-1:], extra, axis=0)])
            mets = np.vstack([mets, np.full((extra, n), REST)])
            hour = np.vstack([hour, (hour[-1:] + k * M.DT / 60.0) % 24.0])
        traj = self._orig(snaps, carbs, slow, mets, hour, self.rng, process_noise)
        idx = [hh // int(M.DT) - 1 for hh in XH]
        sel = traj[:, :, idx]
        self.parts.append({"med": np.median(sel, axis=1), "sd": sel.std(axis=1),
                           "q05": np.quantile(sel, 0.05, axis=1), "q95": np.quantile(sel, 0.95, axis=1)})
        return out

    def attach(self, res: RunResult, df: pd.DataFrame) -> None:
        o = res.origins
        if len(o) == 0 or not self.parts:
            return
        tl = build_timeline(df)
        n = len(tl.t)
        cat = {k: np.concatenate([p[k] for p in self.parts]) for k in ("med", "sd", "q05", "q95")}
        if len(cat["med"]) != len(o):
            raise RuntimeError("exploratory capture does not match the forecast origins")
        oi = o["idx"].to_numpy(int)
        for c, hh in enumerate(XH):
            for k in ("med", "sd", "q05", "q95"):
                o[f"x{k}_{hh}"] = cat[k][:, c]
            j = oi + hh // int(M.DT)
            ok = j < n
            jj = np.minimum(j, n - 1)
            o[f"true_{hh}"] = np.where(ok & tl.cgm_native[jj], tl.cgm[jj], np.nan)


# ----------------------------------------------------------------------------- jobs
def _job(args: tuple) -> tuple[str, str, str, str]:
    cfg, tag, pid, df, prior_med, prior_sd, covd, meta = args
    path = CACHE / meta["config_key"] / tag / f"{pid}.pkl"  # key fixed at planning time
    if path.exists():
        return cfg.name, tag, pid, "cached"
    kw = dict(cfg.kwargs)
    if cfg.dataset == "shanghai" and "calib_days" not in kw:
        span = (df.t.max() - df.t.min()).total_seconds() / 86400
        kw["calib_days"] = float(min(5.0, max(1.5, 0.45 * span)))
    extended = cfg.extended and tag == test_tag(meta["fold"]) if cfg.prior == "cv" else False
    try:
        policy = POLICIES.get(cfg.policy) if cfg.policy else None
        if extended:
            with ExtendedCapture(SEED) as cap:
                res = run_patient(df, prior_med, prior_sd, seed=SEED, covariates=covd, prick_policy=policy, **kw)
            cap.attach(res, df)
        else:
            res = run_patient(df, prior_med, prior_sd, seed=SEED, covariates=covd, prick_policy=policy, **kw)
    except Exception as exc:  # noqa: BLE001
        return cfg.name, tag, pid, f"error: {exc!r}"
    _atomic_pickle(Stage1Run(res, {**meta, "extended_horizons": list(XH) if extended else []}), path)
    return cfg.name, tag, pid, "ok"


def plan_jobs(cfgs: list[Config]) -> list[tuple]:
    ts, cov = load()
    fits = P.load_fits()
    folds = assign_folds(cov)
    person = person_of(cov)
    groups = dict(tuple(ts.groupby("pid")))
    jobs = []
    for cfg in cfgs:
        prior_cache: dict[tuple[str, ...], P.PopulationPrior] = {}
        for pid in sorted(cov.loc[cov.dataset == cfg.dataset, "pid"]):
            for tag in replay_tags(cfg, pid, folds):
                if run_path(cfg, tag, pid).exists():
                    continue
                people = tuple(prior_people(cfg, tag, cov, folds))
                if person[pid] in people:  # never happens by construction; guard anyway
                    raise AssertionError(f"{pid}: own person in prior membership ({cfg.name}/{tag})")
                if people not in prior_cache:
                    prior_cache[people] = fit_prior_for(people, fits, cov)
                covd = cov.loc[cov.pid == pid].iloc[0].to_dict()
                med, sd = prior_cache[people].predict(covd)
                meta = {"config": cfg.name, "config_key": cfg.key(), "tag": tag, "pid": pid, "person": person[pid],
                        "fold": folds[pid], "prior_people": list(people), "fingerprint": fingerprint()}
                jobs.append((cfg, tag, pid, groups[pid], med, sd, covd, meta))
    return jobs


def run_configs(cfgs: list[Config] | None = None, workers: int = 30) -> None:
    cfgs = cfgs or all_configs()
    jobs = plan_jobs(cfgs)
    # longest records first for better load balance
    jobs.sort(key=lambda j: -len(j[3]))
    print(f"stage1 (fingerprint {fingerprint()}): {len(jobs)} jobs to run", flush=True)
    done, errors = 0, 0
    with cf.ProcessPoolExecutor(workers, mp_context=mp.get_context("spawn")) as ex:
        for name, tag, pid, status in ex.map(_job, jobs, chunksize=1):
            done += 1
            errors += status.startswith("error")
            if status != "ok" or done % 100 == 0:
                print(f"  [{done}/{len(jobs)}] {name}/{tag} {pid} {status}", flush=True)
    if errors:
        raise SystemExit(f"stage1: {errors} jobs failed")


class _Unpickler(pickle.Unpickler):
    """Resolve ``Stage1Run`` to this module even if a pickle names ``__main__``/``__mp_main__``."""

    def find_class(self, module: str, name: str) -> Any:
        if name == "Stage1Run" and module in {"__main__", "__mp_main__"}:
            return Stage1Run
        return super().find_class(module, name)


def load_runs(cfg: Config, tags: Iterable[str] | None = None) -> dict[str, dict[str, Stage1Run]]:
    """``{tag: {pid: Stage1Run}}`` for the cached replays of ``cfg`` (optionally only ``tags``)."""
    root = CACHE / cfg.key()
    wanted = set(tags) if tags is not None else None
    out: dict[str, dict[str, Stage1Run]] = {}
    for d in sorted(p for p in root.glob("*") if p.is_dir()):
        if wanted is not None and d.name not in wanted:
            continue
        runs: dict[str, Stage1Run] = {}
        for p in sorted(d.glob("*.pkl")):
            with open(p, "rb") as f:
                runs[p.stem] = _Unpickler(f).load()
        out[d.name] = runs
    return out


def load_test_runs(cfg: Config) -> dict[str, Stage1Run]:
    """One replay per patient: its outer-test replay (prior excludes its own fold), or the
    transfer replay (prior fitted on the other dataset)."""
    _, cov = load()
    folds = assign_folds(cov)
    if cfg.prior != "cv":
        return load_runs(cfg, [ALL_TAG]).get(ALL_TAG, {})
    tags = {test_tag(f) for f in range(N_FOLDS)}
    out: dict[str, Stage1Run] = {}
    for tag, runs in load_runs(cfg, tags).items():
        for pid, r in runs.items():
            if tag == test_tag(folds[pid]):
                out[pid] = r
    return out


def expected_keys() -> set[str]:
    return {c.key() for c in all_configs()}


if __name__ == "__main__":
    import sys

    # Run through the importable module so pickled results reference nemotwins.eval.stage1.
    from nemotwins.eval import stage1 as _stage1

    _stage1.run_configs(workers=int(sys.argv[1]) if len(sys.argv) > 1 else 30)
