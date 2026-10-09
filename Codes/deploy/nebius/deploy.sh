#!/usr/bin/env bash
# NemoTwins -> Nebius AI Cloud (Serverless endpoint + Managed PostgreSQL + MysteryBox + Container Registry).
#
#   deploy/nebius/deploy.sh plan     # DEFAULT. Read-only lookups + `nebius ai endpoint create --dry-run`. Creates nothing.
#   deploy/nebius/deploy.sh apply    # Creates/updates billable resources. Run only with an agreed budget.
#
# Prerequisites: nebius CLI with an active profile (`nebius profile create`), docker, python3.
# Secrets are read from the local .env WITHOUT printing them and stored in MysteryBox; they are never
# passed on the command line of the endpoint, baked into the image, or written to disk by this script.
# Every command used here was checked against `nebius <cmd> --help` of CLI 0.12.287 (2026-10-08).
set -euo pipefail

MODE="${1:-plan}"
[[ "$MODE" == "plan" || "$MODE" == "apply" ]] || { echo "usage: $0 plan|apply" >&2; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PATH="$HOME/.nebius/bin:$PATH"

# ---------------------------------------------------------------- settings (override via environment)
NAME="${NAME:-nemotwins}"
PROJECT_ID="${NEBIUS_PROJECT_ID:-$(nebius config get parent-id 2>/dev/null || true)}"
REGION="${NEBIUS_REGION:-eu-north1}"
PLATFORM="${PLATFORM:-cpu-e2}"              # CPU only: inference runs on Token Factory, not on this VM
PRESET="${PRESET:-4vcpu-16gb}"              # engine warm-up + LightGBM; 2vcpu-8gb is the minimum tested shape
DISK="${DISK:-40Gi}"
PG_PRESET="${PG_PRESET:-2vcpu-8gb}"          # Managed PostgreSQL: platform cpu-e2, disk network-ssd (only options)
PG_DISK_GIB="${PG_DISK_GIB:-20}"
PG_DB="${PG_DB:-nemotwins}"
PG_USER="${PG_USER:-nemotwins}"
TAG="${TAG:-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M)}"
SECRET_NAME="${SECRET_NAME:-$NAME-runtime}"

[[ -n "$PROJECT_ID" ]] || { echo "No project id: set NEBIUS_PROJECT_ID or create a CLI profile" >&2; exit 2; }
# JSON helper (python3 instead of jq): `... | pyq 'expr' [args]` evaluates expr with d = parsed stdin, a = args.
pyq() { python3 -c 'import json,sys; d=json.load(sys.stdin); a=sys.argv[2:]; r=eval(sys.argv[1]); print(r if isinstance(r,str) else json.dumps(r, ensure_ascii=False))' "$@"; }
say() { printf '\n== %s\n' "$*"; }
run() { if [[ "$MODE" == "apply" ]]; then "$@"; else printf '   [plan] would run: %s\n' "$*"; fi; }

say "Identity (read-only)"
nebius iam whoami --format json | pyq "'   authenticated as a ' + ('user' if 'user_profile' in d else 'service account')"
echo "   project=$PROJECT_ID region=$REGION mode=$MODE image tag=$TAG"

# ---------------------------------------------------------------- 1. container registry + image
say "1. Container Registry"
REGISTRY_ID="$(nebius registry list --parent-id "$PROJECT_ID" --format json | pyq "next((i['metadata']['id'] for i in d.get('items',[]) if i['metadata']['name']==a[0]), '')" "$NAME")"
if [[ -z "$REGISTRY_ID" ]]; then
  echo "   registry '$NAME' does not exist"
  run nebius registry create --name "$NAME" --parent-id "$PROJECT_ID"
  [[ "$MODE" == "apply" ]] && REGISTRY_ID="$(nebius registry list --parent-id "$PROJECT_ID" --format json | pyq "next((i['metadata']['id'] for i in d.get('items',[]) if i['metadata']['name']==a[0]), '')" "$NAME")"
fi
REGISTRY_PATH="${REGISTRY_ID#registry-}"
IMAGE="cr.$REGION.nebius.cloud/${REGISTRY_PATH:-<registry-id>}/$NAME:$TAG"
echo "   image: $IMAGE"
run nebius registry configure-helper
run docker build -f "$ROOT/deploy/Dockerfile" --build-arg "GIT_COMMIT=$TAG" -t "$IMAGE" "$ROOT"
run docker push "$IMAGE"

# ---------------------------------------------------------------- 2. managed PostgreSQL (durable app state)
say "2. Managed PostgreSQL"
NETWORK_ID="$(nebius vpc network list --parent-id "$PROJECT_ID" --format json | pyq "(d.get('items') or [{'metadata':{'id':''}}])[0]['metadata']['id']")"
PG_ID="$(nebius msp postgresql v1alpha1 cluster list --parent-id "$PROJECT_ID" --format json 2>/dev/null | pyq "next((i['metadata']['id'] for i in d.get('items',[]) if i['metadata']['name']==a[0]), '')" "$NAME-db" || true)"
if [[ -z "$PG_ID" ]]; then
  echo "   cluster '$NAME-db' does not exist (network ${NETWORK_ID:-?})"
  if [[ "$MODE" == "apply" ]]; then
    PG_PASSWORD="$(python3 -c 'import secrets,string; a=string.ascii_letters+string.digits; print("Nt-"+"".join(secrets.choice(a) for _ in range(28))+"!a")')"
    nebius msp postgresql v1alpha1 cluster create --name "$NAME-db" --parent-id "$PROJECT_ID" --network-id "$NETWORK_ID" \
      --config-version 16 --config-public-access=false \
      --config-template-resources-platform cpu-e2 --config-template-resources-preset "$PG_PRESET" \
      --config-template-disk-type network-ssd --config-template-disk-size-gibibytes "$PG_DISK_GIB" \
      --config-template-hosts-count 1 --bootstrap-db-name "$PG_DB" --bootstrap-user-name "$PG_USER" \
      --bootstrap-user-password "$PG_PASSWORD" --backup-backup-window-start "02:00:00" --backup-retention-policy 7d
    echo "   created; wait for status Running, then read the private host with:"
    echo "   nebius msp postgresql v1alpha1 cluster get-by-name --name $NAME-db --parent-id $PROJECT_ID"
    echo "   and store DATABASE_URL=postgresql+psycopg://$PG_USER:<password>@<host>:5432/$PG_DB in the secret (step 3)."
  else
    echo "   [plan] would create cluster $NAME-db (pg16, cpu-e2/$PG_PRESET, ${PG_DISK_GIB} GiB network-ssd, 1 host, private, 7-day backups)"
  fi
else
  echo "   exists: $PG_ID"
fi

# ---------------------------------------------------------------- 3. runtime secrets (MysteryBox)
say "3. MysteryBox secret '$SECRET_NAME' (keys only shown)"
need_keys=(TOKENFACTORY_2009_API_KEY JWT_SECRET DATABASE_URL)
optional_keys=(TAVILY_API_KEY)  # further reading; skipped when absent
echo "   payload keys: ${need_keys[*]}  (values read from $ROOT/.env or the environment; never printed)"
if [[ "$MODE" == "apply" ]]; then
  PAYLOAD="$(python3 - "$ROOT/.env" "${need_keys[@]}" -- "${optional_keys[@]}" <<'PY'
import json, os, sys
from pathlib import Path
env = {}
p = Path(sys.argv[1])
if p.exists():
    for line in p.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip().upper()] = v.strip()
args = sys.argv[2:]
cut = args.index("--") if "--" in args else len(args)
required, optional = args[:cut], args[cut + 1:]
aliases = {"TAVILY_API_KEY": ["TAVILY_2009_API_KEY"]}
out = []
for k in required + optional:
    v = os.environ.get(k) or env.get(k, "") or next((env[a] for a in aliases.get(k, []) if env.get(a)), "")
    if not v and k in required:
        sys.exit(f"missing value for {k}")
    if v:
        out.append({"key": k, "string_value": v})
print(json.dumps(out))
PY
)"
  HAS_TAVILY="$(printf '%s' "$PAYLOAD" | python3 -c 'import json,sys; print(any(x["key"]=="TAVILY_API_KEY" for x in json.load(sys.stdin)))')"
  nebius mysterybox secret create --name "$SECRET_NAME" --parent-id "$PROJECT_ID" \
    --secret-version-payload "$PAYLOAD" --secret-version-set-primary >/dev/null
  unset PAYLOAD
  echo "   secret stored"
else
  echo "   [plan] would create MysteryBox secret $SECRET_NAME"
fi

# ---------------------------------------------------------------- 4. serverless endpoint
say "4. Serverless endpoint '$NAME'"
EP_ARGS=(--name "$NAME" --parent-id "$PROJECT_ID" --image "$IMAGE" --platform "$PLATFORM" --preset "$PRESET"
         --disk-size "$DISK" --container-port 8000/http --on-demand
         --env APP_MODE=live --env AI_PROVIDER=nebius_tokenfactory --env APP_ENVIRONMENT=nebius
         --env NEMO_GUARDRAILS_ENABLED=true --env LLM_MAX_CONCURRENT_REQUESTS=4 --env RATE_CHAT_PER_MIN=20
         --env DAILY_INFERENCE_TOKEN_LIMIT=2000000
         --env-secret "TOKENFACTORY_2009_API_KEY=$SECRET_NAME" --env-secret "JWT_SECRET=$SECRET_NAME"
         --env-secret "DATABASE_URL=$SECRET_NAME")
if [[ "${HAS_TAVILY:-False}" == "True" || "$MODE" == "plan" ]]; then
  EP_ARGS+=(--env-secret "TAVILY_API_KEY=$SECRET_NAME")   # optional further-reading key
fi
if [[ "$MODE" == "plan" ]]; then
  echo "   validating the request with --dry-run (creates nothing):"
  if [[ -n "$REGISTRY_ID" ]]; then
    nebius ai endpoint create "${EP_ARGS[@]}" --dry-run || echo "   dry-run reported a problem (see above)"
  else
    echo "   [plan] dry-run skipped: the registry (step 1) does not exist yet, so the image reference is not final"
  fi
else
  nebius ai endpoint create "${EP_ARGS[@]}"
  echo "   public URL: nebius ai endpoint get-by-name --name $NAME --format json   # see status.public_endpoints"
  echo "   then set APP_PUBLIC_URL / CORS_ORIGINS if the frontend is served elsewhere, and run deploy/nebius/smoke.sh <url>"
fi

say "Done ($MODE). Rollback: nebius ai endpoint delete --id <id>; previous image tags stay in the registry."
