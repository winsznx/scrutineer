#!/usr/bin/env bash
# Judge new responses as runs stream in. One instance only: judgement files are append-only.
set -uo pipefail
cd "$(dirname "$0")/.."
while true; do
  .venv/bin/scrutineer judge --concurrency 2 || echo "$(date -u +%FT%TZ) judge pass failed with $?"
  sleep "${JUDGE_INTERVAL:-300}"
done
