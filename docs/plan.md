# Authoritative Revised Execution Plan

| Field | Value |
|---|---|
| Status | **Active** — execution plan and progress source of truth |
| Contest priority | Hidden-evaluation API correctness, evidence quality, latency, and proposal documentation |
| Historical baseline | Completed local XLSX/Neo4j foundation used the organizer files dated **2026-07-11** and the external-ingestion policy window **2026-01-11 → 2026-07-11** |
| Refreshed organizer distribution | Announced as **4 data tables + 4 schema files**; domestic data through business date **2026-08-22** and overseas data through Korea time **2026-08-23** |
| Refreshed local status | **Pending** — `xlsx_data/` is absent locally, so the refreshed files have not been loaded, diffed, or measured |
| Excluded scope | Investment recommendation, suitability judgment, customer profiling, and recommendation scoring |

## Authoritative references

| Reference | Use |
|---|---|
| `docs/README.md` | Documentation index, authority order, and status map. |
| `docs/requirements/contest.md` | Organizer requirement interpretation, API shape, scoring, and proposal expectations; not implementation status. |
| `docs/evaluation/historical-data-capabilities-2026-07-11.md` | Historical 2026-07-11 XLSX/graph capability baseline and sample-question decisions. |
| `docs/evaluation/historical-sample-questions-regression.md` | Regression checklist for historical sample/golden cases. |
| `docs/architecture/query-dsl-spec.md` and `docs/artifacts/query-dsl.schema.json` | Proposed bounded read-only DSL; compiler/API not yet implemented. |
| `docs/data/loading-record.md` | Verified local load totals and KSTR staging proof. |
| `docs/architecture/graph-model-guide.md` | Implemented nodes, relationships, mappings, and limitations. |
| `docs/external/external-data-plan.md` | External enrichment design and source-trust policy. |
| `docs/external/source-decisions-phase3-2026-08-19.md` | Phase 3 D+1 source decision record. |

Momus review round 2 verdict remains **OKAY** for the prior ingestion plan
(recommendation scope excluded). This revised plan supersedes the old
sample-question-led deadline plan while preserving completed implementation
history.

## Strategic goal

Deliver a contest-safe financial-product answering service that can answer each
single hidden question in one turn when evidence is sufficient, return supported
partial facts when only some clauses are supported, and abstain safely when a
question is impossible or under-evidenced. The execution focus is now:

1. refreshed official data intake and reload;
2. explicit product-family metric capability and eligibility rules;
3. bounded planner/DSL execution and `GET /answer` evaluation API;
4. cross-product comparisons only over metric-compatible cohorts;
5. selective external enrichment for holdings, corporate control, disclosures,
   and missing-value support; and
6. hidden-evaluation QA, deployment, and technical proposal documentation.

The three previously emphasized example questions are now **regression/golden
cases**, not the plan's controlling goals. No additional public examples are
expected, so coverage must be driven by a query-capability test matrix.

## Historical baseline and superseded assumptions

- The 2026-07-11 data reference snapshot and 2026-01-11 → 2026-07-11 backfill
  window are a **historical baseline for completed work**, not the current
  authoritative contest data snapshot.
- The older non-goal “no natural-language planner, DSL compiler, or evaluation
  HTTP API this cycle” is superseded. Those items are now P0.
- The older hard 2026-08-30 internal deadline is superseded by the hidden
  evaluation/deployment priorities in this plan.
- Internal/vendor codebook acquisition is **not** a blocker or plan dependency.
  Opaque source codes must be preserved raw and never inferred. Comparisons that
  require a scale, such as rating-grade ordering, remain unsupported unless a
  separately trusted authoritative scale is available.

## Non-goals and guardrails

- No personalized advice, suitability judgment, recommendation scoring, or
  customer profile reasoning. Objective filtering/ranking by an explicitly
  requested metric is allowed when the metric is supported.
- No silent substitution across metrics, product families, dates, currencies, or
  evidence types.
- No inference of holdings, theme history, benchmark constituents, subsidiaries,
  or corporate relations from a product name. Product-name parsing is allowed
  only for candidate/search classification and must be labeled as such.
- No claim that refreshed files were loaded or measured until `xlsx_data/` is
  restored and the reload/diff commands succeed.

## Data and evidence rules

### Source trust and provenance

1. Prefer organizer files, regulators, exchanges, official filing repositories,
   index administrators, and fund managers over aggregators.
2. Preserve immutable raw artifacts with source URL/path, retrievedAt,
   published/effective dates where known, checksum, parser version, and row/fact
   or passage lineage.
3. Later corrections append dated assertions; they do not overwrite historical
   evidence silently.
4. External enrichment may fill missing fields only when source, method, and
   conflict policy are recorded. When external and organizer values conflict,
   keep both, prefer organizer data for organizer-defined evaluation fields, and
   disclose the conflict where answer-visible.

### Raw-layer preservation vs answer-layer eligibility

- **Raw layer:** preserve blanks, zeroes, nulls, opaque codes, and suspicious
  values exactly with provenance.
- **Answer layer:** queried metrics such as return, fee, tracking error, and
  buyable quantity must exclude zero/null values when the field semantics or
  observed population indicate “unavailable/no basis” rather than a real
  measured value. The answer must disclose the exclusion rule and denominator.
- Blank means not supplied. Zero is not automatically false, but zero is also not
  automatically a valid measurement for ranking/comparison when the entire field
  is non-informative.

## Single-turn answer contract

Evaluation calls are one turn. The service must not depend on follow-up
clarification.

| Situation | Required behavior |
|---|---|
| Defensible interpretation exists | Infer explicit conditions, execute them, and disclose assumptions. |
| Partially supported question | Return supported parts with evidence and list unsupported clauses. |
| Ambiguous but bounded | Choose a conservative interpretation only if safe; otherwise abstain with a suggested reformulation. |
| Impossible/insufficient question | Return an unanswerable response in the same API schema; do not fabricate. |
| Exact entity absent | Report snapshot-scoped empty/no exact match and optional labeled near matches. |

`think_trace` must be a safe audit trace of routing/retrieval/evidence checks,
not hidden chain-of-thought or raw secrets.

### Internal status to API outcome mapping

| Internal DSL/runtime status | User-facing/API outcome | Endpoint behavior |
|---|---|---|
| `ok` | `answered` | HTTP 200; return grounded answer with retrieved context and evidence. |
| `partial` | `partial` | HTTP 200; answer supported clauses and state missing/unsupported clauses. |
| `empty` | `empty` | HTTP 200; state no exact match/result within the active snapshot or evidence boundary. |
| `invalid` | `invalid` | HTTP 200; explain the validation problem safely and, when possible, valid values/rules. |
| `unsupported` | `unsupported` | HTTP 200; state that the requested metric/relation/source is unsupported. |
| `insufficient_evidence` | `unanswerable` | HTTP 200; state that evidence is insufficient and do not fabricate. |
| `ambiguous` | `ambiguous` | HTTP 200; either use a disclosed conservative assumption or abstain with suggested reformulation. |
| `timeout` | `unanswerable` | HTTP 200; state timeout/limited execution safely without partial hidden errors. |
| `error` | `unanswerable` | HTTP 200; expose only a safe failure message, never database/model errors or stack traces. |

## Evaluation API and runtime requirements (P0)

- Implement `GET /answer` with required query parameters `question_id` and
  `question`.
- Preserve the organizer API contract: response `Content-Type` must be
  `application/json; charset=utf-8`; no authentication header is required or
  expected; no POST body is accepted; unknown/unexpected query parameters must
  not cause HTTP 500.
- Echo `question_id` and `question` unchanged in every response.
- Always return HTTP 200 with the same JSON schema for answered, partial, empty,
  invalid, unsupported, and unanswerable responses.
- Response fields must include at least `question_id`, `question`,
  `retrieved_context`, `think_trace`, and `answer`.
- Natural-language planning must compile only to a bounded, read-only DSL; the
  executor must use static entity/field/relation maps, parameterized Cypher,
  fixed result/page/depth/timeout caps, and read-only transactions.
- Evidence checks are mandatory before answer generation. Unsupported fields,
  incompatible metrics, missing provenance, timeout, or validation failure must
  produce safe abstention/partial output rather than a database or model error.
- Add API schema tests, organizer-contract tests (content type, GET-only/no auth,
  no POST-body dependency, unexpected-parameter safety), golden/regression
  tests, timeout tests, and latency/concurrency tests. The contest target is
  per-question latency; design for the published ≤60s ceiling and measure
  p50/p95 under concurrent evaluation.

## Product-family metric capability registry (P0)

Create a versioned registry used by the planner and answer validator. Each entry
must record at minimum: registry version, metric key, product family, source
field, eligibility predicate, exclusion reason, denominator basis, as-of basis,
unit, currency, compatible cohort key, and evidence requirement. It records which
metric is supported for each product family, source field, unit, raw-value
eligibility, date semantics, and allowed comparison cohorts.

Initial required entries:

| Product family | Metric | Source field | Status | Rule |
|---|---|---|---|---|
| Domestic ETF/ETN | 1-year return | `du_er_1y` | Supported when populated and eligible | Use as `fund_metric.return_1y`; exclude null/no-basis values and cite rows/asOf. |
| Public fund | 1-year return | `fd_yr1_ern_r` | Supported when populated and eligible | Use as `fund_metric.return_1y`; compare only with compatible public-fund or explicitly union-compatible cohorts. |
| Overseas ETF/ETN | 1-year return | — | **Unsupported/excluded** | The current overseas master has `du_er_1d` only; do **not** substitute `du_er_1d` for a 1-year return. Explain the exclusion. |
| Domestic bond | Buyable quantity | `BUYABLE_QUANTITY` | Supported for positive available quantities | Exclude null/zero when answering “currently buyable/available quantity” filters; disclose sparse coverage. |
| Domestic ETF/ETN | Fee | `cu_charge_rt` | Supported only for populated eligible rows | Exclude null; disclose sparse population. |
| Domestic ETF/ETN | Tracking error | `du_chas_errt` | Currently non-informative in historical baseline | Preserve raw `0.00`; do not rank/explain tracking-error risk from all-zero values without refreshed/authoritative evidence. |

Cross-product behavior is a required capability design, but this plan does not
invent an organizer answer to the unanswered channel question. Cross-product
comparisons must union only metric-compatible cohorts, keep per-family
denominators, and disclose excluded product families/metrics.

## Query-capability test matrix

The hidden set may exercise any combination below. Each row needs planner,
DSL/API, evidence, and abstention tests.

| Capability | Required behavior |
|---|---|
| Exact lookup | ISIN/ticker/name lookup with row provenance and labeled near matches only. |
| Numeric filter/rank | Metric registry validation, zero/null eligibility, stable sorting, denominator disclosure. |
| Cross-product comparison | Union only compatible product families and explain exclusions. |
| Temporal/history query | Use repeated observations only; abstain when only one snapshot exists. |
| Holdings query | Require dated portfolio/basket/N-PORT evidence; no product-name inference. |
| Corporate-control query | Require sourced parent/subsidiary/control assertion; investment exposure alone is not control. |
| Theme query | Require controlled theme vocabulary and evidence-backed dated association. |
| Disclosure/risk query | Require addressable source document/passages with section/page/offset provenance. |
| Code/scale comparison | Require trusted authoritative scale; otherwise exact-match or unsupported only. |
| Unanswerable/empty | Return HTTP 200 schema with clear insufficiency/empty explanation. |

The historical sample questions in `docs/evaluation/historical-sample-questions-regression.md` must remain as
golden regression cases, including unsupported and empty outcomes.

## Security and secret rules

1. Never place API keys, passwords, or SSH keys in chat, source code, plan files,
   logs, or committed files.
2. The user explicitly authorized the current local OpenDART key on 2026-08-24.
   It remains only in the git-ignored `.env` and is never transmitted via chat;
   rotation is still recommended because the key was previously exposed.
3. Runtime secrets live only in `.env`: `OPENDART_API_KEY`, `NEO4J_URI`,
   `NEO4J_USER`, `NEO4J_PASSWORD`, `MIRAE_RAW_REMOTE` (placeholders in
   `.env.example`).
4. Run `scripts/secret_scan.sh` before every commit; abort when required secrets
   are absent; never print secret values.

## Source decisions preserved from Phase 3 D+1

| Source path | Decision |
|---|---|
| KRX automated basket/PDF/API acquisition | **NEEDS-CONTRACT** — no scraping, automation, or redistribution until written approval exists. |
| Korean manager-published holdings/baskets | **GO** fallback path; snapshots labeled `evidenceBasis="manager_published"`. |
| SEC Form N-PORT public data sets | **GO** with identifying User-Agent and ≤10 requests/second. |

The fallback path proceeds regardless of KRX approval status; only recorded
written approval flips KRX to GO.

## Historical implementation record (verified; preserve)

### Phase 0 — kickoff and network route

- [x] Secret hygiene: `.env.example` placeholders, `var/` ignored, secret
      scanner passes on tracked files.
- [x] `scripts/connect_check.py` written (driver TLS + read/write probe against
      `neo4j+s://neo4j-2.yeongmin.net:443`).
- [x] `scripts/transfer_raw.py` written (rsync + sha256 verification).
- [x] Current local OpenDART key explicitly authorized by the user on
      2026-08-24 (`.env` only; value never recorded).
- [ ] Live proxy probe exits 0 (needs `NEO4J_PASSWORD` / remote authorization).
- [ ] rsync round-trip with matching checksums (needs SSH host/user/key).

### Phase 1 — ingestion framework skeleton

- [x] `src/mirae_asset_graph/ingest/` package: adapter base
      (discover → fetch → normalize; adapters never import the Neo4j driver),
      manifest model, watermark/catch-up computation.
- [x] `src/mirae_asset_graph/ingest/graph_loader.py`: deterministic URIs, MERGE upserts
      (batch ≤500), provenance nodes `ExternalSource`/`ExternalArtifact`/
      `IngestionRun`.
- [x] Ontology modules `portfolio.ttl`, `corporate.ttl`, `disclosure.ttl`;
      `ONTOLOGY_MODULES` order `common, bond_kr, etf_kr, etf_gl, fund_pub,
      portfolio, corporate, disclosure`.
- [x] `validate()` blocking flag `--fail-on-validation-error`.
- [x] Fixture tests: watermark (offline), idempotency/resume (env-gated on
      `MIRAE_TEST_NEO4J_URI`). (commit `065c37d`)

### Phase 2 — identity crosswalks

- [x] `data/crosswalks/contest_entities.csv` template + identifier-based loader
      mapping + `tests/test_crosswalk.py` name-merge guard. (commit `7657b24`)
- [x] Crosswalk frozen with real entities: Cambricon, EcoPro family, US
      China-semiconductor ETF set, KR aerospace/semiconductor ETF set. 21
      reviewed rows, official identifiers only; unverified ISINs deliberately
      left as exchange/regulator codes; identity evidence only, not
      holdings/control evidence. (commit `4f313e1`)

### Phase 3 — ETF holdings foundation

- [x] D+1 license stop/go decision recorded in
`docs/external/source-decisions-phase3-2026-08-19.md`. (commit `a6acdb5`)
- [x] Shared `HoldingsRecord` normalized contract + JSONL I/O + loader payload.
      (commit `6602350`)
- [x] Reviewed identifier resolver: source ISIN first, reviewed ISIN crosswalk
      second, unresolved otherwise; no name matching. (commit `4a2e7d8`)
- [x] `nport` adapter: public quarterly XML fetch with atomic raw caching,
      identifying User-Agent, ≤10 requests/second default rate policy, retry
      with backoff, namespace-insensitive XML parser, strict cutoff/report-date
      filtering, normalized `HoldingsRecord`, quarantine. (commit `3c1be81`)
- [x] `Adapter.normalize` contract generalized to
      `normalize(target, raw, output) -> SourceResult`; LSP diagnostics reported
      0 errors. (commit `fbfe3c3`)
- [x] `kr_basket` adapter: manager-published basket CSV (UTF-8/CP949) and XLSX,
      reported or derived weights, reviewed identifier resolution, quarantine;
      PDF deliberately unsupported. (commit `3071dd7`)
- [x] Shared `IngestRunner`: discover/fetch/normalize orchestration,
      as-of/source-document shards capped at 500 rows, append-only manifest,
      loaded-batch resume skip, failure continuation with sanitized errors, and
      full-SHA256 document identity with 32-bit chunk ordinal. (commit `61cc013`)
- [x] `PortfolioSnapshot`/`HoldingPosition` load payload preserves canonical
      evidence fields and source-document-aware identities so amendments remain
      distinct and exact reruns remain idempotent.
- [x] CLI foundation enforces the historical 2026-01-11 → 2026-07-11 window and
      publication cutoff, separates `collect` / `verify-collection` / `load`,
      verifies artifacts offline before driver creation, and gates staging
      writes with explicit environment plus CLI authorization. Production
      loading remains blocked pending remote authorization/staging receipt.
- [x] First reviewed real target configuration: KSTR SEC N-PORT accession
      `0002048251-26-004699` (`asOf=2026-03-31`, filed 2026-05-29). The
      immutable 68,120-byte XML normalized to 51 positions with zero quarantines
      and loaded idempotently into disposable local Neo4j staging.
- [ ] Benchmark-constituent fallback modeling and per-snapshot labeling remain
      pending; the holdings foundation does not implement that fallback.
- [ ] Expand reviewed target set and coverage beyond the first KSTR quarter;
      synthetic `example.invalid` fixtures remain test-only.

### Phase 4+ historical unfinished items

- [ ] OpenDART `corp_code` sync and consolidated-subsidiary/governance section
      extraction.
- [ ] `CorporateRelationshipAssertion` nodes with ownership %, control basis,
      validity dates, and filing provenance.
- [ ] Prospectus/report acquisition, parse, section/page/offset anchoring, and
      risk-passage graph load.
- [ ] Controlled theme vocabulary and evidence-backed dated theme assertions.
- [ ] Golden tests for the historical example questions.

The SEC KSTR source was fetched read-only and loaded only into disposable local
staging. No Yeongmin Neo4j write or OpenDART call has occurred.

## Current blockers

| Blocker | Missing input | Unblocks |
|---|---|---|
| Refreshed organizer files absent locally | `xlsx_data/` containing 4 refreshed data tables + 4 schema files | R1 intake, diff, reload, refreshed metric coverage measurement |
| Yeongmin Neo4j remote credentials/authorization | Explicit remote URI/database/user/password and post-staging approval | Remote graph validation and deployment connection |
| `MIRAE_RAW_REMOTE` + SSH key | Tailscale host/user/key details | rsync raw-artifact transfer |

OpenDART key handling is factual: the local key is present only in `.env` and
authorized for use, but no OpenDART call has yet occurred. The prior
OpenCode/Gemini process-route issue is not an execution blocker for this plan.

## Revised next execution order

### R0 — plan/rules baseline (P0)

- [x] Rewrite `docs/plan.md` to this authoritative revised plan.
- [ ] Convert this plan's rules into machine-enforced registries/checklists:
      metric capability, zero/null eligibility, answer outcomes, and safe audit
      trace requirements.

Scheduling note: while the refreshed organizer files remain absent, R0, R2, and
R3 may proceed against the historical 2026-07-11 baseline and fixtures. They
must not claim refreshed coverage, row counts, metric population, or answerability
until R1 receives, diffs, reloads, and validates the refreshed files.

### R1 — refreshed official data intake, diff, and reload (P0)

- [ ] Restore the organizer distribution locally: 4 data tables + 4 schema files.
- [ ] Record filenames, checksums, declared date coverage, row counts, and schema
      diffs against the 2026-07-11 historical baseline.
- [ ] Reload into local Neo4j, validate graph totals, and update capability
      coverage without claiming success before commands pass.
- [ ] Preserve both historical and refreshed source artifacts immutably.

### R2 — capability/eligibility registry (P0)

- [ ] Implement product-family metric registry for returns, fees, tracking error,
      buyable quantity, AUM/net assets, dates, currencies, and evidence rules.
- [ ] Encode unsupported overseas ETF 1-year return and the no-`du_er_1d`
      substitution rule.
- [ ] Encode raw preservation vs answer eligibility for zero/null values.
- [ ] Add planner-facing explanations for excluded product families and
      unsupported codebook/scale comparisons.

### R3 — query runtime and evaluation API (P0)

- [ ] Implement single-turn intent/entity/condition extraction that records
      assumptions and never waits for follow-up.
- [ ] Implement bounded read-only DSL semantic validation and Cypher execution.
- [ ] Implement `GET /answer` with echo fields, same HTTP 200 schema for
      unanswerable responses, timeout handling, safe errors, and safe audit
      trace.
- [ ] Add evidence sufficiency checks before final answer rendering.

### R4 — cross-product execution (P0/P1)

- [ ] Execute cross-product filters/rankings by unioning only metric-compatible
      cohorts.
- [ ] Return per-family coverage/denominator and explain excluded families,
      metrics, dates, or currencies.
- [ ] Add regression cases for domestic ETF vs public fund 1-year return and
      overseas ETF exclusion.

### R5 — selective external enrichment (P1)

- [ ] Add only enrichment needed by hidden-eval risk: holdings/control/disclosure
      facts with immutable raw artifacts and conflict policy.
- [ ] Use SEC N-PORT and manager-published baskets under existing source
      decisions; do not automate KRX without written approval.
- [ ] Use OpenDART with the authorized local key for corporate-control evidence,
      preserving filings and extraction basis.
- [ ] Add missing-value enrichment documentation: what was collected, how it was
      cleaned, where it is used, and when it is excluded.

### R6 — hidden-eval QA, deployment, and proposal (P0/P1)

- [ ] Build a query-capability golden matrix covering answerable, partial, empty,
      invalid, unsupported, and timeout cases.
- [ ] Test API schema, evidence trace, latency, and concurrent requests.
- [ ] Deploy reproducibly with secrets externalized and health checks.
- [ ] Write the proposal/report sections: collection/ETL, ontology, retrieval
      logic, answerability/abstention, missing-value enrichment, evaluation
      procedure, limitations, and extension path.

## Verification commands

Commands below are the verification set; only the historical results listed in
the progress log are known to have passed. Future API/schema/golden/latency
checks must be added and run when implemented.

```bash
# current
bash scripts/secret_scan.sh                         # existing secret scan
uv run pytest                                       # existing test suite; historical baseline: 183 passed / 2 skipped
uv run python -m compileall src                     # byte-compile check

# blocked until refreshed local data/graph is available
uv run mirae-graph validate                         # graph validation after local reload

# blocked until external credentials/inputs are available
uv run python scripts/connect_check.py              # blocked until Neo4j credentials/authorization
uv run python scripts/transfer_raw.py               # blocked until SSH inputs

# future, after corresponding DSL/API/golden/latency tests are implemented
uv run pytest tests/test_query_dsl*.py              # future DSL/schema tests
uv run pytest tests/golden/                         # future sample + capability golden tests
uv run pytest tests/test_answer_api*.py             # future GET /answer schema/error tests
uv run pytest tests/test_answer_latency*.py         # future timeout/latency/concurrency tests
```

## Progress log

All commits below are verified on `origin/main`.

| Date | Commit | Summary | Evidence | Pushed |
|---|---|---|---|---|
| 2026-08-19 | `065c37d` | External ingestion skeleton: `ingest` package, ontology modules, ops scripts, fixture tests. | pytest 5 passed / 2 skipped; secret scan OK | Yes |
| 2026-08-19 | `7657b24` | Crosswalk loader with name-merge guard; secret scanner self-match fixed and canary-verified. | pytest 11 passed / 2 skipped | Yes |
| 2026-08-21 | `8a3659c` | Secret scanner distinguishes environment credentials (`scripts/secret_scan.sh` only). | secret scan OK at HEAD; pytest 11 passed / 2 skipped | Yes |
| 2026-08-21 | `a6acdb5` | Phase 3 D+1 stop/go decision recorded in `docs/external/source-decisions-phase3-2026-08-19.md` (docs-only). | No tests applicable (no code change); secret scan OK | Yes |
| 2026-08-21 | `4f313e1` | Freeze reviewed contest entity crosswalk. | test_crosswalk 7 passed; full pytest 12 passed / 2 skipped; secret scan OK | Yes |
| 2026-08-21 | `6602350` | Add normalized holdings record contract. | records/resolver stage 36 passed; full pytest 48 passed / 2 skipped | Yes |
| 2026-08-21 | `4a2e7d8` | Add reviewed identifier resolver. | full pytest 48 passed / 2 skipped; secret scan OK | Yes |
| 2026-08-21 | `3c1be81` | Add SEC N-PORT holdings adapter. | nport 18 passed; full pytest 66 passed / 2 skipped; compileall and secret scan OK | Yes |
| 2026-08-21 | `fbfe3c3` | Generalize adapter normalization contract. | targeted 36 passed; full pytest 84 passed / 2 skipped; LSP 0 errors | Yes |
| 2026-08-21 | `3071dd7` | Add Korean manager basket adapter. | basket 18 passed; full pytest 84 passed / 2 skipped; compileall and secret scan OK | Yes |
| 2026-08-21 | `61cc013` | Add resumable holdings ingestion runner. | runner 22 passed; full pytest 106 passed / 2 skipped; compileall, secret scan, and LSP 0 errors | Yes |

Dates are commit author dates from `git log`. 2026-08-21 entries reflect the
actual git timestamps of `8a3659c` and `a6acdb5`, not local clock assumptions.

## Commit and push protocol

After each logical work unit:

1. Update this plan's checklist and progress log when implementation status
   changes.
2. Run the unblocked verification commands above.
3. Commit atomically with a focused message only when explicitly requested.
4. Push only when explicitly requested.
