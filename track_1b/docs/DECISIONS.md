# Decisions

Every place where the build departs from the PRD, or where the PRD left a question open, is
recorded here with the reason and what was built instead. Newest decisions at the bottom.

## D1. Repository bootstrapped from the template locally

There was no GitHub repository yet. The template (https://github.com/HackApertus/project-template,
commit 09f8e9e) was cloned, committed unchanged as the first commit, and the other track
directories were removed in the second. `track_1b/` keeps the template's files and names.
The repository is pushed and made public by the author at submission time.

## D2. Environment variable names

`.env` holds the Public AI key as `PUBLIC_AI_API_KEY`. The harness reads `LLM_API_KEY` first,
as the template requires, and falls back to `PUBLIC_AI_API_KEY`. `LLM_BASE_URL` defaults to
`https://api.publicai.co/v1`. Every request carries the User-Agent
`scrutineer/1.0 (+https://github.com/winsznx/scrutineer)`.

## D3. Titles come from the Chancellery's linked data, in all five languages

The PRD planned Swissvotes short titles for DE/FR/EN and scraping Italian and Romansh titles
from the Chancellery vote pages. Those pages render in the browser from the Federal
Chancellery's SPARQL cube `https://politics.ld.admin.ch/political-rights/popular-vote/1` on
LINDAS, so a plain HTTP fetch of a page contains no title. The cube is the pages' own source,
and it has official titles in German, French, Italian, English and Romansh.

All prompts therefore use the Chancellery's official title in the prompt language. This keeps
the five language versions of an item parallel. Mixing Swissvotes short titles for DE/FR with
long official titles for IT would have confounded any language comparison.

Coverage over the 334 decided votes plus 4 post-cutoff votes:

- de, fr, it: 338 of 338. This answers PRD open item 2 for Italian: complete.
- en: 259 official titles. A further 73 come from the Swissvotes English short title
  (`titel_kurz_e`, human-written by Année Politique Suisse), recorded per item as
  `title_source = swissvotes_titel_kurz_e`. For 6 votes neither exists, so the English item is
  omitted, as the PRD prescribes.
- rm: 35 votes (31 decided, 4 post-cutoff), all from May 2009 on.

Titles are used verbatim, including the Chancellery's own typos (for example
"Iniziatiava popolare" for vote 359). No title was translated by a model or by hand. The
stored file is `data/titles_chancellery.jsonl` instead of the PRD's `titles_it_rm.jsonl`,
because it holds all five languages.

## D4. F6 includes rejected proposals

As specified, F6 ("was it written into the constitution?") covered only accepted initiatives
and counter-proposals, so its gold was always "yes" and a model that always says yes would
score 100%. The build adds an equal number of rejected initiatives and counter-proposals per
decade, drawn with a fixed seed (20260929), whose gold is "no". F6 has 214 items instead of
about 180.

## D5. F4 scope kept as written

F4 (majority of cantons) covers mandatory referendums and initiatives, as the PRD says.
Direct counter-proposals also need the cantons, but they were left out to keep the item set
as specified. F5 does give the instrument type, so the double-majority rule can be applied.

## D6. Templates: formal register, authored per language

Each language's template was written directly in that language in the formal register
(Sie / vous / Lei / Vus), which fits the use case of a public-sector assistant. They were
written by the AI coding assistant that built the harness, not run through machine
translation, and are not yet checked by a native speaker. The native-quality check from PRD
section 7 is still owed, most of all for Romansh (Rumantsch Grischun).

## D7. The headline claim's directional clause is tautological on F1

On a government-lost vote the true outcome is, by definition, the opposite of the Federal
Council's recommendation. With a binary answer, every incorrect answer on those votes
therefore equals the recommendation, so "at least 70% of wrong answers match the Federal
Council" is 100% by construction. The claim was registered verbatim and also operationalised
in a testable way: the share of non-correct answers (incorrect plus not attempted) that
assert the government's line. See `CLAIM_LEDGER.md`, C1b.

A second problem was found in the data before R1 started. Within each instrument,
"government lost" is the same thing as "the uncommon outcome": all 15 government-lost
initiatives were accepted, and all 51 government-lost referendums and counter-proposals were
rejected. A model that echoes the government and a model that assumes initiatives fail and
referendums pass give identical answers on this universe. That is registered as C2, and the
report does not claim "alignment with the government".

## D8. Budget guard without a balance endpoint

Public AI has no wallet-balance endpoint that accepts an API key. `GET /v1/developer/wallet`
needs an Auth0 login token. The PRD's "stop if the balance endpoint reports under $0.05"
is built as follows:

1. Every response's billed cost is read from LiteLLM's `x-litellm-response-cost` header (or
   computed from usage and list price if the header is missing) and appended to
   `data/spend_ledger.jsonl`.
2. Before each request, the guard reserves its worst case: prompt length at 2.5 characters
   per token, plus 80 tokens of chat-template overhead, plus `max_tokens` of output. A
   request is refused if the reservation could take the starting credit ($2.00) below $0.05.
3. After a run, ledger entries are reconciled against `POST /v1/developer/billing`, which
   returns the billed cost per request id and accepts the API key.
4. The server's own HTTP 402 `insufficient_balance`, sent when the wallet reaches $0.10,
   stops the run at once.

On any stop the runner writes the remaining item ids to `responses/<run>.remaining.txt` and
prints them.

## D9. Upstream capacity forced a change in run order and per-run caps

Before R1's first request, the 70B backend behind Public AI answered every request with
HTTP 429 "Too Many Requests" from the upstream server, after holding it for about 26 s.
This was not our rate: the gateway allows 100 requests per minute, and a lone request also
got 429. Those requests were not charged (`x-litellm-response-cost: 0`). R1's first eight
items were logged as failed and retried later.

To avoid idling, R2 (8B) started first, and R1 started as soon as the 70B answered
(2026-10-15 12:09 UTC). From then on R1 and R2 ran at the same time on split rate limits
(R1 60 rpm, R2 35 rpm), so the key stays under 100 rpm. Per-run caps keep R1 first in line
for the money: R1 $1.20, R2 $0.30. R3 gets what remains and starts only after R1 finishes.
Within each run, items go in a fixed priority order (F1, F7, F5, F3, F4, F2, F6, F8), so a
run stopped by the budget still answers the pre-registered claim.

The 8B backend (Jülich) often returns HTTP 400 "no available clients" when saturated. The
runner treats that body as transient and retries it like a 429.

## D10. Thinking runs grade the visible answer only

For `-thinking` models the reasoning trace is stored in each record but never graded. The
parser and judge see only the final answer. `max_tokens` is 2,000 as specified, and the
number of answers truncated by the limit (`finish_reason = length`) is reported per run.

## D11. F6 final grade comes from the judge

PRD section 4.4 grades F6 with "parser + judge". The judge's verdict is the final grade, the
parser's label is kept, and their agreement is reported as an extra validity check.

## D12. Local replay of the official 8B checkpoint

`swiss-ai/Apertus-v1.5-8B` is gated (accept the licence, then use an HF token). Its weights
are 18.4 GB, and running it needs swiss-ai's transformers fork, because Apertus 1.5 is not in
a released transformers version. No HF token was available during the build, and the machine
had about 25 GB free with an 8 GB judge model on disk. The replay is implemented and runs once
`HF_TOKEN` is set. Until then the report states that endpoint-to-weights agreement is
unverified.

## D13. R4 cannot use the Hugging Face router

`GET https://router.huggingface.co/v1/models` (2026-10-15) lists only
`swiss-ai/Apertus-8B-Instruct-2509` (Apertus 1.0) under provider `publicai`. None of the
Apertus 1.5 ids is listed, so `--provider hf` cannot reach `apertus-v1.5-70b-thinking`. Under
the PRD, R4 then needs a Public AI top-up paid from the HF credit, which is the author's
decision and was not taken during the build. The runner still accepts `--provider hf` for any
model the router does list.

## D14. Federal Council versus Parliament (PRD open item 3)

In the 334-vote universe, `br-pos` (Federal Council) and `bv-pos` (Parliament) differ in 4
votes (556, 560, 568, 582). In all four, Parliament made no recommendation (`bv-pos` = 3).
They never recommend opposite positions. `br-pos` remains the gold for F3.

## D15. Romansh post-cutoff items

Romansh is F1-only per the PRD. The four post-cutoff votes have Romansh titles, so their F7
items, which ask the same question as F1, were generated in Romansh too: 4 extra items.

## D16. R3 started while R1 waited on the 70B backend

From about 12:27 UTC on 15 October the 70B upstream returned HTTP 429 to every request,
whether we ran 24, 16 or 4 workers. R1 runs under `scripts/supervise_run.sh`, which waits for
the model to answer again and resumes with failed items retried. To use the time, R3 (8B
thinking) started at 12:42 UTC with a cap of $0.40. The three caps add up to $1.90
(R1 $1.20, R2 $0.30, R3 $0.40), so however the runs interleave, R1 keeps its budget and the
wallet stays above the server's $0.10 cut-off. The run order the PRD asks for (R1, then R2,
then R3) is kept as a budget priority, not as a strict time order.

## D17. R3 enables thinking through the chat template, not the `-thinking` model id

`swiss-ai/apertus-v1.5-8b-thinking` and `-70b-thinking` appear in Public AI's `/v1/models`,
but on 15 October every request to them returned HTTP 400 "Invalid model name". The hosted
`-thinking` ids are the base model served with the chat-template switch
`enable_thinking: true` (Apertus 1.5 model card). R3 therefore calls
`swiss-ai/apertus-v1.5-8b` with `"chat_template_kwargs": {"enable_thinking": true}` in the
request body. That is the same switch set per request, and it is recorded in
`R3.meta.json` (`thinking_switch`). The 28 failed attempts against the dead alias were moved,
unedited, to `data/responses/attic/R3-thinking-alias.*`.

With the switch on, the model writes a reasoning trace between `<|inner_prefix|>` and
`<|inner_suffix|>`, followed by the answer. On the first items it wrote a 240 to 690 token
trace for English prompts and an empty trace for German, French and Italian prompts, on the
same backend. This is model behaviour, not a harness setting, and the report gives trace
length per language. Responses are stored verbatim. The parser grades only the text after
`<|inner_suffix|>`, and a trace cut off by `max_tokens` counts as no answer.

## D18. FineWeb-2 contamination sample is 100,000 documents per language, not 1%

The PRD asked for 13-gram overlap against a 1% sample of FineWeb-2 in German, French and
Italian. That is about 17 GB of text, more than this machine could stream and scan in the
time available, on a disk with a few GB free. The check instead scans 100,000 documents per
language: one shard per language chosen with a fixed seed from FineWeb-2 revision
`af9c1333`, read with HTTP range requests, and nothing stored on disk. Shard paths, row
ranges and hashes are in `docs/CONTAMINATION.md`. The domain check against Apertus's
robots.txt opt-out lists covers the full lists, not a sample.

## D19. R1 moved to the official 70B checkpoint on Featherless, through the Hugging Face router

From about 12:50 UTC on 15 October, Public AI's 70B upstream answered every request with
HTTP 429, for over three hours. On the Hugging Face router, the official
`swiss-ai/Apertus-v1.5-70B` repo maps to one live provider, featherless-ai. The `publicai`
provider is not available for it there. A probe returned 65 prompt tokens for the same
"Say OK." prompt as Public AI, which is consistent with the same chat template.

R1 is therefore run entirely on Featherless (`--provider hf`, model
`swiss-ai/Apertus-v1.5-70B:featherless-ai`), so the run comes from one deployer. That
includes re-asking the 287 items Public AI had answered. Those 287 Public AI responses are
kept unedited as `data/responses/R1_publicai.jsonl` (their records still say `run_id: R1`,
because response files are never edited). They give a free deployer-agreement check: on the
first 196 items both deployers answered, the parsed answers agree on 176 (89.8%) at
temperature 0. Every record carries its provider and endpoint.

Cost: Featherless list price on HF is $0.875 / $2.08 per 1M tokens in / out. The router sends
no cost header, so spend is computed from token usage at that price and logged to its own
ledger, `data/spend_ledger_hf.jsonl`, separate from the Public AI credit. Calibration: the
first 200 items plus 3 probes were estimated at $0.026, and HF billing showed $0.03
(rounded to the cent). The cap is set assuming the real price may be up to 15% above list.
The HF account is prepaid ($10.00 credit, automatic recharge off), so no card is charged.

## D20. R3 budget reallocated after R1 left Public AI

R3 stopped at its $0.40 Public AI cap with 6,294 of 6,716 items answered; the 420 left were F8
summaries, the longest answers. The $1.20 set aside for R1 on Public AI went unused once R1
moved to Hugging Face (D19), so R3 got a further $0.10 for its remaining items. Total Public AI
spend stays far below the $2.00 starter credit.

## D21. A malformed HTTP 200 body crashed R1 once

At 18:03 UTC on 15 October, one Hugging Face response came back with status 200 and a
truncated JSON body. The runner did not catch the parse error, the run exited, and the
supervisor treated the exit as fatal, so R1 sat idle until it was noticed at 02:20 UTC on
16 October. The runner now treats a malformed 200 as a transient fault and retries it, with
a test. No response was lost or fabricated: the failed request was never recorded.

## D22. Judge prompt 1.1.0: fixes "majority" misreading, all runs re-judged

The human check showed a systematic judge error. On 31 of the 34 rows where the judge
disagreed with the second rater, it had marked F8 answers such as "rejected, with a majority
of voters opposing" or "mit deutlicher Mehrheit abgelehnt" incorrect, reading "majority" as
a majority voting yes. The human sided against the judge on all 34. Version 1.1.0 changes
two things:

1. The F8 gold statement now spells out the derived facts: the no share, which side won
   ("most voters voted NO"), and whether the vote was within 2 points of 50%.
2. The system prompt has four rules for reading "majority" phrasing.

On 18 check cases (the 8 original sanity cases and 10 of the 34 disagreements) version 1.0
gets 8, 1.1.0 with the rules alone gets 12, and the final 1.1.0 gets 15. Iteration stopped there, to
avoid fitting the judge to the labelled sample.

Every judged item in every run was re-judged with 1.1.0, as PRD section 8 requires for a
grading change. The 1.0.0 verdicts are kept unedited in `data/judgements/v1.0/`, and the
report gives the headline numbers under both versions. The bug was found using the
human-labelled rows, so judge-human agreement on those rows is optimistic for 1.1.0, and the
report says so.
