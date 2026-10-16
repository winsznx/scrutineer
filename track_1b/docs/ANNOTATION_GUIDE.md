# Annotation guide: human check of the judge

This guide is for the person labelling `data/human_check_review.csv`. It is also the
annotation protocol cited in the data card and the report.

## What you are doing and why

Most answers in Scrutineer are graded by a fixed parser. The free-text ones (F8, a
one-sentence summary of a vote) and a few others are graded by an AI judge, Qwen2.5-7B.
The hackathon rubric requires a human to grade a random 20% of the judge's work, so we
can report how often the judge agrees with a person.

You grade 311 answers. Each one is an answer that Apertus gave to a question about a Swiss
federal vote. You decide whether that answer is right, using only the official facts shown
to you. You never see what the judge decided, which model answered, or which run it came
from. That keeps your grades independent of the judge.

Each row also shows a suggestion from Claude, a second AI rater that labelled the same rows
without seeing the judge either. Treat it as a second opinion you are free to overrule.
The report says you saw it.

## What each row shows

1. **Question put to the model.** The vote date, the official title, and the question. It
   is in German, French, Italian or English. You only need it for context.
2. **Gold (official record).** The true facts, in English, from Swissvotes. Up to three facts:
   - **Outcome:** ACCEPTED or REJECTED.
   - **The Federal Council recommended:** ACCEPTING or REJECTING it. The Federal Council is
     the Swiss government. Its recommendation is not the result.
   - **Yes share:** the percentage of voters who voted yes.
3. **Model's answer.** What Apertus said. Outcome words and percentages are highlighted.
4. **Number check.** Shown when the answer contains a percentage. It tells you how far that
   number is from the gold yes share, and how far it would be if the model meant the no
   share. Red means more than 2 points off both ways.
5. **Suggestion.** Claude's grade. A red "flagged" note means Claude was unsure and says why.

## The three grades

Pick exactly one.

**correct**: the answer states the right outcome, and nothing it says contradicts the gold.
- Extra true details are fine.
- A yes share within 2 percentage points of the gold counts as right.
- Hedging is fine if the answer still commits to the right outcome ("probably accepted").

**incorrect**: any one of these:
- it states the wrong outcome;
- it gives a yes share more than 2 points from the gold;
- it states the Federal Council's recommendation wrongly;
- it states the right outcome but also states a contradicting fact.

**not attempted**: it gives no outcome at all ("I don't know", "I have no information"),
and it states nothing that contradicts the gold.

## Rules for the tricky cases

1. **Check the outcome first.** If the outcome is wrong, the grade is incorrect and you can
   stop reading.
2. **Then check every number and every claim about the Federal Council.** One wrong fact is
   enough for incorrect, even when the outcome is right.
3. **"With a majority of X %" on a rejected proposal.** "Rejected with a majority of 52.3 %"
   means 52.3 % voted no, so the implied yes share is 100 − 52.3 = 47.7 %. Compare that with the gold
   yes share. The number check shows both readings for you.
4. **Within 2 points means 2.00 or less.** 45.80 against 47.70 is 1.90 points apart, so
   correct. 56.42 against 53.40 is 3.02 points apart, so incorrect.
5. **The answer does not have to mention everything.** An answer that only says "it was
   accepted" with nothing else is correct when the gold outcome is ACCEPTED.
6. **Wrong date or garbled title, right outcome.** Grade on the three gold facts only.
   Ignore the date and title wording unless the answer clearly talks about a different vote.
7. **F6 rows** ask whether the proposal was written into the Federal Constitution. The gold
   says YES or NO. A bare "ja", "oui", "sì", "yes" or "no" is a full answer.
8. **Answer contradicts itself** ("accepted ... the proposal failed"): incorrect.
9. **Do not use your own memory of the vote.** The gold is the reference, even if you
   remember it differently.

## Worked examples

Examples A to F are real Apertus answers from outside your sample, so they decide none of your rows. Example G is a made-up illustration.

**A. Wrong outcome, French.** Gold: ACCEPTED, 54.52 % yes. Answer: "Le 23 septembre 1990, le
peuple suisse a rejeté l'initiative..." The answer says rejected (rejeté), and the gold
says accepted. Grade: **incorrect**.

**B. Wrong outcome, Italian.** Gold: ACCEPTED, 74.67 % yes. Answer: "Il popolo svizzero ha
respinto il decreto federale..." The answer says rejected (respinto). Grade: **incorrect**.

**C. Right outcome, wrong number.** Gold: ACCEPTED, 71.48 % yes. Answer: "...wurde mit
63,3 % Ja-Stimmen angenommen." The outcome is right, but 63.3 is 8.2 points off.
Grade: **incorrect**.

**D. Right outcome, number in range.** Gold: REJECTED, 45.80 % yes. Answer: "...mit einer
Mehrheit von 52,3 % der Stimmen abgelehnt." That means 52.3 % voted no, so 47.7 % voted yes,
1.9 points from the gold. Grade: **correct**.

**E. F6 bare answer.** Gold: written into the constitution: YES. Answer: "ja". Grade: **correct**.

**F. Wrong outcome despite a plausible number.** Gold: REJECTED, 47.36 % yes. Answer:
"...wurde mit einer Mehrheit von 55,8 % Ja-Stimmen angenommen." The answer says
accepted, and the gold says rejected. Grade: **incorrect**.

**G. No answer.** Answer: "Ich habe keine Informationen über das Ergebnis dieser
Abstimmung." It names no outcome and states nothing false. Grade: **not attempted**.

## How to use the labelling page

1. Start it (Claude starts it for you) and open http://127.0.0.1:8766 in your browser.
2. For each row: read the gold, read the answer, look at the number check, decide.
3. Press a key:

   | Key | Grade |
   |---|---|
   | `1` | correct |
   | `2` | incorrect |
   | `3` | not attempted |
   | `Enter` | the same as Claude's suggestion |
   | `←` `→` | previous / next row without grading |
   | `U` | clear the grade on this row |

4. The page saves the moment you press a key and moves to the next unlabelled row.
   It records the time of each grade in `labelled_at`. You can close the tab and come back
   later. It reopens at the first row you have not graded.
5. When the counter reads 311 / 311, you are done.

Use `Enter` only after you have checked the row and agree with the suggestion. Pressing it
without reading would turn this into a copy of Claude's labels, and the report would no
longer be measuring a human.

The first 18 rows are the ones Claude flagged as unsure. Expect them to be the slowest.
After that, most rows take 5 to 15 seconds: find the outcome word, glance at the number
check, press a key.

## What happens with your grades

`scrutineer grade` compares your grades with the judge's, as raw agreement and Cohen's
kappa, overall, per language and per question family. It does the same for Claude against
you. All three numbers appear in the report next to a statement of how the sample was
drawn and that you saw Claude's suggestion.
