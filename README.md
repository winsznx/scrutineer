# Scrutineer

**Ask Apertus what the Swiss people decided, and in French or English it will usually tell you
"rejected", whatever actually happened.**

Scrutineer is a benchmark of every Swiss federal popular vote since 1990, asked of Apertus 1.5
in German, French, Italian, English and Romansh, graded against the official record.

**Live site and vote explorer**: <https://winsznx.github.io/scrutineer/> ·
**Report (PDF)**: [`track_1b/Scrutineer_Report.pdf`](track_1b/Scrutineer_Report.pdf) ·
**Dataset**: <https://huggingface.co/datasets/winsznx/scrutineer> ·
**Claim ledger**: [`track_1b/docs/CLAIM_LEDGER.md`](track_1b/docs/CLAIM_LEDGER.md) ·
**Decisions log**: [`track_1b/docs/DECISIONS.md`](track_1b/docs/DECISIONS.md)

Hack Apertus 2026 · Track 1B Swiss Voices · core task intelligence. The project root is
[`track_1b/`](track_1b/).

---

## Who has this problem

**A Swiss public body putting an assistant in front of residents.** A canton answering questions
about administration, a city chatbot, a library or school helping people understand what is on
the ballot. Apertus is the obvious model for that job: it was built in Switzerland, for
Switzerland, in the national languages.

The first question such an assistant gets about democracy is simple: *what did we vote on, and
what happened?* The outcome of a federal vote is binding, public, and checkable against an
official record. It is the least a civic assistant must get right.

## The bottleneck today

Nobody had measured it. There was no public benchmark of whether a model knows Swiss vote
outcomes, in any language.

The question came from one observation. On 13 October 2026, Apertus 1.5 70B was asked about the
13th AHV old-age pension, accepted by the people on 3 March 2024 with 58.25% yes. It said the
proposal was rejected. Scrutineer asked the same question on the official 70B weights, in every
national language:

| Language | Apertus 1.5 70B answer | Truth |
|---|---|---|
| Deutsch | `abgelehnt` | accepted |
| Français | `rejeté` | accepted |
| Italiano | `respinto` | accepted |
| English | `rejected` | accepted |
| Rumantsch | `refusà` | accepted |

One vote is an anecdote. Scrutineer asks about all of them.

## What Scrutineer does

It turns every decided federal vote since 1990 into a set of questions, sends them to the model
exactly as written, and grades every answer against the record.

<!-- scrutineer:begin dataset_stats -->
6,716 items over 334 decided federal votes (1 Jan 1990 to 27 Sep 2026, 66 of them lost by the Federal Council) plus the 4 votes of 29 Nov 2026.

By family: F1 1,361 · F2 1,330 · F3 1,330 · F4 797 · F5 334 · F6 214 · F7 20 · F8 1,330.

By language: German 1,928 · English 1,565 · French 1,594 · Italian 1,594 · Romansh 35.

`items.jsonl` sha256 `fe3ee9af2f440fa3…` (full hash in `data/items.manifest.json`).
<!-- scrutineer:end dataset_stats -->

Eight question families look at the same vote from different sides, so a failure can be located,
not just counted:

| | Asks | Gold |
|---|---|---|
| F1 | Was the proposal accepted or rejected? | Swissvotes `annahme` |
| F2 | What share of voters said yes? (±1 point) | `volkja-proz` |
| F3 | What did the Federal Council recommend? | `br-pos` |
| F4 | Did a majority of cantons accept it? | `kt-ja` > `kt-nein` |
| F5 | Given the yes share and cantonal votes, title hidden: accepted? | `annahme` |
| F6 | Was it written into the Federal Constitution? | `annahme` |
| F7 | Outcome of a vote that has not been held yet | not decided |
| F8 | Summarise the vote in one sentence | outcome, recommendation, yes share |

F5 is the control. It gives the model the numbers and hides the title, so it separates "cannot
reason about Swiss voting rules" from "does not remember this vote". F7 asks about four votes of
29 November 2026, where the only correct answer is that nobody knows yet.

Every gold value comes from the Swissvotes dataset (Année Politique Suisse, Universität Bern),
pinned by sha256, and every item stores the hash of the source row it came from. Every vote
title is the Federal Chancellery's own official wording, fetched from its linked-data service in
all five languages. **No model wrote or translated anything in the dataset.**

---

## The measured result

<!-- scrutineer:begin headline -->
On F1 (did the vote pass?) in German, French, Italian and English, Apertus 1.5 70B is right on **64.7%** of votes the Federal Council won and **55.9%** of votes it lost, a gap of **8.8 points** (z = 2.64, p = 0.0083; n = 1069 and 261 answers). Pre-registered claim C1: **FAILED**.
<!-- scrutineer:end headline -->

The claim was written down before the first model request:

<!-- scrutineer:begin claim_status -->
- C1: **FAILED**. Gap 8.8 points (falsifier: under 10), p = 0.0083, R1 on Featherless (D19).
- C1b: directional share 96.5%, above the 70% threshold; reported as part of C1, which fails on the gap.
- C2: within initiatives the gap is 73.2 points; within referendums and counter-proposals it is -27.0 points. The errors follow a default "rejected" answer, not the Federal Council.
- C3: **SUPPORTED**. F5 95.5% against F1 (de) 30.3% on government-lost votes.
<!-- scrutineer:end claim_status -->

### 1. The claim failed. The model is not repeating the government.

The hypothesis was that Apertus misremembers votes the government lost because it repeats the
government's recommendation. Split the votes by type and the data says otherwise:

<!-- scrutineer:begin within_instrument -->
| Model | Instruments | Gov. won | Gov. lost | Gap (pts) | p |
|---|---|--:|--:|--:|--:|
| 70B (Featherless) | initiative | 90.5% (n=524) | 17.2% (n=58) | 73.2 | 0.0000 |
| 70B (Featherless) | referendum or counterproposal | 40.0% (n=545) | 67.0% (n=203) | -27.0 | 0.0000 |
| Public AI "8B" route | initiative | 90.3% (n=524) | 17.2% (n=58) | 73.0 | 0.0000 |
| Public AI "8B" route | referendum or counterproposal | 40.2% (n=545) | 67.0% (n=203) | -26.8 | 0.0000 |
| Public AI "8B" route, thinking | initiative | 90.6% (n=524) | 17.2% (n=58) | 73.4 | 0.0000 |
| Public AI "8B" route, thinking | referendum or counterproposal | 38.3% (n=545) | 69.5% (n=203) | -31.1 | 0.0000 |
| 70B thinking (Featherless) | initiative | 89.9% (n=524) | 19.0% (n=58) | 70.9 | 0.0000 |
| 70B thinking (Featherless) | referendum or counterproposal | 38.9% (n=545) | 68.0% (n=203) | -29.1 | 0.0000 |
| Baseline: always the FC's line | all | 100.0% | 0.0% | | |
| Baseline: initiatives fail, all else passes | all | 99.3% | 0.0% | | |
<!-- scrutineer:end within_instrument -->

On initiatives the government lost, the people accepted them and the model mostly says
rejected. On referendums the government lost, the people rejected them and the model is right
*more* often than on referendums the government won. A model that repeats the government fails
both. A model with a **default answer of "rejected"** fails the first and passes the second,
which is what the numbers show.

### 2. The answer depends on the language you ask in

<!-- scrutineer:begin language_table -->
| Model | Language | Says accepted | Gold accepted | Accuracy | Abstained |
|---|---|--:|--:|--:|--:|
| 70B (Featherless) | German | 55.3% | 46.1% | 76.3% (n=334) | 4.2% |
| 70B (Featherless) | English | 2.2% | 45.4% | 54.3% (n=328) | 4.0% |
| 70B (Featherless) | French | 4.7% | 46.1% | 54.2% (n=334) | 3.9% |
| 70B (Featherless) | Italian | 33.3% | 46.1% | 67.1% (n=334) | 5.7% |
| 70B (Featherless) | Romansh | 5.6% | 41.9% | 35.5% (n=31) | 41.9% |
| Public AI "8B" route | German | 55.6% | 46.1% | 76.0% (n=334) | 4.2% |
| Public AI "8B" route | English | 2.2% | 45.4% | 54.3% (n=328) | 4.0% |
| Public AI "8B" route | French | 5.0% | 46.1% | 54.5% (n=334) | 3.9% |
| Public AI "8B" route | Italian | 33.5% | 46.1% | 67.1% (n=334) | 5.4% |
| Public AI "8B" route | Romansh | 5.6% | 41.9% | 35.5% (n=31) | 41.9% |
| Public AI "8B" route, thinking | German | 47.2% | 46.1% | 75.7% (n=334) | 4.2% |
| Public AI "8B" route, thinking | English | 15.8% | 45.4% | 58.2% (n=328) | 4.9% |
| Public AI "8B" route, thinking | French | 2.2% | 46.1% | 54.2% (n=334) | 3.0% |
| Public AI "8B" route, thinking | Italian | 24.5% | 46.1% | 62.9% (n=334) | 1.8% |
| Public AI "8B" route, thinking | Romansh | 5.6% | 41.9% | 35.5% (n=31) | 41.9% |
| 70B thinking (Featherless) | German | 46.9% | 46.1% | 74.9% (n=334) | 4.2% |
| 70B thinking (Featherless) | English | 17.4% | 45.4% | 58.5% (n=328) | 4.6% |
| 70B thinking (Featherless) | French | 2.5% | 46.1% | 53.9% (n=334) | 4.2% |
| 70B thinking (Featherless) | Italian | 25.2% | 46.1% | 62.9% (n=334) | 2.7% |
| 70B thinking (Featherless) | Romansh | 0.0% | 41.9% | 32.3% (n=31) | 38.7% |

Votes where German, French, Italian and English give the same answer: 70B (Featherless): 135 of 309 (43.7%); Public AI "8B" route: 137 of 310 (44.2%); Public AI "8B" route, thinking: 153 of 303 (50.5%); 70B thinking (Featherless): 146 of 296 (49.3%).
<!-- scrutineer:end language_table -->

![Share of answers saying "accepted", by question language](track_1b/docs/figures/fig5_language_bias.png)

Asked in French or English, Apertus calls almost every proposal rejected. In German it answers
close to the true rate. A resident asking in French and one asking in German get different
accounts of the same binding decision.

To rule out a prompt artefact, the answer options were reversed ("rejected or accepted") on
every German, French and English item, as a pre-registered test:

<!-- scrutineer:begin order_swap_table -->
Same F1 items, options reversed ("rejected or accepted"), `swiss-ai/apertus-v1.5-8b`, compared with R2:

| Language | n | Says accepted, original order | Says accepted, reversed | Shift (pts) | Answer changed |
|---|--:|--:|--:|--:|--:|
| German | 334 | 55.6% | 32.5% | -23.1 | 23.4% |
| English | 328 | 2.2% | 0.0% | -2.2 | 2.4% |
| French | 334 | 5.0% | 3.4% | -1.5 | 2.4% |
<!-- scrutineer:end order_swap_table -->

French and English do not move. The bias is not the order of the options.

### 3. Reasoning works, recall fails

![Recall (F1) against reasoning from the numbers (F5)](track_1b/docs/figures/fig4_reasoning_vs_recall.png)

Given the yes share and the cantonal votes, the model applies the double-majority rule almost
perfectly, including on the votes the government lost. Asked to recall the same outcome, it
fails on most of them. The failures are memory, not reasoning.

<!-- scrutineer:begin family_table -->
| Family | 70B (Featherless) | Public AI "8B" route | Public AI "8B" route, thinking | 70B thinking (Featherless) |
|---|--:|--:|--:|--:|
| F1 Outcome | 63.0% (n=1330) | 63.0% (n=1330) | 62.8% (n=1330) | 62.6% (n=1330) |
| F2 Yes share | 11.6% (n=1330) | 11.1% (n=1330) | 12.1% (n=1330) | not run |
| F3 FC recommendation | 79.3% (n=1330) | 79.4% (n=1330) | 83.6% (n=1330) | 83.3% (n=636) |
| F4 Cantons majority | 73.0% (n=797) | 72.8% (n=797) | 71.5% (n=797) | not run |
| F5 Reasoning control | 98.5% (n=334) | 98.5% (n=334) | 98.2% (n=334) | 98.2% (n=334) |
| F6 In the constitution | 56.1% (n=214) | 55.6% (n=214) | 55.1% (n=214) | not run |
| F7 Post-cutoff | 100.0% (n=16) | 100.0% (n=16) | 100.0% (n=16) | 100.0% (n=16) |
| F8 Free recall | 61.2% (n=1330) | 61.7% (n=1330) | 55.8% (n=1330) | not run |
<!-- scrutineer:end family_table -->

It also does not know the numbers (F2), and it correctly declines to answer about votes that
have not happened (F7):

<!-- scrutineer:begin secondary_table -->
| Model | F2 MAE (pts) | F2 within 1 pt | F7 abstains (correct) | F5 − F1 de, gov. lost |
|---|--:|--:|--:|--:|
| 70B (Featherless) | 14.5 | 13.0% | 100.0% (n=16) | 65.2 pts |
| Public AI "8B" route | 14.7 | 12.5% | 100.0% (n=16) | 65.2 pts |
| Public AI "8B" route, thinking | 12.3 | 15.4% | 100.0% (n=16) | 56.1 pts |
| 70B thinking (Featherless) | n/a | n/a | 100.0% (n=16) | 56.1 pts |
<!-- scrutineer:end secondary_table -->

### 4. Same weights, different answers

<!-- scrutineer:begin flip_rate -->
The same official 70B weights at temperature 0, served by Public AI and by Featherless, give a different answer on 7.7% of the 287 items both answered, about 1 in 13.
<!-- scrutineer:end flip_rate -->

<!-- scrutineer:begin route_identity_text -->
- the official 70B (Featherless) and Public AI's "8B" route: identical text on 91.9% of 6,716 items
- the official 70B on Featherless and on Public AI: identical text on 92.3% of 287 items
- Public AI's 70B and "8B" routes: identical text on 92.3% of 287 items
- Public AI's "8B" route with thinking and the 70B with thinking (Featherless): identical text on 68.8% of 2,351 items
<!-- scrutineer:end route_identity_text -->

Public AI's `swiss-ai/apertus-v1.5-8b` endpoint answers word for word like the official 70B, as
closely as the two 70B providers match each other. It is routed to a moving alias, not a pinned
checkpoint. Scrutineer therefore reports **no 8B result**, and labels every run by the route it
called ([D24](track_1b/docs/DECISIONS.md)).

---

## What the experiment holds constant

- **Same items, same wording, every run.** The prompt is the item. No system prompt, temperature
  0, seed 0. Every response record stores the sha256 of the exact request body, the provider,
  the endpoint and a timestamp.
- **The claim came first.** The headline claim, its falsifier and the analysis were committed to
  the [claim ledger](track_1b/docs/CLAIM_LEDGER.md) before the first request. When the data
  showed something else, that analysis was registered as exploratory before it was tested.
- **Grading does not depend on the model being graded.** A deterministic five-language parser
  (150 test fixtures, negation and "accepted or rejected" restatements handled) grades most
  answers. A local open-weights judge, Qwen2.5-7B-Instruct on llama.cpp, grades free-text
  answers and anything the parser cannot read. It never sees which model answered, and it is
  never Apertus.
- **The judge is checked.** A seeded 20% sample of judged items was labelled blind by a second
  rater and reviewed by a person. That check exposed a judge bug, and every answer was re-judged
  with the fix. Both versions are reported:

<!-- scrutineer:begin human_table -->
Labelled 311 of 311 sampled judgements (complete). The labeller saw a blind Claude pre-label; human and Claude agree on 99.4% of rows, so judge versus human is close to judge versus Claude and is not an independent second annotation.

| Language | n | Judge 1.1.0 vs human | κ | Judge 1.0.0 vs human | κ |
|---|--:|--:|--:|--:|--:|
| all | 311 | 94.5% | 0.887 | 88.4% | 0.770 |
| German | 83 | 95.2% | 0.901 | 83.1% | 0.667 |
| English | 78 | 89.7% | 0.790 | 78.2% | 0.589 |
| French | 84 | 95.2% | 0.902 | 97.6% | 0.952 |
| Italian | 66 | 98.5% | 0.967 | 95.5% | 0.903 |
<!-- scrutineer:end human_table -->

- **Contamination is measured, not assumed.** None of the source sites is on Apertus's robots.txt
  opt-out lists, so the official pages were eligible for training. Our prompt wording does not
  appear in a FineWeb-2 sample; only fragments of the official titles do.

<!-- scrutineer:begin contamination -->
Apertus robots.txt opt-out lists: `fw1_domains.txt` (487,666 hosts): no swissvotes.ch or admin.ch host; `fw2_domains.txt` (333,971 hosts): no swissvotes.ch or admin.ch host.

| Language | Prompts | With a 13-gram hit | Inside the title only | Touching template | Titles found verbatim |
|---|--:|--:|--:|--:|--:|
| German | 1,928 | 6 | 6 | 0 | 1 of 337 |
| French | 1,594 | 9 | 8 | 1 | 0 of 337 |
| Italian | 1,594 | 9 | 9 | 0 | 0 of 338 |

Sample: 100,000 FineWeb-2 documents per language (revision `af9c1333`, seed 0). Details in `docs/CONTAMINATION.md`.
<!-- scrutineer:end contamination -->

## Runs

<!-- scrutineer:begin runs_table -->
| Run | Model id | Answered | Failed (final) | Failed attempts logged | Cost (USD) | Tokens in / out | Latency p50 / p95 (ms) |
|---|---|--:|--:|--:|--:|--:|--:|
| R1 | `swiss-ai/Apertus-v1.5-70B` | 6,716 / 6,716 | 0 | 0 | 1.0291 | 973,764 / 85,120 | 1626 / 3373 |
| R2 | `swiss-ai/apertus-v1.5-8b` | 6,716 / 6,716 | 0 | 85 | 0.1144 | 973,764 / 85,312 | 880 / 3812 |
| R3 | `swiss-ai/apertus-v1.5-8b` | 6,716 / 6,716 | 0 | 2 | 0.4291 | 973,764 / 1,658,495 | 1341 / 37854 |
| R4 | `swiss-ai/Apertus-v1.5-70B` | 2,351 / 6,716 | 0 | 0 | 1.1372 | 350,212 / 399,425 | 1309 / 24859 |
<!-- scrutineer:end runs_table -->

R1 and R4 are the official `swiss-ai/Apertus-v1.5-70B` weights on Featherless through the
Hugging Face router. R2 and R3 are Public AI's `apertus-v1.5-8b` route. R3 and R4 switch thinking
on through the chat template.

---

## What went wrong, and what we did about it

The honest version is in [`DECISIONS.md`](track_1b/docs/DECISIONS.md), 26 entries. The ones that
change how to read the results:

- **The 70B endpoint went down.** Public AI's 70B returned HTTP 429 for over three hours. R1
  moved to the same official weights on Featherless; the 287 answers Public AI gave first were
  kept and became the deployer-agreement measurement above (D19).
- **The "8B" was not an 8B.** Comparing outputs across runs showed it answering like the 70B
  (D24).
- **The judge had a bug.** "Rejected by a majority of voters" was read as contradicting a low yes
  share. Fixed, everything re-judged, both numbers reported (D22).
- **A runner bug ignored a pre-registered order.** The thinking run (R4) followed the default
  family order instead of its registered sampling plan. It still answered every F1 item, so the
  registered comparison holds; the bug is fixed and tested (D26).
- **The human check leans on the second rater.** The labeller kept 309 of 311 of the second
  rater's labels, so judge-versus-human agreement is close to judge-versus-AI, and is reported
  that way.

---

## Reproduce it

No API key, no GPU, no network beyond the Docker build:

```bash
git clone https://github.com/winsznx/scrutineer && cd scrutineer/track_1b
make run
```

`make run` rebuilds all 6,716 items from the pinned Swissvotes CSV and checks them byte for
byte, replays grading from the stored responses and judge verdicts, recomputes `results.json`
and checks its sha256, checks that every number quoted in this README, the report and the data
card is current, and rebuilds the site. Any mismatch exits non-zero. On a laptop it takes under
a minute after the image build.

Test another model against the same items, on any OpenAI-compatible endpoint:

```bash
pip install -e ".[dev]"
scrutineer run --run-id mymodel --provider env --model <model id>   # LLM_BASE_URL, LLM_API_KEY
make judge-server                                                   # local Qwen judge, once
scrutineer judge && scrutineer grade && scrutineer report
```

The runner resumes from its own file, never pays twice for an item, rate-limits itself, retries
transient errors, and stops under a hard spend cap before it can exceed a wallet.

## How it is built

```
  Swissvotes CSV (pinned) ─┐
                            ├─► scrutineer build ─► 6,716 items (deterministic, hash-checked)
  Chancellery titles ──────┘                              │
                                                          ▼
                                    scrutineer run ─► responses (resumable, budget-capped)
                                                          │
                                  ┌───────────────────────┴───────────────────────┐
                                  ▼                                               ▼
                       parser (5 languages)                        local judge (Qwen2.5-7B)
                                  └───────────────────────┬───────────────────────┘
                                                          ▼
                                       results.json (sha256-checked) ─► report, site, card
```

| Path | What |
|---|---|
| [`track_1b/README.md`](track_1b/README.md) | quickstart for judges and the challenge text |
| [`track_1b/technical_report.md`](track_1b/technical_report.md) | the report source, built to `Scrutineer_Report.pdf` |
| [`track_1b/docs/CLAIM_LEDGER.md`](track_1b/docs/CLAIM_LEDGER.md) | registered claims and their generated status |
| [`track_1b/docs/DECISIONS.md`](track_1b/docs/DECISIONS.md) | every departure from the plan |
| [`track_1b/docs/DATA_CARD.md`](track_1b/docs/DATA_CARD.md) | the dataset card |
| [`track_1b/docs/JUDGE.md`](track_1b/docs/JUDGE.md) | the judge, its prompt versions and agreement |
| [`track_1b/docs/CONTAMINATION.md`](track_1b/docs/CONTAMINATION.md) | the contamination check |
| [`track_1b/docs/ANNOTATION_GUIDE.md`](track_1b/docs/ANNOTATION_GUIDE.md) | the human-check protocol |
| [`track_1b/data/`](track_1b/data/) | items, responses, judge verdicts, human check, `results.json` |
| [`track_1b/src/scrutineer/`](track_1b/src/scrutineer/) | the package: `build`, `run`, `grade`, `report`, `site` |

The package is typed (mypy strict), linted (ruff) and tested (pytest), and installs as the
`scrutineer` command.

## Limitations

- One model size was tested. The 8B could not be reached on a route that verifiably served it.
- "The government lost" coincides with "the uncommon outcome for that instrument" on this set of
  votes. The split by vote type separates them only partly.
- Prompts use the long official titles. People ask with short everyday names, so this measures
  recall under the most informative cue a model could get.
- Templates were written per language, not by native speakers. Romansh covers 35 votes and the
  outcome question only. No dialects.
- The same weights on two providers disagree on several percent of answers, so single-run
  numbers carry a few points of serving noise.

## License

Code Apache-2.0 ([LICENSE](LICENSE)). Dataset CDLA-Permissive-2.0. Report CC-BY-4.0.

Source data: Swissvotes, Année Politique Suisse, Universität Bern (CC BY 4.0), and the Swiss
Federal Chancellery (official texts, open government data). Built from the
[Hack Apertus project template](https://github.com/HackApertus/project-template).
