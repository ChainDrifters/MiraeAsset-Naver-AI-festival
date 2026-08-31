# Contest entity crosswalk

`contest_entities.csv` is the reviewed freeze set of officially verified
identities for contest questions as of 2026-08-21. Every row was reviewed
against an official issuer, exchange, or regulator page
(`reviewed_by=official-source-audit`, `reviewed_at=2026-08-21`), and
`source_url` records the exact official page on which the identity was
verified. The header is exactly the ten fields expected by
`CROSSWALK_FIELDS` in `src/mirae_asset_graph/ingest/crosswalk.py`, and
`load_crosswalk` rejects any row that breaks that contract.

## Scope of the evidence

- Rows are **identity evidence only**. A row establishes that one local key
  (an exchange listing code, ticker, or DART corporation code) refers to the
  named company or fund. Rows are not holdings, portfolio-composition, or
  corporate-control evidence, and they assert no parent/subsidiary or
  manager relationship. The private EcoPro companies are recorded for
  identity only; no control or subsidiary claim is made for them.
- Where an official ISIN was not verified, the standard identifier
  deliberately uses the official exchange or regulator code instead: the SSE
  listing code for Cambricon, KRX codes for the Korean PLUS funds, and the
  Nasdaq ticker for SMHC. These entities remain unresolved for ISIN-only
  loading until a later crosswalk enrichment verifies an official ISIN. No
  ISIN is invented, derived, or carried over from unreviewed sources.
- Entities are never merged by name alone. `detect_name_only_merge` enforces
  this on load, and `tests/test_crosswalk.py` runs it against the real CSV.
- The verified source universe behind these entities (issuers, listing
  venues, and the official pages reviewed 2026-08-19) is recorded in
  [`docs/external/source-decisions-phase3-2026-08-19.md`](../../docs/external/source-decisions-phase3-2026-08-19.md).

## Freeze guard

`tests/test_crosswalk.py::test_repository_crosswalk_is_frozen` loads this
CSV and asserts the freeze invariants: at least 20 rows, no `EXAMPLE_`
names, every row reviewed with the frozen reviewer and date, unique mapping
keys, no name-only merges, required official identifiers present, and an
`https://` official `source_url` on every row.
