# Phase 3 target discovery

Status: reviewed target evidence for the first controlled external collection.

## Included target

The first target is the KSTR filing submitted by **Krane Shares Trust**
(`CIK 0001547576`). SEC submissions metadata records accession
`0002048251-26-004699`, filing date `2026-05-29`, and report date
`2026-03-31`. The filing XML identifies the series as **KraneShares SSE Star
Market 50 Index ETF**. The reviewed fund identity is ISIN `US5007676944`.

The SEC metadata supplies a date rather than an intraday timestamp. The target
configuration represents that date as `2026-05-29T00:00:00+00:00` solely as a
normalized date boundary. It is not evidence that publication occurred at
midnight.

Official evidence:

- <https://data.sec.gov/submissions/CIK0001547576.json>
- <https://www.sec.gov/Archives/edgar/data/1547576/000204825126004699/primary_doc.xml>
- <https://kraneshares.com/etf/kstr/>

The exact SEC submissions response is retained content-addressably under
git-ignored `var/ingest/raw/sec_submissions/`. Its SHA-256 is
`1c26aba582a4d4cc921dcee1f9da3835440b3ed60da11e449ea83ea65e1db2dd`.
The filing-specific immutable extract is tracked at
`docs/phase3-sec-metadata-extract.json` so the filing date remains
auditable without another network request.

## Manager-published KSTR CSV

The official file
<https://kraneshares.com/csv/06_30_2026_kstr_holdings.csv> was verified to be
dated `2026-06-30` and to list Cambricon at `9.90%`. It is not part of the first
production target configuration because the file does not expose an exact
publication timestamp and its title row plus English column names require a
reviewed source profile before normalization.

## Exclusions

`docs/phase3-discovery-report.json` accounts for all nine products in
the recorded target universe. Products are excluded rather than inferred when
the fund identifier, qualifying archived document, publication metadata, or
jurisdiction adapter has not been verified. KRX automated acquisition remains
prohibited until a written contract decision changes the source policy.

This report initially established target identity and source availability. The
selected KSTR target was subsequently collected and loaded into disposable local
Neo4j staging; see `docs/data-loading.md`. It has not been loaded into the
Yeongmin Neo4j database.
