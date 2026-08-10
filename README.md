# Mirae Asset Financial Product Agent

Ontology-grounded financial-product retrieval for the Mirae Asset × Naver AI
Festival. The repository currently implements the **XLSX-to-Neo4j data and
ontology foundation**. The natural-language query service, external evidence
pipelines, and answer-generation API are planned but not yet implemented.

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
- [ ] Add reviewed fund-family, organization, market, and security-identifier
      crosswalks; never merge entities by name alone.
- [ ] Implement snapshot supersession, correction, disappearance, and deletion
      semantics for later XLSX loads.

### External evidence and ontology enrichment

- [ ] Implement a source-acquisition framework with authentication, rate limits,
      licensing metadata, checksums, retries, amendment handling, and cutoff
      controls.
- [ ] Add `portfolio.ttl` and dated ETF holdings/creation baskets, benchmark
      constituents, weights, quantities, values, and currencies.
- [ ] Add `corporate.ttl` and sourced, time-bounded parent/subsidiary/control
      assertions with security-to-company mappings.
- [ ] Add `reporting.ttl` and conformant XBRL/iXBRL ingestion, preserving filing,
      taxonomy, concept, context, period, unit, dimensions, and amendments.
- [ ] Add `disclosure.ttl`, prospectuses/reports, addressable risk passages, and
      a document/vector index.
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

- [ ] Add unit tests for parsing, normalization, identity, and DSL validation.
- [ ] Add integration tests for Neo4j loading, idempotency, provenance, and
      query compilation.
- [ ] Turn the sample questions into golden answerability/evidence tests,
      including deliberately unanswerable inputs.
- [ ] Measure external-source coverage, freshness, corrections, and outage
      behavior.
- [ ] Meet the contest latency target and test concurrent evaluation requests.
- [ ] Add service observability, secrets handling, source-health reporting, and
      a reproducible production deployment.

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
