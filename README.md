# Scrutineer

**Does Apertus know what the Swiss people decided?** Scrutineer asks Apertus 1.5 about every
Swiss federal popular vote since 1990: 334 decided votes plus 4 not yet held, 6,716 questions
in German, French, Italian, English and Romansh, with gold answers from Swissvotes
(Universität Bern) and the Federal Chancellery's official vote titles.

Hack Apertus 2026, Track 1B Swiss Voices (core task intelligence). The project lives in
[`track_1b/`](track_1b/).

| | |
|---|---|
| Live site and vote explorer | https://winsznx.github.io/scrutineer/ |
| Report (PDF, 4 pages) | [`track_1b/Scrutineer_Report.pdf`](track_1b/Scrutineer_Report.pdf) |
| Dataset (items, responses, metadata) | https://huggingface.co/datasets/winsznx/scrutineer |
| Full README, quickstart, results | [`track_1b/README.md`](track_1b/README.md) |

## What we found

- The pre-registered claim, that Apertus repeats the government's line on votes the
  government lost, **failed**: the gap is 8.8 points, under the 10-point falsifier.
- The real pattern is a **default answer of "rejected"**, and how strong it is depends on the
  language: about 95% "rejected" when asked in French or English, close to the true rate in
  German.
- **Reasoning works, recall fails**: given the yes share and cantonal votes the model is right
  95.5% of the time on votes the government lost, and 30.3% when asked to remember.
- **Serving matters**: the same official 70B weights on two providers differ on 7.7% of
  answers at temperature 0, and Public AI's 8B endpoint answers like the 70B, so no 8B result
  is reported.

![Share of answers saying "accepted", by question language](track_1b/docs/figures/fig5_language_bias.png)

## Reproduce

```bash
git clone https://github.com/winsznx/scrutineer && cd scrutineer/track_1b
make run    # Docker, under a minute after the image build, no API key
```

`make run` rebuilds all 6,716 items from the pinned sources, replays grading from the stored
responses and judge verdicts, checks `results.json` against its recorded hash and every number
quoted in the docs, and rebuilds the site. It exits non-zero on any mismatch.

## Where things are

| Path | What |
|---|---|
| `track_1b/technical_report.md` | the report source |
| `track_1b/docs/CLAIM_LEDGER.md` | the claim, registered before the first model request, and its status |
| `track_1b/docs/DECISIONS.md` | every departure from the plan (D1 to D26) |
| `track_1b/docs/DATA_CARD.md` | the dataset card |
| `track_1b/data/` | items, responses, judge verdicts, human check, `results.json` |
| `track_1b/src/scrutineer/` | the package: build, run, grade, report, site |

## License

Code Apache-2.0 ([LICENSE](LICENSE)). Dataset CDLA-Permissive-2.0. Report CC-BY-4.0. Source
data: Swissvotes (Année Politique Suisse, Universität Bern, CC BY 4.0) and the Swiss Federal
Chancellery.

Built from the [Hack Apertus project template](https://github.com/HackApertus/project-template).
