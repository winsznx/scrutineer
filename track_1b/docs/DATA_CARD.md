---
license: cdla-permissive-2.0
language:
- de
- fr
- it
- en
- rm
pretty_name: Scrutineer
size_categories:
- 1K<n<10K
task_categories:
- question-answering
tags:
- switzerland
- direct-democracy
- factuality
- multilingual
- apertus
- hackapertus
configs:
- config_name: items
  data_files:
  - split: test
    path: items.jsonl
- config_name: metadata
  data_files:
  - split: test
    path: metadata.jsonl
- config_name: responses
  data_files:
  - split: R1_apertus_v1.5_70b
    path: responses/R1.jsonl
  - split: R2_apertus_v1.5_8b
    path: responses/R2.jsonl
  - split: R3_apertus_v1.5_8b_thinking
    path: responses/R3.jsonl
---

# Dataset Card for Scrutineer

Scrutineer asks a language model what the Swiss people decided in each federal popular vote
since 1990, in German, French, Italian, English and Romansh, and records where and why it
gets the answer wrong. Every gold answer comes from the Swissvotes database and every vote
title from the Federal Chancellery. Nothing in the dataset was written or translated by a
language model, except the question templates noted under Annotations.

<!-- scrutineer:begin dataset_stats -->
6,716 items over 334 decided federal votes (1 Jan 1990 to 27 Sep 2026, 66 of them lost by the Federal Council) plus the 4 votes of 29 Nov 2026.

By family: F1 1,361 · F2 1,330 · F3 1,330 · F4 797 · F5 334 · F6 214 · F7 20 · F8 1,330.

By language: German 1,928 · English 1,565 · French 1,594 · Italian 1,594 · Romansh 35.

`items.jsonl` sha256 `fe3ee9af2f440fa314554c0201e5fff83145bbe3e49bcb5e4e7400b86e1625ee`.
<!-- scrutineer:end dataset_stats -->

## Dataset Details

The dataset has three parts:

- `items`: the evaluation set. One question per row, with a gold answer, accepted answer
  variations, source citations and stratum labels.
- `responses`: the verbatim answers of Apertus 1.5 models to every item, one split per run,
  with request hashes, token usage, cost and latency.
- `metadata`: one row per item with instance-level provenance and licensing.

Eight question families probe the same vote from different sides:

| Family | Question | Gold | Graded by |
|---|---|---|---|
| F1 | Was the proposal accepted or rejected? | Swissvotes `annahme` | parser, judge if unparseable |
| F2 | What share of voters said yes? | `volkja-proz`, ±1.0 point | numeric parser |
| F3 | What did the Federal Council recommend? | `br-pos` | parser |
| F4 | Did a majority of cantons accept it? (initiatives, mandatory referendums) | `kt-ja` > `kt-nein` | parser |
| F5 | Given the yes share and cantonal votes, was it accepted? (no title, German) | `annahme` | parser |
| F6 | Was it written into the Federal Constitution? (initiatives, counter-proposals; balanced yes/no) | `annahme` | judge, parser recorded |
| F7 | Outcome of a vote of 29 November 2026, after the data cut-off | not yet decided; abstaining is correct | parser |
| F8 | One-sentence summary of how the vote turned out | outcome, FC position, yes share | judge |

- **Curated by:** Tim (GitHub `winsznx`), for the Hack Apertus online hackathon, track 1B
- **Funded by:** no funding. Model calls used the Public AI starter credit
- **Shared by:** Tim (`winsznx`)
- **Language(s) (NLP):** German (de-CH usage), French, Italian, English, Romansh (Rumantsch Grischun, F1 and F7 only)
- **License:** CDLA-Permissive-2.0 for the items, metadata and responses. Source facts from
  Swissvotes are CC BY 4.0; titles are official federal documents. See Data Instance Licenses
- **Git repository:** https://github.com/winsznx/scrutineer (directory `track_1b/`)

## Uses

The use case is a civic information assistant for Swiss public bodies and residents: a
chatbot that answers "what did we vote on X, and what happened?". Such an assistant built on
Apertus will be asked these questions in every national language. A wrong answer here misstates
a binding democratic decision.

### Direct Use

- Measuring whether a model recalls Swiss federal vote outcomes, yes shares, Federal Council
  recommendations and cantonal majorities, per language, decade, instrument and margin.
- Measuring whether errors depend on the Federal Council having lost the vote (stratum
  `gov_lost`), and comparing recall (F1) with reasoning from given numbers (F5).
- Measuring abstention on votes after the model's data cut-off (F7).
- Regression testing of new Apertus checkpoints: `scrutineer run --model <id>` runs any
  OpenAI-compatible endpoint against the same items.

### Out-of-Scope Use

- Not a source of truth about votes. Use Swissvotes or the Federal Chancellery directly.
- Not a measure of political opinion or bias in a partisan sense. `gov_lost` describes
  whether the Federal Council's recommendation prevailed, not any party position.
- Romansh coverage is 35 votes and only F1/F7. It is too small for strong conclusions.
- Training on the items would contaminate the benchmark. Please don't.

### Specifications

- Universe: every federal vote from 1 January 1990 to 27 September 2026 with a decided
  outcome (`annahme` 0 or 1) and a Federal Council recommendation of accept or reject
  (`br-pos` 1 or 2). Tie-break questions and votes without a recommendation are excluded.
- Post-cutoff controls: the four votes of 29 November 2026 (outcome not yet known at build).
- Prompt format: a header with the vote date and official title in the item language,
  then one question and a format instruction, for example "Answer with one word: accepted or
  rejected. If you do not know, say that you do not know." No system prompt.
- Inference settings used for the responses: temperature 0, seed 0, `max_tokens` 60
  (F8: 120; thinking models: 2,000).

## Dataset Structure

`items.jsonl` fields:

| Field | Meaning |
|---|---|
| `item_id` | `<anr>-<family>-<lang>`, e.g. `675-F1-it` |
| `anr` | Swissvotes vote number (`465.1`, `465.2` for an initiative and its counter-proposal) |
| `vote_date` | ISO date |
| `family`, `lang` | question family F1 to F8, language code |
| `prompt` | exact text sent to the model |
| `gold` | family-specific gold, e.g. `{"outcome": "accepted"}` or `{"yes_share": 58.24, "tolerance": 1.0}` |
| `gold_answers` | accepted answer variations in the item language (e.g. `abgelehnt`, `verworfen`) |
| `gold_source_url`, `gold_source_urls` | Swissvotes vote page and Chancellery chronology page |
| `title`, `title_source`, `title_source_url` | title used in the prompt, where it came from, its LINDAS IRI |
| `strata` | `gov_lost`, `instrument`, `margin_bucket`, `era`, `lang`, `double_majority_split` |
| `template_id`, `template_version`, `generator_version` | provenance of the wording |
| `source_row_sha256` | sha256 of the raw Swissvotes CSV row the gold comes from |

`responses/<run>.jsonl` fields: `item_id`, `run_id`, `model`, `provider`, `endpoint`,
`request_sha256` (sha256 of the canonical request body), `status` (`ok` or `failed`),
`response` (verbatim), `reasoning` (thinking trace, if any), `finish_reason`, `usage`,
`cost_usd`, `request_id`, `served_model`, `latency_ms`, `attempts`, `http_status`, `timestamp`.
Files are append-only. A retried item appears more than once, and the last record counts.

`metadata.jsonl`: `item_id`, licences per component, source URLs, row hash, title provenance.

There is a single `test` split. The strata labels define the analysis slices.

## Dataset Creation

### Curation Rationale

Apertus is presented as Switzerland's model, and the federal popular vote is Switzerland's
defining civic act. In a pre-check on 13 October 2026, Apertus 1.5 70B, asked through Public AI
chat, reported the wrong outcome for 8 of 9 votes in which the people overruled the Federal
Council. It said the 13th AHV pension (accepted 3 March 2024, 58.2% yes) was rejected, in four
languages. No public benchmark measured multilingual recall of Swiss vote outcomes, so there
was no way to tell whether this was anecdote or pattern.

### Source Data

- Swissvotes dataset, release with data state 28.09.2026 (Année Politique Suisse,
  Universität Bern), CC BY 4.0. Pinned file sha256
  `594dbafb5c9ae8f7563f1e0e3de00cac561993cdfd53034e86ed8bce1ddc3a35`.
- Official vote titles in five languages from the Federal Chancellery's linked-data cube
  `https://politics.ld.admin.ch/political-rights/popular-vote/1` on LINDAS, which is the
  source of the Chancellery's own vote pages.

Details, hashes and fetch dates: `data/SOURCES.md` in the repository.

#### Data Collection

`scrutineer build` reads the pinned CSV, selects the universe, joins the stored titles and
renders each item from a hand-written template per language. The build is deterministic:
`scrutineer build --check` and `make run` regenerate `items.jsonl` and fail if a single byte
differs. Titles were fetched once with `scrutineer fetch-titles` and stored with their fetch
time and IRI.

#### Source Data Producers and Data Subjects

Swissvotes is compiled by political scientists at Année Politique Suisse from official
results. Titles and results are published by the Federal Chancellery. The data subjects are
votes, which are public acts of the electorate. No individual is represented. Initiative
committee members' names, present in some Swissvotes columns, were not used.

#### Ownership and Consent Management

There are no human subjects. All source data is public, aggregate and published under open
terms for reuse with attribution: CC BY 4.0 for Swissvotes and open government data terms for
federal documents. No consent form applies, because no person contributed data about
themselves, no personal data is processed, and the only annotator is the dataset author. AI
use permissions: Swissvotes' CC BY 4.0 allows reuse including for evaluation. The Chancellery
publishes the titles as open government data. Neither domain is on Apertus's robots.txt
opt-out lists (see `docs/CONTAMINATION.md`).

#### Data Processing and Quality Control

- Universe filters and strata are computed in code from named CSV columns
  (`src/scrutineer/build/swissvotes.py`) and covered by tests.
- Titles are used verbatim. Missing titles are omitted per language and logged, never
  filled by translation (`data/items.manifest.json`, `omitted_titles`, `fallback_titles`).
- English titles fall back to the Swissvotes English short title where the Chancellery has
  none (73 votes); 6 votes have no English title and no English items.
- F6 negatives were added (rejected proposals, matched by decade, seed 20260929) so the
  family is balanced.
- Each item records the hash of its source row, so gold values can be checked against the
  pinned CSV.
- Parser: 150 hand-written fixtures (30 per language) in `tests/fixtures/parse_fixtures.yaml`.
- Contamination check: domain opt-out lists and 13-gram overlap with a FineWeb-2 sample
  (`docs/CONTAMINATION.md`).

<!-- scrutineer:begin contamination -->
_Contamination check not run yet._
<!-- scrutineer:end contamination -->

#### Data Instance Licenses

| Component | Licence |
|---|---|
| Item text (prompts, templates, gold answer variations, strata) | CDLA-Permissive-2.0 |
| Gold facts (outcome, yes share, cantons, recommendation) | from Swissvotes, CC BY 4.0, attribution: Swissvotes, Année Politique Suisse, Universität Bern |
| Vote titles | official texts of the Swiss Federal Chancellery (LINDAS), open government data, attribution required |
| Model responses | outputs of Apertus 1.5 (Apache-2.0 model), released under CDLA-Permissive-2.0 |

Each row of `metadata.jsonl` repeats these per item.

### Annotations

The gold labels are not annotations. They are copied from Swissvotes. Two kinds of human
or model work are involved:

1. Question templates: one per family and language (`src/scrutineer/templates/`), written
   directly in each language in the formal register by the AI coding assistant that built
   the harness, then reviewed by the author. They were not machine-translated from another
   language. A native-speaker review is still pending, most of all for Romansh.
2. Judge labels: F6, F8 and unparseable answers are graded by Qwen2.5-7B-Instruct (local,
   temperature 0). A blind 20% sample was labelled by the author to measure agreement.

#### Annotation Process

Human check: a seeded random 20% of all judged items is exported to `human_check.csv` in
shuffled order. Each row shows only an opaque id, the question, the gold facts and the answer.
Model, run and judge verdict are hidden in a separate key file. The labeller assigns
`correct`, `incorrect` or `not_attempted` under the same SimpleQA rules the judge uses, and
records a timestamp per row.

<!-- scrutineer:begin human_table -->
_Human check status: not exported._
<!-- scrutineer:end human_table -->

#### Annotator Details

One annotator: the dataset author, fluent in English, working from the gold facts given in
each row. That is a limitation: the check measures whether the judge applies the rules as a
careful reader would, not native-speaker judgement of nuance.

## Risks, Bias, and Limitations

- The `gov_lost` effect is confounded with the instrument's base rate. In this universe every
  government-lost initiative was accepted and every government-lost referendum was rejected,
  so "repeats the government" and "assumes initiatives fail and referendums pass" cannot be
  separated. Reported results say "coincides with", not "aligned with".
- Official titles are long and formal. Users ask with short names ("13th AHV pension"), so
  recall may differ in practice.
- Swiss German dialects are not covered. Romansh coverage is thin.
- F2 tolerance (±1 point) and the F8 judge rules are design choices that affect scores.
- The judge is a 7B model. Its agreement with a human is measured on a sample, not guaranteed.
- Responses come from one hosted endpoint (Public AI) on given dates. Endpoint-to-weights
  agreement is reported in the report when the local replay has run.

### Personally Identifiable Information

None. Items describe votes, not people. Initiative committee and author names in Swissvotes
were not used.

### Sensitive Information

Political subject matter: votes on immigration, religion, taxation, social security and
more. The dataset records official outcomes only, not opinions about them. It contains no
data about any individual's political views.

### Recommendations

Report results per stratum, not just overall accuracy. Compare against the two reference
baselines (`fc_echo`, `instrument_prior`) before reading the government-lost gap as alignment.
Treat Romansh numbers as indicative.

## Citations

**BibTeX:**

```bibtex
@misc{scrutineer2026,
  title  = {Scrutineer: multilingual recall of Swiss federal vote outcomes},
  author = {Tim (winsznx)},
  year   = {2026},
  howpublished = {\url{https://huggingface.co/datasets/winsznx/scrutineer}},
  note   = {Hack Apertus 2026, track 1B}
}
@misc{swissvotes,
  title  = {Swissvotes: die Datenbank der eidgen{\"o}ssischen Volksabstimmungen},
  author = {{Ann{\'e}e Politique Suisse}},
  institution = {Institut f{\"u}r Politikwissenschaft, Universit{\"a}t Bern},
  howpublished = {\url{https://swissvotes.ch}},
  note   = {Dataset state 28.09.2026, CC BY 4.0}
}
```

**APA:**

Tim (winsznx). (2026). *Scrutineer: Multilingual recall of Swiss federal vote outcomes*
[Data set]. Hugging Face. https://huggingface.co/datasets/winsznx/scrutineer

Année Politique Suisse. (2026). *Swissvotes – die Datenbank der eidgenössischen
Volksabstimmungen* [Data set, state 28.09.2026]. Universität Bern. https://swissvotes.ch

## Glossary

- **Federal Council (Bundesrat / Conseil fédéral):** the Swiss government. It recommends a
  yes or no vote on every proposal.
- **gov_lost:** 1 if the people's decision went against the Federal Council's recommendation.
- **Popular initiative:** a citizen proposal to amend the constitution. It needs a majority
  of voters and of cantons.
- **Mandatory / optional referendum:** a vote on an act of parliament, required by the
  constitution or triggered by 50,000 signatures.
- **Cantonal majority (Ständemehr):** a majority of the 23 cantonal votes. Six half-cantons
  count as half a vote.
- **SimpleQA grading:** correct / incorrect / not attempted, where a confident wrong answer
  is worse than an abstention.

## More Information

Harness, report and reproducibility instructions: the `track_1b/` directory of the
repository. `make run` replays all grading in Docker without an API key and checks the
results hash.

## Dataset Card Authors

Tim (`winsznx`).

## Dataset Card Contact

GitHub issues at https://github.com/winsznx/scrutineer.
