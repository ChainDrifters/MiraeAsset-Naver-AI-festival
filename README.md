# Mirae Asset Financial Product Agent

Ontology-grounded financial-product retrieval for the Mirae Asset × Naver AI
Festival. The repository implements the **XLSX-to-Neo4j data and ontology
foundation** plus the credential-independent core of an **external-evidence
ingestion framework**. Live external backfill, corporate/disclosure/theme
evidence, the natural-language query service, and the answer-generation API
remain incomplete.

Current data boundary: four financial-product master snapshots dated
**2026-07-11**. See
[`docs/current-data-capabilities.md`](docs/current-data-capabilities.md) before
claiming that a question is answerable.

## Implementation checklist

Checked items are present in this repository. Unchecked items are required or
planned work; their order roughly follows implementation priority.

### Data and graph foundation

- [x] Load the four supplied XLSX datasets and their schema workbooks.
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
- [ ] Obtain the source vendor's field definitions, code dictionaries, rating
      scales, and formula/unit specifications.
- [x] Add a reviewed contest-entity identity crosswalk with strict identifier
      joins and a tested guard against name-only merges.
- [ ] Expand reviewed fund-family, organization, market, and identifier
      crosswalks beyond the contest entity set.
- [ ] Implement snapshot supersession, correction, disappearance, and deletion
      semantics for later XLSX loads.

### External evidence and ontology enrichment

- [x] Implement the source-acquisition core: adapter contract, append-only run
      manifests, deterministic batches, checksums, retries, cutoff filtering,
      quarantine, offline artifact verification, and resumable loads.
- [x] Implement SEC N-PORT XML and Korean manager-published CSV/XLSX basket
      adapters with offline fixtures and source-specific access controls.
- [ ] Implement live target discovery, archived-file collection, and the
      2026-01-11 through 2026-07-11 backfill.
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
- [ ] Add jurisdiction adapters as coverage requires: OpenDART/KRX/KOFIA,
      SEC EDGAR/N-PORT, EDINET, ESEF national repositories, FCA/Companies House,
      and Chinese exchanges.

### Query service and agent

- [x] Specify the proposed read-only query DSL and JSON request schema.
- [x] Define `answered`, `partial`, `empty`, `invalid`, `unsupported`, and
      `ambiguous` answer outcomes.
- [ ] Implement semantic DSL validation and compilation to bounded Cypher.
- [ ] Implement exact entity resolution, alias handling, and clearly labeled
      near-match suggestions without silent substitution.
- [ ] Implement natural-language intent/entity extraction and query planning.
- [ ] Implement routing across the graph, an XBRL/numeric fact store, and the
      document index.
- [ ] Implement observation selection, temporal joins, ranking, currency
      normalization, and evidence merging.
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
- [ ] Turn the sample questions into golden answerability/evidence tests,
      including deliberately unanswerable inputs.
- [ ] Measure external-source coverage, freshness, corrections, and outage
      behavior.
- [ ] Meet the contest latency target and test concurrent evaluation requests.
- [ ] Add service observability, secrets handling, source-health reporting, and
      a reproducible production deployment.

Current test baseline: **183 passed and 2 environment-gated integration tests
skipped** without a live test Neo4j URI.

## Current external-ingestion status

The tracked execution source of truth is [`docs/plan.md`](docs/plan.md). Source
licensing and access decisions are recorded in
[`docs/external-sources-decision.md`](docs/external-sources-decision.md).

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
  183 passing offline tests.

Known blockers and unfinished work:

- the current local OpenDART key was explicitly authorized by the user on
  2026-08-24 and remains only in the git-ignored `.env`; rotation is still
  recommended because it was previously exposed;
- separate authorization and credentials are still required before loading the
  verified staging bundle into the Yeongmin Neo4j database;
- Tailscale SSH/rsync parameters are required for raw-artifact transfer;
- `xlsx_data/` is absent from this checkout; and
- target coverage beyond the first KSTR N-PORT filing, OpenDART control
  ingestion, disclosure passages, theme history, and golden answerability tests
  are not implemented.

Investment recommendation, suitability judgment, customer profiling, and
recommendation scoring are explicitly out of scope. Objective filtering,
comparison, and ranking by a user-supplied metric remain in scope.

## Current dataset and graph

| Dataset | Source rows | Canonical result |
|---|---:|---|
| Domestic bonds | 42,394 | 42,394 bonds |
| Korean ETF/ETN | 1,734 | 1,202 ETFs and 532 ETNs |
| Overseas ETF/ETN | 5,646 | 5,537 ETFs and 59 ETNs |
| Public funds | 95,619 | 11,138 funds and 11,138 units; one malformed row rejected |
| **Total** | **145,393** | **145,392 linked source rows** |

Validated graph totals include 17,877 funds, 17,877 fund units, 591 ETNs,
32,303 listings, and 67,825 observations, with no duplicate resource URIs or
unlinked non-rejected source rows.

The observations are point-in-time records from one load—not per-product
history. Current XLSX data does not include ETF holdings, corporate-control
relationships, sourced theme history, or prospectus risk passages.

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

The production target policy accepts only `sec_nport` and `manager_basket`,
hard-blocks KRX acquisition identifiers and URLs, and fixes the inclusive
as-of window to 2026-01-11 through 2026-07-11 with publication cutoff
2026-07-11T23:59:59Z. CLI bounds may narrow but cannot widen that policy.
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
[`uv`](https://docs.astral.sh/uv/). The XLSX snapshots and neosemantics plugin
are already present in this repository.

```bash
cp .env.example .env
# Set a non-default NEO4J_PASSWORD in .env.

docker compose up -d neo4j-2 neo4j-proxy-2
uv sync

uv run mirae-graph dry-run
uv run mirae-graph load --batch-size 500
uv run mirae-graph validate
```

Load selected datasets by repeating `--dataset`:

```bash
uv run mirae-graph load \
  --dataset domestic_bonds \
  --dataset domestic_etf_etn
```

Valid dataset codes are `domestic_bonds`, `domestic_etf_etn`,
`overseas_etf_etn`, and `public_funds`.

## Current answerability

The graph can currently support exact product/identifier lookup, source-backed
manager/issuer and listing traversal, classifications, provenance, and many
point-in-time numeric filters where values are populated.

It cannot answer the three relationship-heavy examples end to end:

| Question | Current result | Primary gap |
|---|---|---|
| Cambricon in China semiconductor ETFs | Unsupported | Dated holdings and company/security identity |
| Six-month aerospace-theme connections | Unsupported as written | Repeated snapshots and sourced temporal theme links |
| Largest ETF holding an EcoPro subsidiary, with risks | Unsupported as written | Corporate control, holdings, and risk disclosures |

Field existence is not enough: domestic dividend frequency is entirely blank,
the main fee field is populated in only 217 of 1,734 ETF/ETN rows, and every
populated tracking-error value is `0.00`. See the full
[`answerability matrix`](docs/current-data-capabilities.md#evaluation-of-all-sample-questions).

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
[`docs/external-data-plan.md`](docs/external-data-plan.md).

## Repository layout

```text
.
├── docs/                  # requirements, model, field, DSL, and planning docs
├── ontology/              # five current FIBO-aligned Turtle modules
├── plugins/               # neosemantics plugin used by Compose
├── src/mirae_asset_graph/ # XLSX model, loader, CLI, and validation
├── xlsx_data/             # four data snapshots and four schema workbooks
├── docker-compose.yaml
├── pyproject.toml
└── uv.lock
```

## Documentation

Use the status column to distinguish implemented behavior from requirements and
future plans. A model or example in a design document is not evidence that its
data or execution path currently exists.

| Document | Status / authority | Use it for |
|---|---|---|
| [`docs/contest_req.md`](docs/contest_req.md) | Requirements context | Contest interpretation and target behavior; not implementation status |
| [`docs/current-data-capabilities.md`](docs/current-data-capabilities.md) | **Current capability baseline** | Current XLSX/graph evidence boundary and all sample-question decisions |
| [`docs/sample_questions.md`](docs/sample_questions.md) | Current evaluation checklist | Compact supported/partial/empty/unsupported decisions |
| [`docs/graph-model-guide.md`](docs/graph-model-guide.md) | Current implementation | Implemented nodes, relationships, mappings, and limitations |
| [`docs/data-loading.md`](docs/data-loading.md) | Current implementation | Reproducible load record, environment, commands, and validation totals |
| [`docs/xlsx-field-reference.md`](docs/xlsx-field-reference.md) | Current source reference | All 207 fields, graph treatment, ambiguity, and population cautions |
| [`docs/query-dsl-spec.md`](docs/query-dsl-spec.md) | Design only | Proposed read-only query language; compiler/API not implemented |
| [`docs/query-dsl.schema.json`](docs/query-dsl.schema.json) | Design artifact | Structural JSON Schema for the proposed DSL |
| [`docs/external-data-plan.md`](docs/external-data-plan.md) | Future work | Planned official sources, XBRL handling, and ontology modules |
| [`docs/README.old.md`](docs/README.old.md) | Archive | Preserved verbose architecture proposal; not current behavior |

## License

Private — Mirae Asset × Naver AI Festival 2026.
