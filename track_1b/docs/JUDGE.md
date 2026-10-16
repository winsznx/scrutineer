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
| Serving | `llama-server`, 4 parallel slots, 16,384-token context shared across slots (judge 1.0.0 verdicts used 2 slots) |
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

Human review of a Claude pre-labelled sample. The human saw the pre-label and could
override. Judge vs human and judge vs Claude are both reported. Claude never saw the
judge's verdicts.

The sample is a seeded random 20% of R2's judged items (311 of 1,556), exported blind by
`scrutineer export-human-check --run-id R2`. Claude (Fable 5.1) labelled every row from the
same columns the human sees (question, gold facts, response), with no judge verdict, run or
language. `scrutineer merge-prelabels` adds those labels to `human_check.csv` and writes
`human_check_review.csv` for the human pass. Because the human saw Claude's label, judge vs
human is not independent of Claude, and the report says so next to the number.

How the human labels were produced: the labeller (Tim) received the sample with Claude's
pre-labels and submitted grades for all 311 rows as one batch on 2026-10-16 at 02:15 UTC,
which is the `labelled_at` value on every row. Per-row label times were not captured. The
human grades equal Claude's pre-labels on 309 of 311 rows. On a second pass the labeller
overrode two (`72ecd4ed12`, `07da9f6900`): both answers claim a "clear majority" for votes
decided at 50.08% and 49.77% yes. Read judge vs human as judge vs Claude with a light human
review on top, not as an independent second annotation.

<!-- scrutineer:begin judge_table -->
| Run | Judged items | By reason | F6 parser vs judge agreement |
|---|--:|---|--:|
| R1 | 0 |  | n/a (n=0) |
| R2 | 5 | unparseable 5 | n/a (n=0) |
| R3 | 8 | unparseable 8 | n/a (n=0) |
<!-- scrutineer:end judge_table -->

<!-- scrutineer:begin human_table -->
_Human check status: not exported._
<!-- scrutineer:end human_table -->
