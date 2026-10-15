# Judge

## Role

Most items are graded by the deterministic parser in `src/scrutineer/grade/parse.py`. An
LLM judge decides three kinds of item:

1. every F8 free-recall answer (one-sentence summary of a vote),
2. every F6 answer ("was it written into the constitution?"); the parser's label is kept
   alongside and agreement is reported,
3. any F1 to F5 or F7 answer the parser marks `unparseable`.

The judge returns one of `correct`, `incorrect`, `not_attempted` plus a one-line reason,
following the SimpleQA grading rules. A hedged but wrong answer is incorrect, and an answer
that commits to nothing and contradicts nothing is not attempted.

## Model

The judge is **Qwen2.5-7B-Instruct**, an open-weights model from a different developer than
Apertus. It is never Apertus. It runs locally on llama.cpp, with no paid API.

| | |
|---|---|
| Weights | `Qwen/Qwen2.5-7B-Instruct-GGUF`, `Q8_0`, three shards |
| Revision and sha256 | recorded in `docs/judge_meta.json` by `scripts/judge_server.sh` |
| Runtime | llama.cpp `llama-server` (version in `docs/judge_meta.json`), Metal on an M1 Pro |
| Sampling | temperature 0, seed 0, `max_tokens` 120 |
| Output | constrained by a JSON schema: `{"grade": correct\|incorrect\|not_attempted, "reason": ...}` |

Q8_0 was chosen as the closest quantisation to the full-precision weights that fits on the
build machine next to the other artefacts.

## Prompt

The system and user prompts are in `src/scrutineer/grade/judge.py` (`JUDGE_SYSTEM`,
`JUDGE_USER`), version `JUDGE_PROMPT_VERSION`. Every judgement record stores the prompt
version, the prompt's sha256 and the sha256 of the exact request body.

The judge sees:

- the question exactly as the model saw it (in the item's language),
- a gold statement in English, generated from the item's gold fields by `describe_gold`.
  For F8 that statement gives the outcome, the Federal Council's recommendation and the yes
  share,
- the model's visible answer. Thinking traces are removed first.

The judge never sees the model name, run id or provider. For F8, a stated yes share more than
2 points from the gold counts as a contradiction. That is looser than F2's ±1.0 point because
a one-sentence summary usually rounds.

## Running it

```bash
make judge-server            # downloads the GGUF once, writes docs/judge_meta.json, serves on :8080
scrutineer judge             # judges every run's pending items, resumable
scrutineer grade             # folds judgements into data/results.json
```

`make run` does not call the judge. It replays grading from the stored judgements in
`data/judgements/`, so a reviewer needs neither the model nor a key.

## Agreement

Human agreement comes from a blind 20% sample (PRD section 6.3); see `human_check.csv` and
the report.

<!-- scrutineer:begin judge_table -->
<!-- scrutineer:end judge_table -->

<!-- scrutineer:begin human_table -->
<!-- scrutineer:end human_table -->
