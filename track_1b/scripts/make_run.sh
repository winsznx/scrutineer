#!/usr/bin/env bash
# What `make run` executes inside the container. Exits non-zero if any check fails.
set -euo pipefail

step() { printf '\n== %s\n' "$1"; }

step "1/5 rebuild items from the pinned CSV and titles, compare with data/items.jsonl"
scrutineer build --check

step "2/5 replay grading from stored responses and judgements, verify results.sha256"
scrutineer verify

step "3/5 regenerate figures and the numbers quoted in README, report and data card"
scrutineer report --check

step "4/5 rebuild the static site"
scrutineer site

if [ -n "${LLM_API_KEY:-}" ] && [ "${SCRUTINEER_LIVE:-0}" = "1" ]; then
  step "5/5 live smoke: 50 items against ${LLM_BASE_URL:-Public AI} / ${LLM_NAME:?set LLM_NAME}"
  scrutineer run --provider "$([ -n "${LLM_BASE_URL:-}" ] && echo env || echo publicai)" --run-id "smoke-$(date -u +%Y%m%dT%H%M%SZ)" --model "$LLM_NAME" \
    --limit 50 --max-usd 0.05
else
  step "5/5 live smoke skipped (set LLM_API_KEY and SCRUTINEER_LIVE=1 to run 50 items against a model)"
fi

printf '\nAll checks passed.\n'
