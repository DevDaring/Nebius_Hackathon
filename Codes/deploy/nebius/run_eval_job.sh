#!/usr/bin/env bash
# Run the multilingual agent evaluation as a Nebius AI Serverless Job (batch, outside patient requests).
#
#   deploy/nebius/run_eval_job.sh plan    # DEFAULT: `nebius ai job create --dry-run` only
#   deploy/nebius/run_eval_job.sh apply   # starts the job (billable; bounded by --timeout and EVAL_MAX_CASES_PER_JOB)
#
# Uses the image pushed by deploy.sh. Inference goes to Token Factory (key from MysteryBox). If
# NEBIUS_OBJECT_STORAGE_BUCKET is set, the bucket is mounted at /app/reports/jobs so the versioned report
# survives the job (an ephemeral container directory is NOT durable storage); otherwise read the
# report from the job logs (`nebius ai job logs`).
set -euo pipefail
MODE="${1:-plan}"
[[ "$MODE" == "plan" || "$MODE" == "apply" ]] || { echo "usage: $0 plan|apply" >&2; exit 2; }
export PATH="$HOME/.nebius/bin:$PATH"
# JSON helper (python3 instead of jq): `... | pyq 'expr' [args]` evaluates expr with d = parsed stdin, a = args.
pyq() { python3 -c 'import json,sys; d=json.load(sys.stdin); a=sys.argv[2:]; r=eval(sys.argv[1]); print(r if isinstance(r,str) else json.dumps(r, ensure_ascii=False))' "$@"; }
NAME="${NAME:-nemotwins}"
PROJECT_ID="${NEBIUS_PROJECT_ID:-$(nebius config get parent-id)}"
REGION="${NEBIUS_REGION:-eu-north1}"
TAG="${TAG:?set TAG to the image tag pushed by deploy.sh}"
REGISTRY_ID="$(nebius registry list --parent-id "$PROJECT_ID" --format json | pyq "next((i['metadata']['id'] for i in d.get('items',[]) if i['metadata']['name']==a[0]), '')" "$NAME")"
IMAGE="cr.$REGION.nebius.cloud/${REGISTRY_ID#registry-}/$NAME:$TAG"
SECRET_NAME="${SECRET_NAME:-$NAME-runtime}"
REPEATS="${REPEATS:-1}"
ARGS=(--name "$NAME-eval-$(date +%Y%m%d-%H%M)" --parent-id "$PROJECT_ID" --image "$IMAGE"
      --platform cpu-e2 --preset 4vcpu-16gb --disk-size 40Gi --on-demand --timeout 2h --restart-policy never
      --container-command "python -m nemotwins.eval.agent_multilingual --mode live --repeats $REPEATS --out-dir /app/reports/jobs"
      --env APP_MODE=live --env EVAL_MAX_CASES_PER_JOB="${EVAL_MAX_CASES_PER_JOB:-200}"
      --env-secret "TOKENFACTORY_2009_API_KEY=$SECRET_NAME")
if [[ -n "${NEBIUS_OBJECT_STORAGE_BUCKET:-}" ]]; then
  ARGS+=(--volume "s3://$NEBIUS_OBJECT_STORAGE_BUCKET:/app/reports/jobs:rw")
fi
if [[ "$MODE" == "plan" ]]; then
  nebius ai job create "${ARGS[@]}" --dry-run
else
  nebius ai job create "${ARGS[@]}"
  echo "follow: nebius ai job logs --name <job-name>"
fi
