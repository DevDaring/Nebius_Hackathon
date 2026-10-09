"""Response models for the Twin API (spec section 4.6, docs/API_CONTRACT.md).

They document the endpoints in OpenAPI and validate every twin response against the
contract. ``extra="allow"`` keeps additive fields (e.g. ``p_low_validated``), so the
models never strip anything the frontend may read.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _M(BaseModel):
    model_config = ConfigDict(extra="allow")


class Reliability(_M):
    """Held-out reliability of the calibration bin containing p (reports/calibration_curve.json)."""

    pred_lo: float | None
    pred_hi: float | None
    observed: float | None
    n: int
    ci_lo: float | None
    ci_hi: float | None
    source: str


class Prob(_M):
    """No particle-binomial interval. P(>180): validated=true + reliability; P(<70): validated=false."""

    p: float = Field(ge=0, le=1)
    freq_text: str
    validated: bool
    reliability: Reliability | None = None


class Band(_M):
    lo: float
    hi: float


class Quantiles(_M):
    t: list[str]
    q05: list[float | None]
    q25: list[float | None]
    q50: list[float | None]
    q75: list[float | None]
    q95: list[float | None]
    validated_horizon_min: int | None = Field(None, description="points beyond this horizon are exploratory")


class Reading(_M):
    t: str
    value: float
    kind: Literal["cgm", "fingerprick", "lab"]
    source: str | None = Field(None, description="dataset | manual | chat | replay")


class MealEventOut(_M):
    t: str
    name: str
    carbs: float


class Driver(_M):
    name: str
    label_en: str
    contribution: float
    source: Literal["physiology", "learned"]


class Abstain(_M):
    flag: bool
    reason: str | None


class Peak(_M):
    t: str
    value: float


class PriorInput(_M):
    value: Any
    source: str
    date: str | None = None


class Provenance(_M):
    model_version: str
    hybrid_trained_on: str
    inputs_revision: int
    prior_inputs: dict[str, PriorInput]
    observations_used: int
    replay_now: str


class Forecast(_M):
    forecast_id: str
    origin: str
    horizon_min: int
    traj: Quantiles
    p_high: Prob
    p_low: Prob
    p_low_validated: bool = Field(False, description="P(<70) is not validated: too few lows in the training data")
    peak: Peak
    conformal_level: float
    abstain: Abstain
    drivers: list[Driver]
    provenance: Provenance | None = None


class Candidate(_M):
    t: str
    gain_pct: float


class NextBestPrick(_M):
    time: str | None
    expected_gain_pct: float
    reason: str
    candidates: list[Candidate]


class Freshness(_M):
    score: float
    hours_since_reading: float
    label: Literal["fresh", "ageing", "stale"]


class Series(_M):
    t: list[str]
    v: list[float]


class History(_M):
    virtual_cgm: Quantiles
    readings: list[Reading]
    true_cgm: Series | None = None
    meals: list[MealEventOut]
    steps: Series


class Target(_M):
    lo: float
    hi: float


class Replay(_M):
    now: str
    day: int
    offset_min: int
    max_offset_min: int
    label_en: str
    mode: Literal["replay"]


class TwinState(_M):
    now: str
    ladder: Literal["full", "4", "2", "1", "0"]
    estimate: float
    band: Band
    freshness: Freshness
    last_observation: Reading | None
    abstain: Abstain
    ess: float
    history: History
    forecast: Forecast
    next_best_prick: NextBestPrick
    target: Target
    p_low_validated: bool = False
    replay: Replay | None = None


class Delta(_M):
    mean: float
    lo: float
    hi: float


class WhatIf(_M):
    baseline: Forecast
    scenario: Forecast
    delta_p_high: Delta
    delta_peak: float
    too_small_to_call: bool
    note: str
    label_en: str | None = Field(None, description="'Model simulation — not a proven effect'")
    assumptions_en: list[str] | None = None


class SafetyResult(_M):
    """The shared reading-safety policy (agent/safety.py assess_reading)."""

    level: Literal["ok", "low", "very_low", "high", "very_high"]
    emergency: bool
    title: str
    message: str
    actions: list[str]


class WidthNow(_M):
    before: float
    after: float
    signed_pct: float


class WidthH(WidthNow):
    horizon_min: int


class WidthChange(_M):
    now: WidthNow
    h120: WidthH


class Assimilation(_M):
    state: TwinState
    band_before: Band
    band_after: Band
    narrowed_pct: float = Field(description="= -width_change.h120.signed_pct (negative = the band widened)")
    innovation: float
    safety: SafetyResult | None = None
    width_change: WidthChange | None = None


class Outlook(_M):
    label: Literal["projection"]
    days: list[int]
    tir_current: list[float]
    tir_scenario: list[float]
    ehba1c_current: list[float]
    ehba1c_scenario: list[float]
    scenario_label: str
    note: str


class ToolCall(_M):
    name: str
    args: dict[str, Any]
    output: Any
    contract: dict[str, Any] | None = Field(None, description="contract tool name, schema version, execution id, "
                                                               "engine version, status, source, interval semantics")


class Explanation(_M):
    physiology: list[Driver]
    learned: list[Driver]
    tool_calls: list[ToolCall]
    text_en: str


class Ok(_M):
    ok: bool


class Grounding(_M):
    passed: bool
    numbers: list[str]
    fallback_used: bool


class Safety(_M):
    blocked: bool
    emergency: bool
    reason: str | None
    level: str | None = Field(None, description="reading level when the message reported a reading")


class Claim(_M):
    slot: str
    field: str
    value: Any
    rendered: str


class PendingActionOut(_M):
    id: str
    kind: Literal["log_reading", "log_meal"]
    summary_en: str
    payload: dict[str, Any]


class Highlight(_M):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    view: Literal["stage", "forecast", "whatif", "nbp", "none"]
    from_: str | None = Field(None, alias="from", description="ISO start of the time window the reply is about")
    to: str | None = Field(None, description="ISO end of that window")


class AgentReply(_M):
    reply: str
    lang: Literal["en-US", "es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP"]
    intent: str
    tool_calls: list[ToolCall]
    grounding: Grounding
    safety: Safety
    highlight: Highlight
    audio_url: str | None = Field(None, description="Always null in NemoTwins (no speech provider)")
    source: Literal["fixture", "live"]
    source_detail: str = Field("", description="rules | template | router ... | provider:model | template fallback after ...")
    claims: list[Claim] = Field(default_factory=list, description="every number in the reply, bound to a tool field")
    pending_action: PendingActionOut | None = Field(None, description="a proposed mutation; confirm via /api/agent/confirm")
    # --- agent contract (docs/API_CONTRACT_AGENT.md)
    execution_id: str | None = None
    schema_version: str | None = None
    clarification: dict[str, Any] | None = Field(None, description="one question (portion | unit) before simulating")
    disclosures: list[dict[str, Any]] = Field(default_factory=list, description="stale_data | exploratory | "
                                              "ranking_uncertain | fallback | not_validated | wider_range")
    checks: dict[str, str] | None = Field(None, description="numbers: verifier result; guardrails_input/output status")
    model: dict[str, Any] | None = Field(None, description="provider, model_id, live")
    references: dict[str, Any] | None = Field(None, description="further reading from allowlisted health sites "
                                              "(Tavily search; topic-only query; never shown to the model)")


# ----------------------------------------------------------------------------- body view
class FluxSeries(_M):
    q10: list[float]
    q50: list[float]
    q90: list[float]


class BloodSeries(_M):
    q05: list[float]
    q50: list[float]
    q95: list[float]


class BodyVariant(_M):
    forecast_id: str
    blood: BloodSeries
    fluxes: dict[str, FluxSeries]
    learned_correction: list[float]


class OrganMeta(_M):
    key: str
    label_en: str
    unit: str
    description_en: str
    status: Literal["simulated"]


class BodyView(_M):
    """Per-organ flows of the simplified physiology model at 'now' and every 5 min for 4 h.

    t[0] is the replay now; series have len(t) points. Organ flows are SIMULATED; only blood
    glucose is validated (reports/). ``scenario`` is present when a scenario was requested."""

    persona_id: str
    replay_now: str
    t: list[str]
    validated_horizon_min: int
    label_en: str
    validated_en: str
    organs: list[OrganMeta]
    baseline: BodyVariant
    scenario: BodyVariant | None = None
    scenario_label: str | None = None
