# NemoTwins architecture

## Components

```
Browser (React 18 + Vite, six locales, Intl formatting, central mg/dL ↔ mmol/L conversion)
   │  HTTPS, JWT bearer (demo accounts), no secrets in the bundle
   ▼
FastAPI  nemotwins/api/main.py  (one process; SPA served from STATIC_DIR in the container)
   ├─ auth + per-user scoping (events, replay clock, labs, pending actions, audit) ─────► PostgreSQL 16
   ├─ Twin API  twin/engine.py   the ONLY source of glucose numbers (estimate, bands, forecasts, what-ifs)
   │     model.py (ODE) · calibrate.py (CEM) · filter.py (Liu–West PF) · hybrid.py (LightGBM residual,
   │     conformal, calibrated events) · nbp.py (experimental next reading) · artifacts/ (fitted, frozen)
   ├─ Agent  agent/orchestrator.py  (bounded pipeline, below)
   │     contracts.py (typed tools, clarification policy, evidence receipt) · safety.py · verifier.py
   │     slots.py · templates.py · lexicon.py · nemo_text.py
   ├─ NeMo Guardrails  guardrails/  (open-source library, self-check input/output rails)
   ├─ Providers
   │     llm.py ──HTTPS──► Nebius Token Factory (OpenAI-compatible): Nemotron 3 Super (planner),
   │                        Nemotron 3 Nano (router, rails), Gemma 3 27B (meal-photo dish candidates)
   │     nebius_cloud.py ──gRPC──► Nebius IAM whoami (admin page only, read-only)
   │     speech.py  (unavailable: no Token Factory speech model)
   │     tavily.py ──HTTPS──► Tavily search API (topic query only; allowlisted health sites; display-only results)
   └─ Perception  meal.py (vision → dish candidates → food table) · lab.py · food.py (INDB/IFCT/USDA table)
```

## Agent pipeline (one chat turn)

1. **Deterministic safety** (`safety.py`): emergency symptoms, very low/high readings, dose or medicine
   changes, diagnosis requests, prompt injection — six languages. A hit returns a fixed, reviewed message.
2. **Evidence questions** (validation, populations, long-term outcomes, next-year HbA1c) → a fixed answer
   filled from `get_evidence_receipt` (values read from `reports/summary.json`).
3. **NeMo Guardrails input rail** (Nemotron 3 Nano, thinking off). Blocked → localised refusal, no tools.
4. **Clarification** (`contracts.py`): at most ONE question — unit for a bare decimal reading, or portion for
   a meal forecast in which no dish has a quantity (asked about the dish with the most carbohydrate). The
   options are the user's own message with the amount inserted. Skip → the usual portion with carbohydrate
   SD widened from 20 % to 50 % (the engine propagates it into its bands), disclosed as `wider_range`.
5. **Routing**: rules first; the LLM router (Nano) only when rules are unsure; its emergency label is
   authoritative, its dose label defers to the rail.
6. **Tool loop** (Nemotron 3 Super, thinking off, ≤ `LLM_MAX_TOOL_STEPS`): contract tools only
   (`get_twin_state`, `get_forecast`, `lookup_food`, `simulate_scenarios` (≤ 3 per turn),
   `preview_reading_update`, `preview_meal`, `explain_forecast`, `next_best_reading`, `outlook_projection`,
   `get_evidence_receipt`); anything else is refused. The first round must call a tool for data questions.
   Patient identity comes from the session, never from model arguments. Reported readings use the
   deterministic path (unit conversion in code).
7. **Checks**: slots rendered from tool fields; every remaining digit must be grounded in this turn's tool
   outputs, the user's text or fixed thresholds (`verifier.py`); medication policy; script / sentence checks;
   **NeMo Guardrails output rail**. Any failure → regenerate once → approved localised template, labelled
   `template fallback after <model>` with a `fallback` disclosure (never shown as a live answer).
8. **Disclosures**: `stale_data` (from the engine's freshness), `exploratory` (any what-if),
   `ranking_uncertain` (difference within simulation variability), `not_validated` (P(<70)),
   `wider_range`, `fallback`.
9. **Further reading** (education / evidence questions only): Nemotron picks one topic from a fixed list
   (JSON schema); the topic's canonical query — never the user's words — goes to the Tavily search API with a
   per-language allowlist of public-health and diabetes-society sites; results are filtered on the exact host
   and shown as quoted links under the reply. They are never passed to the model.
10. **Audit**: tool calls, contract metadata (schema version, execution id, engine version, status, interval
   semantics), checks and model id. Raw conversation text is not stored (`AUDIT_STORE_TEXT=false`).

Mutations (adding a reading or a meal) are only *proposed* in chat and performed by
`/api/agent/confirm` through the same safety policy as manual entry.

## Trust boundaries

| Boundary | Rule |
|---|---|
| Browser ↔ API | JWT; per-user scoping on every query; upload size limits; rate limits on model-backed endpoints |
| API ↔ Token Factory | key from `TOKENFACTORY_2009_API_KEY` (runtime secret); request/response content never logged; local token quota |
| Agent ↔ engine | allowlisted contract tools only; bounded arguments; no shell, SQL, HTTP fetch, Cloud control or messaging tools |
| Model output ↔ user | numeric verifier is authoritative; a rail can block but never approve an ungrounded number |
| API ↔ Nebius Cloud | `NEBUIS_CLOUD_API_KEY` used only by the admin page's read-only whoami; never reachable from the agent |
| Text in meal names / uploads | treated as data; injection patterns flagged and refused |
| API ↔ Tavily | only fixed topic queries leave the app; results are display-only (React-escaped text, `rel=noopener noreferrer nofollow`) and never enter a model prompt |

## Data paths

* **Engine inputs**: frozen artefacts (fitted on CGMacros; CC BY-NC-SA) + this user's events. Language never
  changes engine inputs: dishes map to the same food ids in every language (one alias → one id, tested).
* **Model calls**: prompt = system rules + the user's message + tool outputs of this turn (synthetic persona
  data). Sent to Nebius Token Factory only.
* **Stored**: users, events, replay clock, pending actions, lab revisions, reviews, redacted audit log.
* **Reports**: generated by `nemotwins.eval.*` into `backend/reports/` (or a mounted Object Storage bucket
  when run as a Nebius Serverless Job).
