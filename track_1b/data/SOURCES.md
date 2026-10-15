# Sources

Every number in this benchmark traces back to one of the sources below. Files are pinned
by SHA-256. `scrutineer build --check` rebuilds `items.jsonl` from them and fails if the
result differs by a single byte.

## Swissvotes dataset

| Field | Value |
|---|---|
| File | `data/swissvotes_dataset.csv` |
| Origin | https://swissvotes.ch/page/dataset/swissvotes_dataset.csv |
| Codebook | https://swissvotes.ch/page/dataset/codebook-de.pdf |
| Publisher | Année Politique Suisse, Institut für Politikwissenschaft, Universität Bern |
| Licence | CC BY 4.0 |
| Data state | 28.09.2026 (Swissvotes release after the 27 Sep 2026 votes) |
| Size | 2,724,453 bytes, 714 vote rows, 874 columns, `;` separated, UTF-8 with BOM, CRLF |
| SHA-256 | `594dbafb5c9ae8f7563f1e0e3de00cac561993cdfd53034e86ed8bce1ddc3a35` |
| Fetched | 2026-10-15. The local copy and a fresh download on that date were byte-identical |

Columns used: `anr`, `datum`, `titel_kurz_d`, `titel_kurz_f`, `titel_kurz_e`, `titel_off_d`,
`titel_off_f`, `rechtsform`, `br-pos`, `bv-pos`, `annahme`, `volk`, `stand`, `volkja-proz`,
`kt-ja`, `kt-nein`, `bkchrono-de`, `bkchrono-fr`, `swissvoteslink`. Each item stores
`source_row_sha256`, the SHA-256 of the raw bytes of its CSV row (without the CRLF), so a
reader can check any item against the pinned file.

Citation: Swissvotes – die Datenbank der eidgenössischen Volksabstimmungen. Année Politique
Suisse, Universität Bern. www.swissvotes.ch.

## Official vote titles (Federal Chancellery, LINDAS)

| Field | Value |
|---|---|
| File | `data/titles_chancellery.jsonl` |
| Origin | SPARQL endpoint `https://cached.lindas.admin.ch/query`, cube `https://politics.ld.admin.ch/political-rights/popular-vote/1` |
| Publisher | Swiss Federal Chancellery, via LINDAS (the federal linked-data service) |
| Licence | Official federal documents, Swiss open government data (opendata.swiss terms: open use, source must be cited) |
| Query | `TITLE_QUERY` in `src/scrutineer/build/titles.py` |
| Fetched | stored per record in `fetched_at` |

The Chancellery's vote pages (`bk.admin.ch/<lang>/details-...?voteNumber=N`, the
`bkchrono-de`/`bkchrono-fr` links in the CSV) render client-side from this same cube, so
the stored titles are the titles those pages show. Each record carries the title IRI.
Titles are stored and used verbatim, including the Chancellery's own typos. No title was
translated, by a person or a model.

`scrutineer fetch-titles` refreshes the file. Its SHA-256 is recorded in
`data/items.manifest.json` (`titles_sha256`).
