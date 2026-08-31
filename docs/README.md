# Documentation index

Start here for documentation authority and status. The current execution source
of truth is [`docs/plan.md`](plan.md). If another document conflicts with the
plan, follow the plan unless it explicitly delegates authority to that document.

## Authority order

1. [`docs/plan.md`](plan.md) — active plan, guardrails, blockers, and current
   status.
2. Current implementation docs — architecture, data, operations, source decisions,
   and artifacts listed below.
3. Historical evaluation docs — preserved baselines and regression checklists;
   they do **not** override the current plan.
4. Archive — preserved proposals or stale architecture notes only.

The active organizer data boundary is fixed at the 2026-07-11 baseline in
`data/1.금융상품`. The local file set and dry-run are verified; Neo4j load and
graph validation remain pending. Later organizer announcements or files,
including the 2026-08-22/2026-08-23 notice, are superseded audit context only
and must never be loaded into the active graph.

Organizer baseline and evaluation clarifications are summarized in
[`requirements/contest.md`](requirements/contest.md#organizer-baseline-and-clarification-addendum).

## Map

| Area | Role |
|---|---|
| [`requirements/`](requirements/) | Contest requirements interpretation and target API/proposal expectations. |
| [`architecture/`](architecture/) | Implemented graph model and proposed read-only query DSL. |
| [`data/`](data/) | XLSX field reference and historical local load record. |
| [`operations/`](operations/) | Operational records for local staging and run procedures. |
| [`external/`](external/) | External enrichment plan, Phase 3 source decisions, and target discovery. |
| [`evaluation/`](evaluation/) | Historical 2026-07-11 capability baseline and regression checklist. |
| [`artifacts/`](artifacts/) | Machine-readable schema and reviewed Phase 3 JSON evidence artifacts. |
| [`archive/`](archive/) | Superseded or proposal-era documents; not current behavior. |

## Key documents

| Document | Status / authority | Use it for |
|---|---|---|
| [`plan.md`](plan.md) | **Current source of truth** | Active priorities, current blockers, status, and execution order |
| [`requirements/contest.md`](requirements/contest.md) | Requirements context | Contest interpretation and target behavior; not implementation status |
| [`architecture/graph-model-guide.md`](architecture/graph-model-guide.md) | Current implementation | Implemented nodes, relationships, mappings, and limitations |
| [`architecture/query-dsl-spec.md`](architecture/query-dsl-spec.md) | Design only | Proposed read-only query language; compiler/API not implemented |
| [`artifacts/query-dsl.schema.json`](artifacts/query-dsl.schema.json) | Design artifact | Structural JSON Schema for the proposed DSL |
| [`data/loading-record.md`](data/loading-record.md) | Historical implementation record | 2026-07-11 local load totals and KSTR local staging proof |
| [`data/xlsx-field-reference.md`](data/xlsx-field-reference.md) | Historical source reference | Fields observed in the historical 2026-07-11 workbooks |
| [`external/external-data-plan.md`](external/external-data-plan.md) | Future work | Planned official sources, XBRL handling, and ontology modules |
| [`external/source-decisions-phase3-2026-08-19.md`](external/source-decisions-phase3-2026-08-19.md) | Decision record | Phase 3 source stop/go decisions |
| [`external/phase3-target-discovery.md`](external/phase3-target-discovery.md) | Reviewed evidence | First controlled external-collection target discovery |
| [`operations/local-neo4j-staging.md`](operations/local-neo4j-staging.md) | Operational record | Disposable local Neo4j staging procedure and proof |
| [`evaluation/historical-data-capabilities-2026-07-11.md`](evaluation/historical-data-capabilities-2026-07-11.md) | Active fixed baseline | Loaded 2026-07-11 XLSX/graph capability facts for the organizer baseline |
| [`evaluation/historical-sample-questions-regression.md`](evaluation/historical-sample-questions-regression.md) | Historical regression checklist | Preserved outcomes for the old public sample questions |
| [`archive/README.old.md`](archive/README.old.md) | Archive | Preserved verbose architecture proposal; not current behavior |
