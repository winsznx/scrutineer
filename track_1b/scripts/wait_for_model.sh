#!/usr/bin/env bash
# Poll a Public AI model until it answers, then log the probe's billed cost to the ledger.
# Usage: scripts/wait_for_model.sh swiss-ai/apertus-v1.5-70b [interval_seconds]
set -euo pipefail

model="$1"
interval="${2:-180}"
root="$(cd "$(dirname "$0")/.." && pwd)"
key="${LLM_API_KEY:-${PUBLIC_AI_API_KEY:?set LLM_API_KEY}}"
headers="$(mktemp)"
trap 'rm -f "$headers"' EXIT

while true; do
  code=$(curl -sS -m 150 -o /dev/null -D "$headers" -w "%{http_code}" \
    https://api.publicai.co/v1/chat/completions \
    -H "Authorization: Bearer $key" -H "User-Agent: scrutineer/1.0" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$model\",\"messages\":[{\"role\":\"user\",\"content\":\"Say OK.\"}],\"max_tokens\":3,\"temperature\":0}" \
    || echo 000)
  echo "$(date -u +%FT%TZ) $model HTTP $code"
  if [ "$code" = "200" ]; then
    cost=$(grep -i '^x-litellm-response-cost:' "$headers" | tr -d '\r' | awk '{print $2}')
    rid=$(grep -i '^inference-id:' "$headers" | tr -d '\r' | awk '{print $2}')
    printf '{"cost_usd": %s, "item_id": "availability-probe", "kind": "spend", "request_id": "%s", "run_id": "probe", "timestamp": "%s"}\n' \
      "${cost:-0}" "$rid" "$(date -u +%FT%T.000+00:00)" >> "$root/data/spend_ledger.jsonl"
    exit 0
  fi
  sleep "$interval"
done
