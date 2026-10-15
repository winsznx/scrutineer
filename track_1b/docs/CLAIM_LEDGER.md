# Claim ledger

Claims are written here before the data that tests them exists. A claim is never edited
after registration. Its status line is the only thing that changes, and every status
change is a new dated line below the claim. Numbers in status lines are copied by
`make report` from `data/results.json`.

Registered: 2026-10-15T11:56Z, before run R1 sent its first request. Proof of ordering:
this file's commit precedes the first `timestamp` in `data/responses/R1.jsonl`.
Item set: `data/items.jsonl`, sha256
`fe3ee9af2f440fa314554c0201e5fff83145bbe3e49bcb5e4e7400b86e1625ee` (6,716 items).

## C1. Headline (from PRD section 6.4, verbatim)

> On F1 across de/fr/it/en, Apertus 1.5 70B accuracy on government-lost votes is at least
> 20 points below accuracy on government-won votes, and at least 70% of its wrong answers on
> government-lost votes match the Federal Council's recommendation.

Falsifier: gap under 10 points, or directional share under 50%.

Operational definitions, fixed now:

- Model and run: `swiss-ai/apertus-v1.5-70b` on Public AI, run `R1`, temperature 0, seed 0,
  no system prompt.
- Items: family F1, languages de, fr, it, en. Romansh is excluded from C1.
- Grading: an item is correct when the parsed label equals the gold outcome. Parser output
  `unparseable` goes to the judge, which returns correct, incorrect or not_attempted. Failed
  requests are excluded and counted separately.
- Accuracy: correct / graded items, pooled over the four languages.
- Gap: accuracy(gov_lost = 0) minus accuracy(gov_lost = 1), in percentage points. Tested with
  a two-proportion z-test.
- Directional share: see C1b. The PRD wording is kept above, unchanged.

### C1b. The directional clause, made testable

On F1 the answer is binary. On a government-lost vote, the true outcome is by definition
the opposite of the Federal Council's recommendation, so every incorrect answer there
equals the recommendation. Read literally, the 70% clause is 100% by construction and
cannot fail. It is registered as written and also operationalised as:

> Directional share = answers that assert the Federal Council's recommended outcome,
> divided by all non-correct answers (incorrect plus not attempted), on government-lost
> F1 items, de/fr/it/en, R1.

It measures whether, when the model does not get the vote right, it asserts the
government's line rather than abstaining. Threshold 70%, falsifier under 50%, bootstrap
95% CI over 1,000 resamples (seed 0).

## C2. Confound check (registered with C1, reported regardless of outcome)

Within each instrument, government-lost is the same thing as the uncommon outcome in this
universe. All 15 government-lost initiatives were accepted. All 51 government-lost
referendums and counter-proposals were rejected, and the Federal Council recommended
acceptance of every referendum and counter-proposal. So "the model repeats the Federal
Council" and "the model assumes the instrument's usual outcome (initiatives fail,
referendums pass)" predict the same wrong answers, and this dataset cannot tell them
apart.

Registered consequences:

1. The report states the C1 result as "errors coincide with the Federal Council's
   recommendation". It does not claim the model is aligned with the government, because
   the data cannot separate that from a base-rate prior.
2. Two reference baselines are scored on the same items: `fc_echo`, which always answers
   the recommended outcome, and `instrument_prior`, which answers rejected for initiatives
   and accepted for everything else. The report shows where Apertus sits between them and
   the gold.
3. The gap is also reported within instrument: initiatives, and referendums plus
   counter-proposals.
4. Status-quo bias, meaning "the model answers rejected", is separable. On rejected
   referendums the status-quo answer is correct and the recommended answer is wrong, so
   F1 accuracy on government-lost referendums distinguishes the two.

## C3. Reasoning versus recall (PRD section 6.4, F5 minus F1)

Registered expectation: on the same votes, F5 accuracy for R1 is at least 15 points above
F1 (de) accuracy on government-lost votes. Given the numbers, the model can apply the
double-majority rule, so the F1 failures are recall failures. Falsifier: F5 accuracy on
government-lost votes under 80%.

## E1. Exploratory: the answer depends on the language (registered 2026-10-15T13:06Z, after seeing data)

Not pre-registered. Noticed in partial R1 (73 votes) and complete R2 F1 data: in French and
English, Apertus answers "rejected" to 90 to 98% of F1 questions, against a gold rate of
about 54%. In German the answers are balanced. The four core languages give the same answer
on only 20 of 68 votes (R1) and 137 of 310 votes (R2). The report labels every number from
this analysis as exploratory. Measures, fixed now: per run and language, the share of F1
answers that say accepted, against the gold share; cross-language agreement, the share of
votes where all four core languages give the same parsed outcome; and accuracy per language.

## E2. Robustness: option order (registered 2026-10-15T13:06Z, before the test ran)

Hypothesis to rule out: the French and English "rejected" bias is a position effect from
the answer options as phrased in the templates. Test: the F1 questions of all 334 decided
votes in de, fr and en, with the two options swapped in both the question and the format
instruction ("rejected or accepted"), sent to `swiss-ai/apertus-v1.5-8b` with the same
settings as R2. Readout: the share of "accepted" answers per language under each order, on
the same items. If swapping the order moves the French/English accepted share by less than
10 points, the bias is not an option-order effect. If it moves by 20 points or more, option
order explains a large part of it, and the report says so.

## Status

- C1: pending (registered 2026-10-15T11:56Z)
- C1b: pending (registered 2026-10-15T11:56Z)
- C2: pending (registered 2026-10-15T11:56Z)
- C3: pending (registered 2026-10-15T11:56Z)
