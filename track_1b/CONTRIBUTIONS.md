# Contributions back to Apertus

After the hackathon submission is in, the finding goes to the Apertus maintainers as an
issue on https://github.com/swiss-ai/apertus-tech-report (or the model repository they
point to), with a link to the dataset. Track 1B results are public; it is still posted only
after submission. Draft below. The numbers are generated from `data/results.json`.

---

**Title:** Apertus 1.5 answers Swiss federal vote outcomes differently depending on the question language

**Body:**

Scrutineer is an open benchmark of 6,716 questions about every Swiss federal popular vote
since 1990 in German, French, Italian, English and Romansh, with gold answers from Swissvotes
and official Federal Chancellery titles (dataset: https://huggingface.co/datasets/winsznx/scrutineer,
harness: https://github.com/winsznx/scrutineer).

<!-- scrutineer:begin headline -->
On F1 (did the vote pass?) in German, French, Italian and English, Apertus 1.5 70B is right on **60.2%** of votes the Federal Council won and **48.5%** of votes it lost, a gap of **11.7 points** (z = 1.69, p = 0.0917; n = 221 and 66 answers). Pre-registered claim C1: **INCONCLUSIVE**.
<!-- scrutineer:end headline -->

The largest effect is the language of the question:

<!-- scrutineer:begin language_table -->
| Model | Language | Says accepted | Gold accepted | Accuracy | Abstained |
|---|---|--:|--:|--:|--:|
| Apertus 1.5 70B | German | 69.9% | 57.5% | 71.2% (n=73) | 0.0% |
| Apertus 1.5 70B | English | 4.3% | 58.0% | 46.4% (n=69) | 0.0% |
| Apertus 1.5 70B | French | 9.6% | 57.5% | 46.6% (n=73) | 0.0% |
| Apertus 1.5 70B | Italian | 59.7% | 58.3% | 65.3% (n=72) | 0.0% |
| Apertus 1.5 8B | German | 55.6% | 46.1% | 76.0% (n=334) | 4.2% |
| Apertus 1.5 8B | English | 2.2% | 45.4% | 54.3% (n=328) | 4.0% |
| Apertus 1.5 8B | French | 5.0% | 46.1% | 54.5% (n=334) | 3.9% |
| Apertus 1.5 8B | Italian | 33.5% | 46.1% | 67.1% (n=334) | 5.4% |
| Apertus 1.5 8B | Romansh | 5.6% | 41.9% | 35.5% (n=31) | 41.9% |
| Apertus 1.5 8B thinking | German | 52.0% | 46.6% | 78.4% (n=148) | 0.0% |
| Apertus 1.5 8B thinking | English | 18.7% | 47.9% | 58.5% (n=142) | 0.0% |
| Apertus 1.5 8B thinking | French | 2.7% | 46.9% | 55.8% (n=147) | 0.0% |
| Apertus 1.5 8B thinking | Italian | 29.3% | 46.9% | 64.6% (n=147) | 0.0% |

Votes where German, French, Italian and English give the same answer: Apertus 1.5 70B: 20 of 68 (29.4%); Apertus 1.5 8B: 137 of 310 (44.2%); Apertus 1.5 8B thinking: 63 of 139 (45.3%).
<!-- scrutineer:end language_table -->

<!-- scrutineer:begin order_swap_table -->
Same F1 items, options reversed ("rejected or accepted"), `swiss-ai/apertus-v1.5-8b`, compared with R2:

| Language | n | Says accepted, original order | Says accepted, reversed | Shift (pts) | Answer changed |
|---|--:|--:|--:|--:|--:|
| German | 19 | 57.9% | 47.4% | -10.5 | 10.5% |
| English | 18 | 0.0% | 0.0% | 0.0 | 0.0% |
| French | 18 | 11.1% | 5.6% | -5.6 | 5.6% |
<!-- scrutineer:end order_swap_table -->

For a civic assistant this means the same resident gets a different account of the same
binding decision depending on whether they ask in German or French. Every item, response,
judge verdict and the grading code are in the links above. `make run` reproduces every
number without an API key.
