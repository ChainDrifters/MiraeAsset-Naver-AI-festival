# Mirae Asset Financial Product Agent

Ontology-grounded financial-product retrieval for the Mirae Asset × Naver AI
Festival. The repository implements the **XLSX-to-Neo4j data and ontology
foundation** plus the credential-independent core of an **external-evidence
ingestion framework**. Live external backfill, corporate/disclosure/theme
evidence, the natural-language query service, and the answer-generation API
remain incomplete.

Current data boundary: the active organizer baseline is fixed at
**2026-07-11**. XLSX intake must use `data/1.금융상품` with an explicit
`--input-dir "data/1.금융상품"` on dry-run/load commands. Later organizer
announcements or files, including 2026-08-22/2026-08-23 refresh notices, are
superseded audit context only: they must never be loaded into the active graph
or used for active capability claims. See [`docs/plan.md`](docs/plan.md) and the
baseline evidence in
[`docs/evaluation/historical-data-capabilities-2026-07-11.md`](docs/evaluation/historical-data-capabilities-2026-07-11.md)
before claiming that a question is answerable.

## Implementation checklist

Checked items are present in this repository. Unchecked items are required or
planned work; their order roughly follows implementation priority.

### Data and graph foundation

- [x] Implement and historically verify loading for the four supplied XLSX
      datasets and their schema workbooks.
- [x] Preserve every nonblank source value with file/row provenance.
- [x] Build canonical bond, ETF, ETN, fund, unit, organization, benchmark,
      listing, offering, classification, and observation nodes.
- [x] Use deterministic URIs, constraints, indexes, idempotent upserts, and a
      malformed-row quarantine path.
- [x] Split the required ontology into `common.ttl`, `bond_kr.ttl`,
      `etf_kr.ttl`, `etf_gl.ttl`, and `fund_pub.ttl`.
- [x] Align the class hierarchy to selected FIBO concepts and load it through
      Neo4j neosemantics.
- [x] Provide dry-run, load, and graph-validation commands.
- [ ] Declare operational object/datatype properties formally in OWL.
- [ ] Add SHACL shapes and validation for graph structure, cardinality, values,
      dates, units, and provenance.
- [x] Record that internal vendor codebooks are unavailable and not a blocker;
      preserve opaque codes raw, and keep codebook-dependent ordering
      unsupported unless backed by a separately trusted scale.
- [x] Add a reviewed contest-entity identity crosswalk with strict identifier
      joins and a tested guard against name-only merges.
- [ ] Expand reviewed fund-family, organization, market, and identifier
      crosswalks beyond the contest entity set.
- [ ] Implement snapshot supersession, correction, disappearance, and deletion
      semantics for later XLSX loads.
- [x] Verify the fixed 2026-07-11 organizer baseline file set from
      `data/1.금융상품`: eight local files found, all four data/schema pairs match
      the 2026-07-11 declaration, data/schema column counts align, and raw data
      rows are 42,394 / 1,734 / 5,646 / 95,619.
- [x] Run the fixed-baseline dry-run with explicit
      `--input-dir "data/1.금융상품"`.
- [ ] Load the fixed baseline into Neo4j and validate graph totals; do not claim
      current graph readiness until this passes.

### External evidence and ontology enrichment

- [x] Implement the source-acquisition core: adapter contract, append-only run
      manifests, deterministic batches, checksums, retries, cutoff filtering,
      quarantine, offline artifact verification, and resumable loads.
- [x] Implement SEC N-PORT XML and Korean manager-published CSV/XLSX basket
      adapters with offline fixtures and source-specific access controls.
- [ ] Implement selective external target discovery and backfill according to R5
      query-capability gaps; the adapter's 2026-01-11 through 2026-07-11 window
      is a historical Phase-3 policy, not the current contest-wide data policy.
- [x] Add `portfolio.ttl` and normalized portfolio snapshot/holding loader
      conventions.
- [ ] Load production dated holdings/creation baskets and benchmark
      constituents with source-backed quantities, values, weights, currencies,
      and coverage records.
- [x] Add the `corporate.ttl` semantic module.
- [ ] Load sourced, time-bounded parent/subsidiary/control assertions with
      security-to-company mappings.
- [ ] Add `reporting.ttl` and conformant XBRL/iXBRL ingestion, preserving filing,
      taxonomy, concept, context, period, unit, dimensions, and amendments.
- [x] Add the `disclosure.ttl` semantic module.
- [ ] Load prospectuses/reports and addressable risk passages; document-vector
      indexing remains out of the contest-critical path.
- [ ] Add a controlled theme vocabulary, evidence-backed temporal theme
      associations, and repeated historical snapshots.
- [ ] Fetch authoritative fee, distribution, tracking-error, NAV/AUM, and FX
      data with comparable dates, currencies, and metric definitions.
- [ ] Use selective trusted external enrichment for holdings, corporate control,
      disclosures, and missing-value support only where query-capability gaps
      require it, with reportable source reliability, integrity, ETL, and use
      logic.
- [ ] Add jurisdiction adapters as coverage requires: OpenDART/KRX/KOFIA,
      SEC EDGAR/N-PORT, EDINET, ESEF national repositories, FCA/Companies House,
      and Chinese exchanges.

### Query service and agent

- [x] Specify the proposed read-only query DSL and JSON request schema.
- [x] Define `answered`, `partial`, `empty`, `invalid`, `unsupported`, and
      `ambiguous` answer outcomes.
- [ ] Implement semantic DSL validation and compilation to bounded Cypher.
- [ ] Implement a product-family metric capability/eligibility registry covering
      zero/null exclusion rules, compatible cohorts, date/unit/currency basis,
      and evidence requirements.
- [ ] Encode the overseas ETF 1-year-return exclusion: it is unavailable, must
      not be substituted with 1-day return, and may be excluded with explanation
      from cross-product 1-year-return answers.
- [ ] Implement exact entity resolution, alias handling, and clearly labeled
      near-match suggestions without silent substitution.
- [ ] Implement natural-language intent/entity extraction and query planning.
- [ ] Enforce the single-turn API contract: answer each request in one response,
      infer defensible bounded conditions, and abstain/unavailable safely when
      evidence is insufficient.
- [ ] Implement routing across the graph, an XBRL/numeric fact store, and the
      document index.
- [ ] Implement observation selection, temporal joins, ranking, currency
      normalization, and evidence merging.
- [ ] Execute cross-product filters/rankings only across metric-compatible
      cohorts, with per-family denominator and exclusion explanations.
- [ ] Implement evidence sufficiency checks and contest-safe abstention.
- [ ] Implement the evaluation HTTP API, response schema, audit trace, timeout,
      and error behavior.
- [ ] Integrate contest-compliant final answer generation with citations to
      source rows, facts, filings, or passages.

### Quality and delivery

- [x] Add unit tests for manifests, normalization, identity resolution,
      N-PORT parsing, manager baskets, and runner resume/chunk/failure behavior.
- [ ] Add semantic DSL validation tests.
- [x] Add environment-gated Neo4j integration tests for external-load
      idempotency and resume behavior.
- [ ] Add integration tests for provenance and query compilation.
- [ ] Build a query-capability golden matrix for answerable, partial, empty,
      invalid, unsupported, timeout, and unanswerable cases; keep historical
      sample questions as regression cases inside that matrix.
- [ ] Measure external-source coverage, freshness, corrections, and outage
      behavior.
- [ ] Meet the contest latency target and test concurrent evaluation requests.
- [ ] Add service observability, secrets handling, source-health reporting, and
      a reproducible production deployment.

Current test baseline: **203 passed and 2 environment-gated integration tests
skipped** without a live test Neo4j URI.

## Current external-ingestion status

The tracked execution source of truth is [`docs/plan.md`](docs/plan.md). Source
licensing and access decisions are recorded in
[`docs/external/source-decisions-phase3-2026-08-19.md`](docs/external/source-decisions-phase3-2026-08-19.md).

Implemented:

- a 21-row reviewed contest entity crosswalk for Cambricon, the EcoPro family,
  China-semiconductor ETF candidates, and Korean aerospace/semiconductor ETFs;
- a normalized `HoldingsRecord` contract and reviewed-identifier resolver that
  never joins by name;
- SEC N-PORT XML and Korean manager CSV/XLSX basket adapters with raw caching,
  retry/rate-limit policy, deterministic JSONL output, and quarantine;
- a resumable `IngestRunner` that shards by source document and as-of date,
  caps graph batches at 500 rows, and records append-only manifest state; and
- a production-safe `mirae-ingest` CLI that separates `collect`,
  `verify-collection`, and `load`; collection creates `READY` artifacts without
  importing Neo4j, while loading re-verifies them and requires explicit staging
  write authorization; and
- a reviewed real KSTR SEC N-PORT target (`2026-03-31`), with an immutable raw
  XML artifact, 51 verified normalized positions, zero quarantined positions,
  and a successful idempotent load into a disposable local Neo4j staging
  container; and
- secret scanning, proxy-connect checks, rsync/checksum transfer tooling, and
  203 passing offline tests.

Known blockers and unfinished work:

- the current local OpenDART key was explicitly authorized by the user on
  2026-08-24 and remains only in the git-ignored `.env`; rotation is still
  recommended because it was previously exposed;
- separate authorization and credentials are still required before loading the
  verified staging bundle into the Yeongmin Neo4j database;
- Tailscale SSH/rsync parameters are required for raw-artifact transfer;
- fixed-baseline Neo4j load and graph validation remain pending; and
- target coverage beyond the first KSTR N-PORT filing, OpenDART control
  ingestion, disclosure passages, theme history, and golden answerability tests
  are not implemented.

Investment recommendation, suitability judgment, customer profiling, and
recommendation scoring are explicitly out of scope. Objective filtering,
comparison, and ranking by a user-supplied metric remain in scope.

## Historical loaded dataset and graph

The row counts below are the fixed active baseline from the 2026-07-11 organizer
files. They are not later organizer refresh measurements. Baseline input
discovery found eight local files under `data/1.금융상품`; all four data/schema
pairs match the 2026-07-11 declaration, data/schema column counts align, and no
commit status for those local files is claimed here. Current fixed-baseline
Neo4j load and graph validation remain pending.

| Dataset | Source rows | Canonical result |
|---|---:|---|
| Domestic bonds | 42,394 | 42,394 bonds |
| Korean ETF/ETN | 1,734 | 1,202 ETFs and 532 ETNs |
| Overseas ETF/ETN | 5,646 | 5,537 ETFs and 59 ETNs |
| Public funds | 95,619 | 11,138 funds and 11,138 units; one malformed row rejected |
| **Total** | **145,393** | **145,392 linked source rows** |

Preserved historical graph totals include 17,877 funds, 17,877 fund units,
591 ETNs, 32,303 listings, and 67,825 observations, with no duplicate resource
URIs or unlinked non-rejected source rows.

The observations are point-in-time records from one historical load—not
per-product history. The local historical XLSX baseline does not include ETF
holdings, corporate-control relationships, sourced theme history, or prospectus
risk passages.

## Architecture

Current implementation:

```text
XLSX data + XLSX schemas + modular TTL
                    |
                    v
        Python normalization/loader
                    |
                    v
Neo4j: source -> canonical -> observation -> ontology
                    |
                    v
            validation + Cypher
```

Implemented external-ingestion path (coverage beyond the first KSTR target and
any Yeongmin graph load remain pending):

```text
official raw source
        |
        v
source adapter -> immutable raw artifact + checksum
        |
        v
normalized JSONL + quarantine + append-only READY manifest
        |
        v
offline checksum/count/identity verification
        |
        v
explicitly authorized load -> bounded MERGE batches -> Neo4j portfolio graph
```

The historical implemented Phase-3 target policy accepts only `sec_nport` and
`manager_basket`, hard-blocks KRX acquisition identifiers and URLs, and fixes
the inclusive as-of window to 2026-01-11 through 2026-07-11 with publication
cutoff 2026-07-11T23:59:59Z. CLI bounds may narrow but cannot widen that
historical adapter policy; it is not the current contest-wide data policy.
One real KSTR N-PORT filing has been collected and written to disposable local
Neo4j staging. No Yeongmin Neo4j write has been performed.
Artifact verification rejects absolute paths, traversal, escapes, and symlinks,
then hashes and parses the same in-memory normalized bytes. This protects the
offline handoff boundary, but cannot defend against a malicious same-user local
process replacing files during the final resolve/read system-call interval.
Each READY artifact and load range is also bound to both the deterministic
target-config digest and the exact crosswalk file SHA-256. Verification and
loading therefore require the same `--crosswalk`; a changed crosswalk requires
recollection and selects its newly content-addressed normalized output without
invalidating older immutable artifacts.
Fetches also resolve and reject non-public IPv4/IPv6 destinations immediately
before every initial or redirected request. The standard TLS client resolves
again when connecting, so DNS rebinding between validation and connection
remains a residual risk until IP-pinned TLS transport is implemented.

Planned query path:

```text
question -> planner -> validated DSL
                       |
             +---------+----------+
             |         |          |
           graph   XBRL/facts   documents
             +---------+----------+
                       |
        evidence merge + answerability
                       |
             grounded final answer
```

The existing TTL files are currently a small FIBO-aligned class/subclass
application profile. Operational graph properties and SHACL constraints remain
on the checklist.

## Quick start

Requirements: Docker with Compose and
[`uv`](https://docs.astral.sh/uv/). The neosemantics plugin is present in this
repository. Active XLSX commands must point at the fixed 2026-07-11 organizer
baseline under `data/1.금융상품`; do not substitute any legacy directory or
later organizer files.

```bash
cp .env.example .env
# Set a non-default NEO4J_PASSWORD in .env.

docker compose up -d neo4j-2 neo4j-proxy-2
uv sync

uv run mirae-graph dry-run --input-dir "data/1.금융상품"
uv run mirae-graph load --input-dir "data/1.금융상품" --batch-size 500
uv run mirae-graph validate
```

Load selected datasets by repeating `--dataset`:

```bash
uv run mirae-graph load \
  --input-dir "data/1.금융상품" \
  --dataset domestic_bonds \
  --dataset domestic_etf_etn
```

Valid dataset codes are `domestic_bonds`, `domestic_etf_etn`,
`overseas_etf_etn`, and `public_funds`.

## Historical answerability baseline

The historical 2026-07-11 graph baseline can support exact product/identifier
lookup, source-backed manager/issuer and listing traversal, classifications,
provenance, and many point-in-time numeric filters where values are populated.

It cannot answer the three relationship-heavy examples end to end:

| Question | Historical result | Primary gap |
|---|---|---|
| Cambricon in China semiconductor ETFs | Unsupported | Dated holdings and company/security identity |
| Six-month aerospace-theme connections | Unsupported as written | Repeated snapshots and sourced temporal theme links |
| Largest ETF holding an EcoPro subsidiary, with risks | Unsupported as written | Corporate control, holdings, and risk disclosures |

Field existence is not enough in the historical 2026-07-11 baseline: domestic dividend frequency is entirely blank,
the main fee field is populated in only 217 of 1,734 ETF/ETN rows, and every
populated tracking-error value is `0.00`. See the full
[`answerability matrix`](docs/evaluation/historical-data-capabilities-2026-07-11.md#evaluation-of-all-sample-questions).

## External-data design

Use separate, linked ontology modules for holdings, companies, filings, and
documents. Add only stable identifiers and carefully defined current projections
to existing product nodes.

XBRL is a filing format and taxonomy—not a replacement for the application
ontology. Preserve full XBRL contexts for company facts. Keep non-XBRL ETF
sources such as KRX baskets, issuer CSV files, and SEC Form N-PORT XML in their
original raw formats, then normalize them into the portfolio model.

The source-by-source acquisition plan, required fields, relationship shapes,
licensing/rate-limit cautions, and delivery sequence are in
[`docs/external/external-data-plan.md`](docs/external/external-data-plan.md).

## Repository layout

```text
.
├── docs/                  # start-here index, plan, and organized documentation
│   ├── requirements/      # contest interpretation
│   ├── architecture/      # graph model and DSL design
│   ├── data/              # field reference and load records
│   ├── evaluation/        # historical baselines/regression checklists
│   ├── external/          # enrichment plans and source decisions
│   ├── operations/        # staging/run records
│   ├── artifacts/         # JSON schema and reviewed JSON evidence
│   └── archive/           # superseded proposal material
├── ontology/              # five current FIBO-aligned Turtle modules
├── plugins/               # neosemantics plugin used by Compose
├── src/mirae_asset_graph/ # XLSX model, loader, CLI, and validation
├── data/1.금융상품/       # fixed 2026-07-11 organizer baseline input directory
├── docker-compose.yaml
├── pyproject.toml
└── uv.lock
```

## Documentation

Start at [`docs/README.md`](docs/README.md). Use the status column to
distinguish implemented behavior from requirements, future plans, historical
baselines, and archive material. A model or example in a design document is not
evidence that its data or execution path currently exists.

| Document | Status / authority | Use it for |
|---|---|---|
| [`docs/plan.md`](docs/plan.md) | **Current source of truth** | Active priorities, blockers, execution order, fixed-baseline rules, and external backlog |
| [`docs/README.md`](docs/README.md) | Start-here index | Documentation authority order and status map |
| [`docs/requirements/contest.md`](docs/requirements/contest.md) | Requirements context | Contest interpretation and target behavior; not implementation status |
| [`docs/evaluation/historical-data-capabilities-2026-07-11.md`](docs/evaluation/historical-data-capabilities-2026-07-11.md) | Historical baseline | Loaded 2026-07-11 XLSX/graph evidence boundary and sample-question decisions |
| [`docs/evaluation/historical-sample-questions-regression.md`](docs/evaluation/historical-sample-questions-regression.md) | Historical regression checklist | Preserved supported/partial/empty/unsupported outcomes |
| [`docs/architecture/graph-model-guide.md`](docs/architecture/graph-model-guide.md) | Current implementation | Implemented nodes, relationships, mappings, and limitations |
| [`docs/data/loading-record.md`](docs/data/loading-record.md) | Historical implementation record | Reproducible 2026-07-11 load record, environment, commands, validation totals, and KSTR staging proof |
| [`docs/data/xlsx-field-reference.md`](docs/data/xlsx-field-reference.md) | Historical source reference | All 207 historical fields, graph treatment, ambiguity, and population cautions |
| [`docs/architecture/query-dsl-spec.md`](docs/architecture/query-dsl-spec.md) | Design only | Proposed read-only query language; compiler/API not implemented |
| [`docs/artifacts/query-dsl.schema.json`](docs/artifacts/query-dsl.schema.json) | Design artifact | Structural JSON Schema for the proposed DSL |
| [`docs/external/external-data-plan.md`](docs/external/external-data-plan.md) | Future work | Planned official sources, XBRL handling, and ontology modules |
| [`docs/external/source-decisions-phase3-2026-08-19.md`](docs/external/source-decisions-phase3-2026-08-19.md) | Decision record | Phase 3 D+1 source stop/go decisions |
| [`docs/external/phase3-target-discovery.md`](docs/external/phase3-target-discovery.md) | Reviewed evidence | Phase 3 target discovery and selected KSTR target evidence |
| [`docs/operations/local-neo4j-staging.md`](docs/operations/local-neo4j-staging.md) | Operational record | Disposable local Neo4j staging procedure and proof |
| [`docs/archive/README.old.md`](docs/archive/README.old.md) | Archive | Preserved verbose architecture proposal; not current behavior |

## License

Private — Mirae Asset × Naver AI Festival 2026.
