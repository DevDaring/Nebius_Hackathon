# Provider capabilities (Nebius Token Factory + NVIDIA)

Machine-readable version: `backend/capabilities/manifest.json` (regenerate:
`APP_MODE=live python -m nemotwins.eval.provider_smoke`). Checked 2026-10-08 against this account.

## Models

| Role | Model id (exact) | NVIDIA | Verified on 2026-10-08 |
|---|---|---|---|
| Planner + explanation | `nvidia/nemotron-3-super-120b-a12b` | yes | in catalog; text in 6 locales, tool calling, JSON object, JSON schema |
| Router, NeMo Guardrails rails | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | yes | in catalog; text in 6 locales, tool calling, JSON object, JSON schema |
| Meal-photo dish candidates | `google/gemma-3-27b-it` | **no** | image input + JSON on a sample photo; used only because no NVIDIA vision model is offered |

Other NVIDIA models in the catalog, not used: `nvidia/Nemotron-3-Ultra-550b-a55b` (not needed);
`nvidia/Nemotron-3_5-Lightning` (in JSON mode it put its reasoning text into the answer and hit the token
limit). Nemotron 3 Nano rejects image input ("This model does not support image input").

Languages: en, es, fr, de, it, ja — the list on the NVIDIA-Nemotron-3-Nano-30B-A3B model card. The smoke
suite confirms a reply in each; behaviour quality is measured by the multilingual suite
(`docs/EVALUATION.md`), not assumed from the card.

## Request settings that matter

| Setting | Value | Why (measured) |
|---|---|---|
| Base URL | `https://api.tokenfactory.nebius.com/v1` (normalised, no `/v1/v1`) | |
| Reasoning | `chat_template_kwargs.enable_thinking=false` for router, rails and planner | Nemotron 3 reasons by default and reasoning tokens count against `max_tokens`: ~300 hidden tokens for a one-line answer; with tools the planner overran 3,000 tokens and took 20–100 s. Off: ~0.7 s per call. `NEMOTRON_PLANNER_THINKING=true` re-enables it |
| Planner model | Super (`NEMOTRON_PLANNER_MODEL=complex`) | Nano without thinking misused slots and contradicted tool results more often in our tests; Super wrote accurate explanations at 3–5 s per turn |
| `tool_choice` | `required` on the first round of data questions | Token Factory accepts it; without it the model sometimes asked the user for values the tools provide |
| Timeouts / retries | 30 s read, 5 s connect, 2 retries for timeouts, 429 and 5xx only; 1 retry for an invalid answer; none for 401/403/400 | |
| Concurrency | 4 parallel requests per process | |

## Integrations

| Integration | Status | Notes |
|---|---|---|
| Nemotron via Token Factory | **implemented, verified** | live dev and held-out suites (EVALUATION.md) |
| Token Factory tool calling / structured output | **implemented, verified** | tool calling and JSON schema in the smoke suite; every response still validated server-side |
| NVIDIA NeMo Guardrails 0.24.1 (library) | **implemented, verified** | self-check input/output rails on Nemotron 3 Nano via the OpenAI-compatible endpoint |
| Nebius AI Cloud auth | **implemented, verified (read-only)** | IAM-token mode: whoami OK with a fresh token; service-account mode implemented, not exercised |
| Public hosting | **live** | self-hosted at https://nemotwins.koushikdeb.com (Caddy + uvicorn), see SELF_HOSTING.md |
| Nebius Serverless endpoint hosting | **optional, not deployed** | `deploy/nebius/deploy.sh`; `--dry-run` currently PermissionDenied for the user (see NEBIUS_DEPLOYMENT.md) |
| Nebius Serverless Jobs (evaluation) | **configured, not run** | `deploy/nebius/run_eval_job.sh` |
| Nebius Object Storage (reports) | **configured, untested** | mounted into the eval job when a bucket and S3 keys exist |
| Nebius Managed PostgreSQL | **configured, not created** | step 2 of deploy.sh |
| Vision (dish candidates) | **implemented, verified, non-NVIDIA** | Gemma 3 on Token Factory; candidates only, user confirms, nutrition from the food table |
| NVIDIA embeddings | **not used** | no retrieval needed; no NVIDIA embedding model in the catalog |
| Further reading (Tavily web-search API) | **implemented, verified** | not a model call (`include_answer` off); Nemotron picks a topic via JSON schema; only the topic's fixed query is sent; results limited to allowlisted health sites per language; snippets shown, never given to the model; 24 h cache |
| Speech (ASR/TTS) | **unavailable** | no speech model on Token Factory; other providers not allowed |
| GPU numerical acceleration | **not used** | no measured bottleneck that a GPU would address |
