#!/usr/bin/env bash
# Keep a run going through upstream outages: when `scrutineer run` stops because the
# endpoint is down (exit 5) or items failed (exit 3), wait for the model to answer and
# resume with failed items retried. Stops for good on completion, budget stop or signal.
# Usage: scripts/supervise_run.sh <run-id> <model> [extra scrutineer run args...]
set -uo pipefail

run_id="$1"; model="$2"; shift 2
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
max_rounds="${MAX_ROUNDS:-40}"

for round in $(seq 1 "$max_rounds"); do
  echo "$(date -u +%FT%TZ) supervise $run_id round $round"
  .venv/bin/scrutineer run --run-id "$run_id" --model "$model" --retry-failed "$@"
  code=$?
  case "$code" in
    0) echo "$(date -u +%FT%TZ) $run_id complete"; exit 0 ;;
    4) echo "$(date -u +%FT%TZ) $run_id stopped by the budget guard"; exit 4 ;;
    6) echo "$(date -u +%FT%TZ) $run_id stopped at its time limit"; exit 6 ;;
    130) echo "$(date -u +%FT%TZ) $run_id stopped by signal"; exit 130 ;;
    3|5)
      if [[ " $* " == *" --provider hf "* ]]; then sleep 120   # HF route: back off, no Public AI probe
      else scripts/wait_for_model.sh "$model" 120; fi ;;
    *) echo "$(date -u +%FT%TZ) $run_id exited with $code"; exit "$code" ;;
  esac
done
echo "$(date -u +%FT%TZ) gave up after $max_rounds rounds"
exit 1
