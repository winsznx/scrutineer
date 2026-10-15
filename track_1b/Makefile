.PHONY: run build test lint report site judge-server clean-docker

# `make run` is what judges execute: Docker, clean checkout, no API key needed.
# It rebuilds the items, replays grading from stored responses, checks the result
# hash, regenerates figures and the site, and exits non-zero on any mismatch.
run:
	docker compose build --quiet
	docker compose run --rm scrutineer

# Local equivalents (need `uv` or a Python 3.12 venv with `pip install -e ".[dev]"`).
build:
	scrutineer build --check

test:
	pytest

lint:
	ruff check src tests
	mypy

report:
	scrutineer grade
	scrutineer report

site:
	scrutineer site

# Starts the local judge (llama.cpp + Qwen2.5-7B-Instruct Q8_0); see docs/JUDGE.md.
judge-server:
	scripts/judge_server.sh

clean-docker:
	docker compose down --rmi local
