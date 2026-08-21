# External Data Collection and Neo4j Ingestion Plan

| Field | Value |
|---|---|
| Status | **Active** — execution plan and progress source of truth |
| Deadline | 2026-08-30 (hard) |
| Data reference snapshot | 2026-07-11 |
| Backfill window | 2026-01-11 → 2026-07-11 |
| Excluded scope | Investment recommendation and suitability judgment |

## Authoritative references

| Reference | Annotation |
|---|---|
| `docs/contest_req.md` | Contest interpretation and target behavior; not implementation status. |
| `docs/current-data-capabilities.md` | Current XLSX/graph capability baseline and sample-question answerability decisions. |
| `docs/external-data-plan.md` | Planned official sources, required fields, and ontology modules. |
| `docs/external-sources-decision.md` | Phase 3 D+1 stop/go decision record with official source URLs. |
| `docs/data-loading.md` | Reproducible load record, environment, commands, and validation totals. |
| `docs/graph-model-guide.md` | Implemented nodes, relationships, mappings, and limitations. |
| `.sisyphus/plans/external-data-tailscale-neo4j.md` | Planning archive (rev 2). Local-only, not committed. |

Momus review round 2 verdict: **OKAY** (recommendation scope excluded from the
review).

## Goals

Extend the financial-product graph with external evidence so the three contest
example questions become answerable as **checked Cypher golden tests with
provenance**:

1. Cambricon appearing in China-semiconductor ETFs.
2. Six-month aerospace-theme connection history.
3. The largest ETF holding an EcoPro subsidiary, with its risk factors.

Every loaded fact carries source, retrievedAt, checksum, and evidence-basis
metadata; all loads are idempotent and restartable; amendments append new dated
assertions instead of overwriting; answer-visible evidence stays inside the
backfill window (cutoff freeze 2026-07-11).

## Non-goals

- No natural-language planner, DSL compiler, or evaluation HTTP API this cycle.
- No investment recommendation, suitability judgment, personalized advice, or
  "best product" output. Objective filtering and ranking by an explicitly
  requested metric stay in scope.
- No customer profiles, risk tolerances, or recommendation scoring.
- No real-time/intraday data; no full XBRL semantics (`reporting.ttl` excluded).
- One holdings source per market; no second vendors this cycle.
- No embeddings; rule-based passage anchoring only.
- Scheduler limited to a catch-up script; no orchestrator.

## Security and secret rules

1. Never place API keys, passwords, or SSH keys in chat, source code, plan
   files, logs, or committed files.
2. The OpenDART key exposed in chat must be revoked; the replacement goes only
   into the local git-ignored `.env`, never transmitted via chat.
3. Runtime secrets live only in `.env`: `OPENDART_API_KEY`, `NEO4J_URI`,
   `NEO4J_USER`, `NEO4J_PASSWORD`, `MIRAE_RAW_REMOTE` (placeholders in
   `.env.example`).
4. Run `scripts/secret_scan.sh` before every commit; abort when required
   secrets are absent; never print secret values.

## Source decisions (Phase 3 D+1, decided 2026-08-19)

| Source path | Decision |
|---|---|
| KRX automated basket/PDF/API acquisition | **NEEDS-CONTRACT** — no scraping, automation, or redistribution until written approval exists. |
| Korean manager-published holdings/baskets | **GO** (fallback path; snapshots labeled `evidenceBasis="manager_published"`). |
| SEC Form N-PORT public data sets | **GO** (identifying User-Agent, ≤10 requests/second). |

Official reference URLs and the target product universe remain in
`docs/external-sources-decision.md`. The fallback path proceeds regardless of
KRX approval status; only a recorded written approval flips KRX to GO.

## Work checklist

### Phase 0 — kickoff and network route (blocked on inputs)

- [x] Secret hygiene: `.env.example` placeholders, `var/` ignored, secret
      scanner passes on tracked files.
- [x] `scripts/connect_check.py` written (driver TLS + read/write probe against
      `neo4j+s://neo4j-2.yeongmin.net:443`).
- [x] `scripts/transfer_raw.py` written (rsync + sha256 verification).
- [ ] Exposed OpenDART key revoked and replaced by user (into `.env` only).
- [ ] Live proxy probe: `connect_check.py` exits 0 (needs `NEO4J_PASSWORD`).
- [ ] rsync round-trip with matching checksums (needs SSH host/user/key).

### Phase 1 — ingestion framework skeleton

- [x] `src/mirae_asset_graph/ingest/` package: adapter base
      (discover → fetch → normalize; adapters never import the Neo4j driver),
      manifest model, watermark/catch-up computation.
- [x] `ingest/graph_loader.py`: deterministic URIs, MERGE upserts
      (batch ≤500), provenance nodes `ExternalSource`/`ExternalArtifact`/
      `IngestionRun`.
- [x] Ontology modules `portfolio.ttl`, `corporate.ttl`, `disclosure.ttl`;
      `ONTOLOGY_MODULES` order `common, bond_kr, etf_kr, etf_gl, fund_pub,
      portfolio, corporate, disclosure`.
- [x] `validate()` blocking flag `--fail-on-validation-error` (nonzero exit on
      duplicate URIs or unlinked non-rejected records).
- [x] Fixture tests: watermark (offline), idempotency/resume (env-gated on
      `MIRAE_TEST_NEO4J_URI`). (commit `065c37d`)

### Phase 2 — identity crosswalks

- [x] `data/crosswalks/contest_entities.csv` template + identifier-based
      loader mapping + `tests/test_crosswalk.py` name-merge guard.
      (commit `7657b24`)
- [x] Crosswalk frozen with real entities: Cambricon, EcoPro family, US
      China-semiconductor ETF set, KR aerospace/semiconductor ETF set.
      21 reviewed rows, official identifiers only; unverified ISINs
      deliberately left as exchange/regulator codes; identity evidence
      only, not holdings/control evidence. (commit `4f313e1`)

### Phase 3 — ETF holdings

- [x] D+1 license stop/go decision recorded in
      `docs/external-sources-decision.md`. (commit `a6acdb5`)
- [x] Shared `HoldingsRecord` normalized contract + JSONL I/O + loader
      payload. (commit `6602350`)
- [x] Reviewed identifier resolver: source ISIN first, reviewed ISIN
      crosswalk second, unresolved otherwise; no name matching.
      (commit `4a2e7d8`)
- [x] `nport` adapter: public quarterly XML fetch with atomic raw caching,
      identifying User-Agent and ≤10 requests/second default rate policy,
      retry with backoff, namespace-insensitive XML parser, strict
      cutoff/report-date filtering, normalized `HoldingsRecord` output,
      quarantine for unresolved/invalid positions. (commit `3c1be81`)
- [x] Support: `Adapter.normalize` contract generalized to
      `normalize(target, raw, output) -> SourceResult` shared across
      adapters; LSP diagnostics report 0 errors. (commit `fbfe3c3`)
- [x] `kr_basket` adapter: manager-published basket CSV (UTF-8/CP949) and
      XLSX, reported or derived weights, reviewed identifier resolution with
      quarantine for unresolved positions, PDF deliberately unsupported.
      (commit `3071dd7`)
- [ ] `PortfolioSnapshot`/`HoldingPosition` graph model per asOf;
      benchmark-constituent fallback labeled per snapshot.
- [ ] Backfill runner for 2026-01-11 → 2026-07-11, monthly where published;
      watermarks per `(source, window_date)`.

### Phase 4 — corporate control (OpenDART)

- [ ] Replacement OpenDART key available in `.env`.
- [ ] `corp_code` sync (API if key arrived, else CSV) and
      consolidated-subsidiary/governance section extraction.
- [ ] `CorporateRelationshipAssertion` nodes with ownership %, control basis,
      validity dates, filing provenance.
- [ ] Manual-official-download fallback if key late, recorded as
      `retrieval_method="manual_official"`.

### Phase 5 — disclosures and risk passages

- [ ] Prospectus/annual-report acquisition for question-3 candidates plus the
      AUM leader.
- [ ] Pipeline: acquisition → parse → anchor (document/section/page/char
      offsets) → quality checks.
- [ ] `DisclosureDocument`/`DocumentSection`/`EvidencePassage`; question-3
      end-to-end with one declared AUM metric/date/currency.

### Phase 6 — aerospace theme history

- [ ] Controlled theme vocabulary (aerospace/defense).
- [ ] `ThematicAssociation` assertions derived only from dated snapshots, with
      rule version and confidence.
- [ ] Coverage rule: ≥4 monthly in-window snapshots → `answered`; 1–3 →
      `partial`; 0 → `unsupported`. No inference from product names.

### Phase 7 — tests and ops

- [ ] Golden tests `tests/golden/test_q1_cambricon.py`,
      `test_q2_aerospace.py`, `test_q3_ecopro.py` with expected fixtures.
- [ ] Catch-up script `scripts/collect.py --catch-up`.
- [ ] Runbook-lite `docs/ops-runbook.md`.

## Current blockers

| Blocker | Missing input | Unblocks |
|---|---|---|
| Replacement OpenDART key | User stores new key in `.env` (never chat) | Phase 4 control ingestion |
| `NEO4J_PASSWORD` | Local `.env` entry | Live proxy probe, remote graph loads |
| `MIRAE_RAW_REMOTE` + SSH key | Tailscale host/user/key details | rsync artifact transfer |
| `xlsx_data/` absent locally | Four source XLSX snapshots | Full local reloads (git-ignored) |

Credential-independent work (crosswalk freeze, adapters, tests) continues
despite these blockers; no remote writes or API calls happen until the inputs
arrive.

## Verification commands

```bash
bash scripts/secret_scan.sh             # secret scan: OK
uv run pytest                           # 84 passed / 2 skipped at HEAD
uv run python -m compileall src         # byte-compile check
uv run python scripts/connect_check.py  # blocked until NEO4J_PASSWORD
uv run python scripts/transfer_raw.py   # blocked until SSH inputs
```

## Progress log

All commits below are verified on `origin/main`.

| Date | Commit | Summary | Evidence | Pushed |
|---|---|---|---|---|
| 2026-08-19 | `065c37d` | External ingestion skeleton: `ingest` package, ontology modules, ops scripts, fixture tests. | pytest 5 passed / 2 skipped; secret scan OK | Yes |
| 2026-08-19 | `7657b24` | Crosswalk loader with name-merge guard; secret scanner self-match fixed and canary-verified. | pytest 11 passed / 2 skipped | Yes |
| 2026-08-21 | `8a3659c` | Secret scanner distinguishes environment credentials (`scripts/secret_scan.sh` only). | secret scan OK at HEAD; pytest 11 passed / 2 skipped | Yes |
| 2026-08-21 | `a6acdb5` | Phase 3 D+1 stop/go decision recorded in `docs/external-sources-decision.md` (docs-only). | No tests applicable (no code change); secret scan OK | Yes |
| 2026-08-21 | `4f313e1` | Freeze reviewed contest entity crosswalk. | test_crosswalk 7 passed; full pytest 12 passed / 2 skipped; secret scan OK | Yes |
| 2026-08-21 | `6602350` | Add normalized holdings record contract. | records/resolver stage 36 passed; full pytest 48 passed / 2 skipped | Yes |
| 2026-08-21 | `4a2e7d8` | Add reviewed identifier resolver. | full pytest 48 passed / 2 skipped; secret scan OK | Yes |
| 2026-08-21 | `3c1be81` | Add SEC N-PORT holdings adapter. | nport 18 passed; full pytest 66 passed / 2 skipped; compileall and secret scan OK | Yes |
| 2026-08-21 | `fbfe3c3` | Generalize adapter normalization contract. | targeted 36 passed; full pytest 84 passed / 2 skipped; LSP 0 errors | Yes |
| 2026-08-21 | `3071dd7` | Add Korean manager basket adapter. | basket 18 passed; full pytest 84 passed / 2 skipped; compileall and secret scan OK | Yes |

Dates are commit author dates from `git log`. 2026-08-21 entries reflect the
actual git timestamps of `8a3659c` and `a6acdb5`, not local clock assumptions.

## Next execution order

1. Implement the ingestion runner/backfill integrating the N-PORT and
   manager-basket adapters over the completed shared contracts
   (`HoldingsRecord` normalized contract, the reviewed identifier resolver,
   the generalized `Adapter.normalize` contract, and the adapters
   themselves) (credential-independent).
2. Run proxy/rsync probes when `NEO4J_PASSWORD` and SSH inputs arrive.
3. OpenDART control ingestion for the EcoPro family (or the
   manual-official fallback).
4. Disclosure passages, theme history, and golden tests for questions 1–3.

## Commit and push protocol

After each logical work unit:

1. Update this plan's checklist and progress log — included in the same
   logical commit where possible.
2. Run the unblocked verification commands above.
3. Commit atomically with a focused message.
4. Push to `origin/main`.
