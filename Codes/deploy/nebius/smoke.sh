#!/usr/bin/env bash
# Post-deployment smoke test against a deployed URL (read-only except one demo chat turn).
#   deploy/nebius/smoke.sh https://<endpoint-host>  [username] [password]
set -euo pipefail
URL="${1:?usage: $0 <base-url> [user] [password]}"; USER_="${2:-TestUser}"; PASS="${3:-TestUser11}"
c() { curl -fsS --max-time 60 "$@"; }
# JSON helper (python3 instead of jq): `... | pyq 'expr' [args]` evaluates expr with d = parsed stdin, a = args.
pyq() { python3 -c 'import json,sys; d=json.load(sys.stdin); a=sys.argv[2:]; r=eval(sys.argv[1]); print(r if isinstance(r,str) else json.dumps(r, ensure_ascii=False))' "$@"; }

echo "health:";        c "$URL/api/health" | pyq 'd'
echo "capabilities:";  c "$URL/api/capabilities" | pyq "{k: d[k] for k in ('mode','inference','locales')}"
echo "spa shell:";     c "$URL/" | grep -o '<title>[^<]*</title>'
TOKEN="$(c -H 'Content-Type: application/json' -d "{\"username\":\"$USER_\",\"password\":\"$PASS\"}" "$URL/api/auth/login" | pyq "d['access_token']")"
PID="$(c -H "Authorization: Bearer $TOKEN" "$URL/api/patients" | pyq "d[0]['id']")"
echo "chat (es-ES):"
c -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"patient_id\":\"$PID\",\"text\":\"¿Qué pasa si ceno arroz con lentejas?\",\"lang\":\"es-ES\"}" \
  "$URL/api/agent/chat" | pyq "{k: d.get(k) for k in ('source','source_detail','intent','checks','clarification','disclosures')}"
echo "ready:";         c "$URL/api/ready" | pyq 'd'
