# Optional: deploying NemoTwins on Nebius AI Cloud

The public demo is self-hosted ([`SELF_HOSTING.md`](SELF_HOSTING.md)). This document describes an
alternative, fully scripted deployment on Nebius AI Cloud. It has not been applied:
`deploy/nebius/deploy.sh plan` runs read-only against an account and creates nothing.

## Target architecture

```
browser ──HTTPS──▶ Nebius AI Serverless endpoint "nemotwins"  (one container, cpu-e2, port 8000)
                    ├─ FastAPI /api + built React SPA (STATIC_DIR)
                    ├─ twin engine (numpy / LightGBM, CPU)            ── no GPU needed
                    ├─ NeMo Guardrails (library, in-process)
                    └──HTTPS──▶ Nebius Token Factory (Nemotron 3 Nano / Super, Gemma 3 vision)
                    └──private network──▶ Managed PostgreSQL 16 "nemotwins-db" (app state, backups 7 d)
secrets: MysteryBox "nemotwins-runtime" → --env-secret (TOKENFACTORY_2009_API_KEY, JWT_SECRET, DATABASE_URL)
batch:   Serverless Job (same image) → multilingual evaluation → Object Storage bucket (mounted) for reports
```

* **Why CPU:** inference runs on Token Factory; the twin engine is CPU numpy/LightGBM. No measured
  numerical bottleneck justifies a GPU (see `docs/PROVIDER_CAPABILITIES.md`).
* **Why one container:** one managed HTTPS URL, no CORS, simplest rollback.
* **Durability:** app state lives in Managed PostgreSQL (backups, 7-day retention). The container
  disk is ephemeral and is used only for caches. Reports from evaluation jobs go to an Object
  Storage bucket mounted into the job (`--volume s3://BUCKET:/app/reports/jobs`).

## Credentials (two different things)

| Variable | What it is | Used by |
|---|---|---|
| `TOKENFACTORY_2009_API_KEY` | Token Factory inference key | the app (runtime secret) |
| `NEBUIS_CLOUD_API_KEY` | Cloud credential slot (spelling intentional). Mode `iam_token`: an IAM access token from `nebius iam get-access-token` (short-lived, about 12 h). Mode `service_account`: ignored; use `NEBIUS_SERVICE_ACCOUNT_ID` + `NEBIUS_PUBLIC_KEY_ID` + `NEBIUS_PRIVATE_KEY_FILE` or `NEBIUS_CREDENTIALS_FILE` | admin page read-only identity check only; never the agent, never the frontend |
| CLI profile `nemotwins` | federated user login (`nebius profile create`) | the deploy scripts |

The Token Factory key does not authorise Cloud provisioning, and the Cloud credential does not
authorise inference. The app's read-only Cloud check (`/api/admin/integrations?probe=1`) uses IAM
`whoami` only — verified 2026-10-08 with a fresh IAM token ("Authenticated as a user").

## Verified facts about this account (read-only, 2026-10-08)

| Check | Result |
|---|---|
| `nebius iam whoami` | active federated user, tenant active |
| project | `default-project-eu-north1`, region `eu-north1` |
| network | `default-network` exists |
| compute platforms | `cpu-d3`, `cpu-e2` (2/4/8 vCPU presets), several GPU platforms |
| Managed PostgreSQL | CLI `msp postgresql v1alpha1` available; docs: version 16, platform `cpu-e2`, disk `network-ssd` only |
| existing endpoints / jobs / registries / buckets | none |
| `nebius ai endpoint create … --dry-run` | **PermissionDenied** (request `90a2a1b3-e632-45eb-95e4-02977716865a`) — see blockers |

## Steps

```bash
export PATH="$HOME/.nebius/bin:$PATH"          # if `nebius` is not found after install: exec -l $SHELL
deploy/nebius/deploy.sh plan                    # read-only + dry-run; prints every create command
deploy/nebius/deploy.sh apply                   # creates: registry, image push, PostgreSQL, secret, endpoint
deploy/nebius/smoke.sh https://<endpoint-host>  # health, capabilities, SPA, login, one Spanish chat turn, readiness
TAG=<image tag> deploy/nebius/run_eval_job.sh plan|apply   # multilingual suite as a Serverless Job
```

`apply` order: (1) `nebius registry create` + `configure-helper` + `docker build -f deploy/Dockerfile`
+ push to `cr.eu-north1.nebius.cloud/<registry id without "registry-">/nemotwins:<git sha>`;
(2) `nebius msp postgresql v1alpha1 cluster create` (private, 1 host, 7-day backups) — wait for
`Running`, read the private host, put `DATABASE_URL` into `.env` or the environment; (3)
`nebius mysterybox secret create` with the three runtime keys (values read from `.env`, never
printed); (4) `nebius ai endpoint create --platform cpu-e2 --preset 4vcpu-16gb --container-port
8000/http --env-secret …`. The public URL is in `status.public_endpoints` of `nebius ai endpoint get-by-name --name nemotwins`.

Health and readiness: `GET /api/health` (process + configured model, no external calls) and
`GET /api/ready` (database reachable **and** twin warm; 503 until both). Schema migrations run at
start-up (`init_db`, additive only). Uvicorn runs one worker (in-process rate limits and forecast
ownership) and drains requests on SIGTERM (20 s).

## Public-demo bounds

Per-user rate limits (`RATE_CHAT_PER_MIN=20` in the endpoint), `LLM_MAX_CONCURRENT_REQUESTS=4`,
`LLM_MAX_TOOL_STEPS=6`, a local daily token quota (`DAILY_INFERENCE_TOKEN_LIMIT`, a guard rail, not a
billing cap — Token Factory metering is authoritative), demo log-in required for every model-backed
endpoint, upload size limits, and evaluation jobs capped by `EVAL_MAX_CASES_PER_JOB` and `--timeout 2h`.
Unauthenticated visitors cannot trigger inference or Cloud jobs.

## Cost assumptions (to confirm against the live price list before `apply`)

Not verified here; no price is asserted. Billable items: one always-on `cpu-e2 4vcpu-16gb` endpoint,
one `cpu-e2 2vcpu-8gb` PostgreSQL host + 20 GiB SSD + backups, registry storage, Token Factory tokens
(the admin page shows per-model token counts), short evaluation jobs. Set `MONTHLY_CLOUD_BUDGET_USD`
/ `DAILY_INFERENCE_BUDGET_USD` for documentation and use Nebius billing alerts for an actual cap.
Idle behaviour: the endpoint keeps running (and billing) until `nebius ai endpoint stop --id <id>`.

## Rollback

* App: `nebius ai endpoint delete --id <id>` and re-create with the previous image tag (tags are
  immutable git SHAs), or `stop` / `start` to pause billing.
* Database: restore from the managed backup (7 days); the schema is additive-only, so an older image
  runs against a newer database.
* Secrets: `nebius mysterybox secret-version` — set the previous version primary.

## Blockers before a real deployment

1. **AI Serverless permission.** `nebius ai endpoint create --dry-run` returned PermissionDenied for
   the `nemotwins` profile. Check in the console that the user has an editor/admin role on
   `default-project-eu-north1` and that AI Serverless (endpoints/jobs) is enabled for the tenant and
   covered by billing/credits; then re-run `deploy/nebius/deploy.sh plan`.
2. **Budget agreement** for the always-on endpoint and database (the scripts never run `apply` by themselves).
3. **Object Storage access keys** (S3-compatible) for report persistence — an IAM token is not an S3 secret.
4. Container image not built yet on this machine (`docker build -f deploy/Dockerfile .` — needs the
   package rename to be committed first).
