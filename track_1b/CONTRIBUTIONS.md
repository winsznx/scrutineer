# Contributions back to Apertus

After the hackathon submission is in, the finding goes to the Apertus maintainers as a
discussion on the model page, https://huggingface.co/swiss-ai/Apertus-v1.5-70B/discussions,
with a link to the dataset. Track 1B results are public; it is still posted only
after submission. Draft below. The numbers are generated from `data/results.json`.

---

**Title:** Apertus 1.5 answers Swiss federal vote outcomes differently depending on the question language

**Body:**

Scrutineer is an open benchmark of 6,716 questions about every Swiss federal popular vote
since 1990 in German, French, Italian, English and Romansh, with gold answers from Swissvotes
and official Federal Chancellery titles (dataset: https://huggingface.co/datasets/winsznx/scrutineer,
harness: https://github.com/winsznx/scrutineer).

<!-- scrutineer:begin headline -->
On F1 (did the vote pass?) in German, French, Italian and English, Apertus 1.5 70B is right on **64.7%** of votes the Federal Council won and **55.9%** of votes it lost, a gap of **8.8 points** (z = 2.64, p = 0.0083; n = 1069 and 261 answers). Pre-registered claim C1: **FAILED**.
<!-- scrutineer:end headline -->

The largest effect is the language of the question:

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
| Public AI "8B" route, thinking | English | 15.8% | 45.1% | 59.9% (n=319) | 5.0% |
| Public AI "8B" route, thinking | French | 2.2% | 46.2% | 54.1% (n=329) | 3.0% |
| Public AI "8B" route, thinking | Italian | 24.5% | 46.3% | 64.8% (n=324) | 1.9% |
| Public AI "8B" route, thinking | Romansh | 5.6% | 41.9% | 35.5% (n=31) | 41.9% |
| 70B thinking (Featherless) | German | 63.3% | 58.3% | 75.0% (n=60) | 0.0% |
| 70B thinking (Featherless) | English | 29.1% | 60.0% | 54.5% (n=55) | 0.0% |
| 70B thinking (Featherless) | French | 6.7% | 58.3% | 48.3% (n=60) | 0.0% |
| 70B thinking (Featherless) | Italian | 38.3% | 58.3% | 56.7% (n=60) | 0.0% |

Votes where German, French, Italian and English give the same answer: 70B (Featherless): 135 of 309 (43.7%); Public AI "8B" route: 137 of 310 (44.2%); Public AI "8B" route, thinking: 153 of 303 (50.5%); 70B thinking (Featherless): 19 of 55 (34.5%).
<!-- scrutineer:end language_table -->

<!-- scrutineer:begin order_swap_table -->
Same F1 items, options reversed ("rejected or accepted"), `swiss-ai/apertus-v1.5-8b`, compared with R2:

| Language | n | Says accepted, original order | Says accepted, reversed | Shift (pts) | Answer changed |
|---|--:|--:|--:|--:|--:|
| German | 334 | 55.6% | 32.5% | -23.1 | 23.4% |
| English | 328 | 2.2% | 0.0% | -2.2 | 2.4% |
| French | 334 | 5.0% | 3.4% | -1.5 | 2.4% |
<!-- scrutineer:end order_swap_table -->

For a civic assistant this means the same resident gets a different account of the same
binding decision depending on whether they ask in German or French. Every item, response,
judge verdict and the grading code are in the links above. `make run` reproduces every
number without an API key.
