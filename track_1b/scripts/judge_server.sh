#!/usr/bin/env bash
# Start the local judge: Qwen2.5-7B-Instruct (official Qwen GGUF, Q8_0) on llama.cpp.
# Downloads the three shards on first use, records their sha256 in docs/judge_meta.json,
# and serves an OpenAI-compatible API on 127.0.0.1:${JUDGE_PORT:-8080}.
# Requires: llama.cpp (`brew install llama.cpp` or a build exposing `llama-server`).
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
dir="$root/models/qwen2.5-7b-instruct"
repo="Qwen/Qwen2.5-7B-Instruct-GGUF"
revision="${JUDGE_REVISION:-bb5d59e06d9551d752d08b292a50eb208b07ab1f}"
shards=(qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf
        qwen2.5-7b-instruct-q8_0-00002-of-00003.gguf
        qwen2.5-7b-instruct-q8_0-00003-of-00003.gguf)

mkdir -p "$dir"
for shard in "${shards[@]}"; do
  if [ ! -f "$dir/$shard.done" ]; then
    curl -sSL --retry 5 -C - -o "$dir/$shard" "https://huggingface.co/$repo/resolve/$revision/$shard"
    touch "$dir/$shard.done"
  fi
done

if [ ! -f "$root/docs/judge_meta.json" ]; then
  commit=$(curl -sS "https://huggingface.co/api/models/$repo/revision/$revision" | python3 -c 'import json,sys; print(json.load(sys.stdin)["sha"])')
  python3 - "$dir" "$commit" "$root/docs/judge_meta.json" "${shards[@]}" <<'PY'
import hashlib, json, subprocess, sys
from pathlib import Path
directory, commit, out, *shards = sys.argv[1:]
hashes = {}
combined = hashlib.sha256()
for name in shards:
    digest = hashlib.sha256()
    with open(Path(directory) / name, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    hashes[name] = digest.hexdigest()
    combined.update(hashes[name].encode())
version = subprocess.run(["llama-server", "--version"], capture_output=True, text=True)
meta = {
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "gguf_repo": "Qwen/Qwen2.5-7B-Instruct-GGUF",
    "gguf_revision": commit,
    "quantisation": "Q8_0",
    "shards_sha256": hashes,
    "gguf_sha256": combined.hexdigest(),
    "runtime": (version.stdout + version.stderr).strip().splitlines()[0],
    "sampling": {"temperature": 0, "seed": 0, "max_tokens": 120},
    "context": 4096,
}
Path(out).write_text(json.dumps(meta, indent=2) + "\n")
print(f"wrote {out}")
PY
fi

exec llama-server -m "$dir/${shards[0]}" --host 127.0.0.1 --port "${JUDGE_PORT:-8080}" \
  --ctx-size 8192 --parallel 2 --n-gpu-layers 99 --seed 0 --alias judge
