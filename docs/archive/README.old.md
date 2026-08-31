# MiraeAsset × Naver AI Festival — Financial Product Agent

> **Archive status — proposal, not current implementation.** This file preserves
> an early target architecture. It assumes an RDB, vector index, holdings,
> corporate relationships, an evaluation API, and query components that are not
> present in the current repository, and some examples/counts are stale. Use
> [`README.md`](../../README.md) as the project index,
> [`../README.md`](../README.md) as the documentation index,
> [`../evaluation/historical-data-capabilities-2026-07-11.md`](../evaluation/historical-data-capabilities-2026-07-11.md) for the preserved historical baseline, and
> [`../external/external-data-plan.md`](../external/external-data-plan.md) for the
> future enrichment design.

An AI-powered financial product search agent built for the MiraeAsset × Naver AI Festival hackathon. The agent answers natural language queries about financial products (ETFs, bonds, funds) using **Ontology-grounded Federated Retrieval** across a Knowledge Graph, RDB, and Vector DB — with **HyperclovaX** as the final answer generation layer.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Pipeline](#pipeline)
- [Sub-Agent Classification](#sub-agent-classification)
- [Data Flow](#data-flow)
- [Graph Schema (Neo4j)](#graph-schema-neo4j)
- [Data Source Responsibilities](#data-source-responsibilities)
- [Latency Budget — 15s Average](#latency-budget--15s-average)
- [Anti-Hallucination & Scoring Defense](#anti-hallucination--scoring-defense)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Key Cypher Patterns](#key-cypher-patterns)

---

## Architecture Overview

The system follows the pipeline emphasized in the tech session:

```
LLM → Ontology → GraphRAG → RDB/VectorDB → LLM
```

Decomposed into a multi-layer Sub-Agent system:

| Layer | Role | Model | LLM Call |
|-------|------|-------|----------|
| **LLM-1 (Query Understanding)** | Parse natural language query, extract Intent + Entities | **HCX-003** | 1 |
| **Ontology** | Map extracted entities to schema classes/properties | **Code (Python)** | 0 |
| **GraphRAG** | Multi-hop relationship traversal in Knowledge Graph | **Code (Cypher)** | 0 |
| **RDB / VectorDB** | Structured numeric data + semantic text search | **Code / Embedding** | 0 |
| **Validation** | Business rule validation, hallucination check | **Code + HCX-003** | 1 |
| **LLM-2 (Answer Generation)** | Generate final answer with provenance | **HCX-005 (required)** | 1 |

**Total LLM calls per query: 3** — everything else is code-based for speed.

> **Model Policy**: Per the session guidelines, HyperclovaX is **required** for Answer Generation. Using HyperclovaX (HCX-003) elsewhere is fully permitted and recommended for Intent Analysis. All non-generation layers use either HCX-003 or pure code to minimize latency.

---

## Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER QUERY (natural language)                │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Layer 1: LLM-1    │         ⏱ ~1.5s
                    │  Query Understanding │
                    │    **HCX-003**       │
                    └──────────┬──────────┘
                               │  Intent + Entities + Constraints
                               │
                    ┌──────────▼──────────┐
                    │   Layer 2: Ontology │         ⏱ ~0.3s
                    │  Ontology Grounding  │
                    │  **Code (Python)**   │
                    └──────────┬──────────┘
                               │  Query plan with schema mapping
                               │
                    ┌──────────▼──────────┐
                    │ Layer 3: Query Router│         ⏱ ~0.1s
                    │ **Code (Python)**    │
                    └──┬─────┬─────┬──────┘
                       │     │     │
          ┌────────────▼┐ ┌──▼───┐ ┌▼────────────┐
          │  GraphRAG   │ │ RDB  │ │  VectorDB   │  ⚡ Parallel
          │  (Neo4j)    │ │(SQL) │ │ (Embedding) │  ⏱ ~2s
          └────────┬────┘ └──┬───┘ └┬────────────┘
                   └────┬─────┘     │
                        │           │
                   ┌────▼───────────▼┐
                   │ Layer 4: Result  │         ⏱ ~0.3s
                   │   Federator      │
                   │ **Code (Python)**│
                   └────────┬─────────┘
                            │  Unified results + evidence
                            │
                   ┌────────▼─────────┐
                   │ Layer 5: Validator│         ⏱ ~0.5s
                   │ Answer Validation │
                   │ + Grounding Check │
                   │ **Code + HCX-003**│
                   └────────┬─────────┘
                            │  Validated evidence data
                            │
                   ┌────────▼──────────┐
                   │  Layer 6: LLM-2   │         ⏱ ~5-8s
                   │ Answer Generation │
                   │ **HCX-005 (req)** │
                   └────────┬──────────┘
                            │  Answer + Provenance
                            │
                    ┌───────▼───────┐
                    │  API Response  │  Total: ~10-14s
                    └───────────────┘
```

---

## Sub-Agent Classification

### Layer 1 — Query Understanding (HCX-003)

| Sub-Agent | Role | Model | Notes |
|-----------|------|-------|-------|
| **Intent Analyzer** | Decompose query into Intent, Domain, Action | HCX-003 | Fast inference |
| **Entity Extractor** | Extract entities (product name, firm, strategy, return period) | HCX-003 | Combined with Intent in single call |
| **Entity Resolver** | Resolve entity references ("this product" → TIGER KOSPI 200) | HCX-003 / Rule-based | Try alias table first → fallback to LLM |

> **Key Challenge**: Entity Resolution is the hardest problem. Chunk-level data ingestion loses context — "this ETF" on page 5 doesn't know it refers to the product named on page 1.

### Layer 2 — Ontology Grounding (Code)

| Sub-Agent | Role | Model | Notes |
|-----------|------|-------|-------|
| **Ontology Mapper** | Map entities to OntologyClass + Property | Code (Python) | Pre-built mapping table + FIBO URI lookup |
| **Constraint Checker** | Validate versioned source/ontology constraints (for example, the applicable risk-grade scale) | Code (Python) | Rule engine — no LLM needed |
| **Query Planner** | Decide which sources (Graph/RDB/Vector) to query | Code (Python) | Intent category → query template matching |

### Layer 3 — Federated Retrieval (Code)

| Sub-Agent | Role | Model | Notes |
|-----------|------|-------|-------|
| **Graph Retriever** | Execute Cypher — Multi-hop relationship traversal | Code (Cypher) | Template-based, no LLM |
| **Vector Retriever** | Vector similarity search — risk descriptions, strategy text | Embedding Model | multilingual-e5-large (1024d) |
| **SQL Retriever** | RDB query — returns, NAV, AUM, fees | Code (SQL) | Pre-defined queries + business logic |

### Layer 4 — Validation (Code + HCX-003)

| Sub-Agent | Role | Model | Notes |
|-----------|------|-------|-------|
| **Result Federator** | Merge 3 sources, deduplicate by Entity URI | Code (Python) | Dict join |
| **Answer Validator** | Business rule validation (asOf date, sort order) | Code (Python) | **Critical** — prevents scoring penalties |
| **Grounding Checker** | Detect hallucinated content not backed by data | Code + HCX-003 | **Critical** — prevents scoring penalties |

### Layer 5 — Answer Generation (HCX-005)

| Sub-Agent | Role | Model | Notes |
|-----------|------|-------|-------|
| **Answer Generator** | Generate final answer with provenance/evidence | **HCX-005** | Required by competition rules |

---

## Data Flow

### Example: "Show me quarterly-dividend ETFs with low management fees"

```
Query Understanding (HCX-003)
  → intent: SEARCH
  → domain: ETF
  → action: FILTER + SORT + TOP_N
  → constraints:
      - dividend_type = "QUARTERLY"
      - sort_by = feeRate ASC
      - market = "KR"
        │
        ▼
Ontology Grounding (Code)
  "ETF"           → OntologyClass: Exchange-traded fund
  "quarterly div" → Fund.dividendFrequency = "QUARTERLY"
  "management fee"→ Fund.feeRate (Graph) or cu_charge_rt (RDB)
  "domestic"      → Market.code = "KR"
        │
        ▼
Query Planner (Code)
  1. Graph: MATCH (f:Fund)-[:HAS_UNIT]->(u)-[:LISTED_AS]->(l)-[:ON_MARKET]->(m {code:'KR'})
             WHERE f.dividendFrequency = 'QUARTERLY'
  2. RDB:   SELECT item_no, fee_rate FROM fund WHERE dividend_freq = 'Q' ORDER BY fee_rate ASC
  3. Vector: SKIP (no unstructured text needed)
        │
        ▼ (parallel execution)
Graph + RDB results federated by Entity URI
        │
        ▼
Answer Validator (Code)
  ✓ AsOf date ≤ 2026-07-11
  ✓ Sort order verified
  ✓ No hallucinated products
        │
        ▼
Answer Generation (HCX-005)
  "Here are 5 quarterly-dividend ETFs with the lowest fees:
   1. TIGER KOSPI 200 (feeRate: 0.05%)
   Evidence: FundSnapshot.asOf=2026-07-11, SourceRecord.uri=..."
```

---

## Graph Schema (Neo4j)

Built on **FIBO** (Financial Industry Business Ontography) standard with **n10s** (Neo4j neosemantics) for RDF/LPG bridging.

### Ontology Class Hierarchy

```
FinancialProduct
└── FinancialInstrument                            (60,862 nodes)
    ├── Debt instrument
    │   ├── Bond                                   (42,394)
    │   └── Exchange-traded note                   (591)
    └── Listed security
        └── Tradable fund unit → FundUnit          (6,914)

FundUnit                                            (17,877)
├── Non-tradable fund unit                         (10,963)
└── Tradable fund unit                             (6,914)

Observation (Snapshot)
├── BondSnapshot                                   (42,394)
├── FundSnapshot                                   (17,877)
└── MarketSnapshot                                 (7,554)
```

### Key Node Properties

| Label | Key Properties |
|-------|---------------|
| `Fund` | name, shortName, strategy, currency, leverageFactor, feeRate, otherFeeRate, productGroup, baseIndexName |
| `FundSnapshot` | netAssetValue, navPerShare, previousNav, assetsUnderManagement, netAssetTotal, return1d/1m/3m/6m/1y/Ytd, asOf |
| `BondSnapshot` | price/yield data, asOf |
| `MarketSnapshot` | basePrice, closePrice, highPrice, lowPrice, tradingVolume1d, priceChangeRate, asOf |
| `Listing` | ticker, marketCode, marketName, listingDate, listingPrice |
| `Organization` | name, identityScheme |
| `Identifier` | scheme, value (ISIN, ticker, etc.) |
| `Classification` | type, category |
| `SourceRecord` | 70+ raw fields from original data (pd_nm, pd_itm_no, cu_strtegy, du_er_ytd, ...) |

### Relationship Types

| Relationship | Direction | Meaning | Count |
|---|---|---|---|
| `INSTANCE_OF` | Node → OntologyClass | Ontology typing | 77,962 |
| `SUBCLASS_OF` | Class → Class | FIBO class hierarchy | 10 |
| `CLASSIFIED_AS` | Node → Classification | Product classification | 194,989 |
| `HAS_IDENTIFIER` | Entity → Identifier | ISIN, ticker | 83,825 |
| `DESCRIBES` | SourceRecord → Entity | Data lineage | 102,407 |
| `HAS_OBSERVATION` | Entity → Snapshot | Time-series data | 67,825 |
| `HAS_UNIT` | Fund → FundUnit | Fund units | 17,877 |
| `ISSUED_BY` | Instrument → Organization | Issuer | 41,476 |
| `MANAGED_BY` | Fund → Organization | Asset manager | 17,862 |
| `LISTED_AS` | Instrument → Listing | Listing info | 24,749 |
| `ON_MARKET` | Listing → Market | Exchange | 32,303 |
| `OFFERS` | Organization → Offering | Sale offering | 17,927 |
| `TRACKS` | Fund → Benchmark | Benchmark tracking | 16,738 |
| `IN_FILE` | SourceRecord → SourceFile | Source lineage | 145,392 |

---

## Data Source Responsibilities

### Neo4j Graph DB (GraphRAG)

**Strength: Multi-hop relationship traversal, inference**

| Query Type | Pattern | Example |
|-----------|---------|---------|
| Direct lookup | `MATCH (f:Fund)-[:MANAGED_BY]->(o)` | "ETFs managed by MiraeAsset" |
| Multi-hop | `MATCH (o)-[:OFFERS]->(f)-[:HAS_UNIT]->(u)-[:LISTED_AS]->(l)-[:ON_MARKET]->(m)` | "Domestic listed ETFs sold by MiraeAsset" |
| Classification | `MATCH (f)-[:CLASSIFIED_AS]->(c)` | "Dividend ETFs" |
| Benchmark | `MATCH (f)-[:TRACKS]->(b:Benchmark)` | "ETFs tracking KOSPI 200" |

### RDB (PostgreSQL)

**Strength: Structured numerics, fast sort/filter, business logic**

| Data | Table | Key Fields |
|------|-------|-----------|
| Product master | `product_master` | item_no, name, strategy, risk_grade, fee_rate |
| Returns | `fund_returns` | return_1d, return_1m, return_ytd, return_1y, as_of |
| NAV/AUM | `fund_nav` | nav_per_share, aum, net_asset_total, as_of |
| Holdings | `etf_holdings` | etf_item_no, constituent_code, weight, as_of |

### Vector DB (Neo4j Native Vector Index)

**Strength: Semantic search on unstructured text**

| Data | Embedding Target | Example |
|------|-----------------|---------|
| Investment risk | Prospectus risk sections | "This ETF has tracking error risk..." |
| Strategy description | Investment objective text | "Focused on secondary battery industry..." |
| Fund reports | Semi-annual/quarterly reports | "During this period, the market..." |

---

## Latency Budget — 15s Average

> Session: "Real service standard is 15 seconds — it's actually quite demanding"
> Target: **15s average**, 30s maximum

### Stage-by-Stage Budget

| Stage | Time | Method | LLM Calls |
|-------|------|--------|-----------|
| 1. Query Understanding | ~1.5s | HCX-003 single call (Intent + Entity combined) | 1 |
| 2. Ontology Grounding | ~0.3s | Code — pre-built mapping table | 0 |
| 3. Query Planning | ~0.1s | Code — Intent → template matching | 0 |
| 4. Federated Retrieval | ~2s | Graph + RDB + Vector **in parallel** | 0 |
| 5. Result Federation | ~0.3s | Code — URI join | 0 |
| 6. Validation | ~0.5s | Code — rule-based | 0 |
| 7. Answer Generation | ~5-8s | HCX-005 | 1 |
| 8. Grounding Check | ~1s | HCX-003 | 1 |
| **Total** | **~10-14s** | | **3** |

### 6 Optimization Strategies

**1. Minimize LLM Calls — Only 3**

| Replaceable LLM Step | Code Replacement |
|---------------------|-----------------|
| Ontology Mapper | Pre-built mapping table (`entity_alias.json`) + FIBO URI lookup |
| Query Planner | Intent category → pre-written Cypher/SQL template sets |
| Constraint Checker | Python rule engine (`if risk_grade not in range(1,6): reject`) |
| Answer Validator | Python business logic (date filter, keyword block, sort verify) |
| Result Federator | Python dict join (`{uri: {graph_data, sql_data, vector_data}}`) |

**2. Parallel Retrieval Execution**

```python
async def federated_retrieval(query_plan):
    graph_task = asyncio.create_task(graph_retriever.execute(query_plan.graph))
    sql_task   = asyncio.create_task(sql_retriever.execute(query_plan.sql))
    vec_task   = asyncio.create_task(vector_retriever.execute(query_plan.vector))

    graph_result, sql_result, vec_result = await asyncio.gather(
        graph_task, sql_task, vec_task
    )
    return federate(graph_result, sql_result, vec_result)
# Parallel: max(2s, 0.5s, 1s) = 2s
# Sequential: 2s + 0.5s + 1s = 3.5s  → saves 1.5s
```

**3. Query Router — Skip Unnecessary Sources**

| Query Type | Graph | RDB | Vector |
|-----------|-------|-----|--------|
| "Top 5 ETFs by AUM" | ✗ | ✓ | ✗ |
| "ETFs managed by MiraeAsset" | ✓ | ✗ | ✗ |
| "Secondary battery theme ETFs" | ✗ | ✗ | ✓ |
| "Quarterly-dividend + low-fee ETFs" | ✓ | ✓ | ✗ |
| "Low tracking-error ETFs" | ✓ | ✓ | ✓ |

**4. Unanswerable Query Fast-Path**

```
"Tell me about KIMI-related investment products"
  → Query Understanding detects "KIMI" in blocklist
  → Skip entire pipeline → return "Cannot be verified" (~2s)
```

**5. Connection Pooling + Pre-warming**

| Resource | Strategy |
|----------|---------|
| Neo4j | Bolt connection pool (min 5 persistent) |
| RDB | SQLAlchemy pool (pool_size=10, pool_pre_ping=True) |
| HCX API | HTTP keep-alive, connection reuse |
| Embedding | Model resident in memory (local inference) |

**6. Answer Generation Tuning (HCX-005)**

| Strategy | Effect |
|----------|--------|
| Limit `max_tokens` | Prevents overlong answers (linear time increase) |
| Feed structured JSON as input | LLM doesn't need to re-interpret → faster |
| Pre-structure evidence | Reduces output token count |

### Latency Simulation

| Scenario | Time | Notes |
|----------|------|-------|
| Simple numeric query ("Top 5 ETFs by AUM") | **6.9s** | RDB only, short answer |
| Complex multi-hop ("Ecopro subsidiary ETFs") | **11.2s** | 4-hop graph + RDB filter |
| Unanswerable ("KIMI products") | **1.7s** | Fast-path skip |
| Worst case (all 3 sources + long answer) | **13.4s** | Within 15s budget |

---

## Anti-Hallucination & Scoring Defense

### Validation Pipeline

```
Search Results
    │
    ├─► Date check: asOf ≤ 2026-07-11 ?
    │     → NO → remove result + log
    │
    ├─► Non-existent product check: KIMI, KODEX AI Robot, AAA bonds, etc.
    │     → HIT → return "Cannot be verified"
    │
    ├─► Unfounded recommendation/forecast check
    │     → qualitative "good" without data → remove
    │
    ├─► Empty result check
    │     → "No products match these criteria"
    │
    └─► Grounding check: every number in answer
          traceable to search results?
          → missing → remove sentence or "Cannot be verified"
```

### Penalty Defense Checklist

| Risk | Defense | Agent |
|------|---------|-------|
| Post-cutoff (7/11) data in answer | `asOf` filter + validation | Answer Validator |
| Non-existent products (KIMI, etc.) | Entity existence check + keyword blocklist | Answer Validator |
| Unfounded recommendations | Numeric source verification | Grounding Checker |
| Return forecasts | "forecast" keyword block | Grounding Checker |
| Sort order errors (AUM #1 missing) | Pre-defined business logic | Answer Validator |
| Response timeout | Query Router optimization + timeout | Query Router |

---

## Tech Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| **API Server** | FastAPI (Python) | Async, fast response |
| **Graph DB** | Neo4j 5.x + GDS | Existing instance: neo4j-2.yeongmin.net |
| **RDB** | PostgreSQL | Structured numeric data |
| **Vector DB** | Neo4j Native Vector Index | Integrated with GraphRAG |
| **Embedding** | multilingual-e5-large (1024d) | Korean support, free |
| **LLM-1 (Query)** | **HCX-003** | Intent Analysis, Entity Extraction, Grounding Check |
| **LLM-2 (Answer)** | **HCX-005** | Final answer generation — required by rules |
| **RDF/Ontology** | n10s (Neo4j neosemantics) | FIBO + custom MiraeAsset ontology |
| **Query Generation** | Code (pre-built templates) | No NL2SQL — speed priority |

---

## Project Structure

```
financial-product-agent/
├── api/
│   ├── main.py                  # FastAPI entrypoint
│   ├── routes/
│   │   ├── query.py             # POST /query
│   │   └── health.py            # GET /health
│   └── middleware/
│       └── timeout.py           # Response time limit (target avg 15s, max 30s)
├── agents/
│   ├── llm1/                    # Query Understanding
│   │   ├── intent_analyzer.py
│   │   ├── entity_extractor.py
│   │   └── entity_resolver.py
│   ├── ontology/                # Ontology Grounding
│   │   ├── ontology_mapper.py
│   │   ├── constraint_checker.py
│   │   └── query_planner.py
│   ├── retrieval/               # Federated Retrieval
│   │   ├── graph_retriever.py   # Neo4j Cypher
│   │   ├── sql_retriever.py     # RDB queries
│   │   ├── vector_retriever.py  # Vector search
│   │   └── result_federator.py  # Result merging
│   ├── validation/              # Answer Validation
│   │   ├── answer_validator.py  # Business rules
│   │   └── grounding_checker.py # Hallucination prevention
│   └── llm2/                    # Answer Generation
│       └── answer_generator.py  # HyperclovaX (HCX-005)
├── graph/
│   ├── schema.cypher            # Neo4j constraints/indexes
│   ├── ontology.ttl             # FIBO + MiraeAsset ontology
│   └── load_data.py             # Data ingestion script
├── db/
│   ├── models.py                # SQLAlchemy models
│   ├── business_rules.py        # YTD, sort criteria, etc.
│   └── migrations/
├── config/
│   ├── settings.py              # Environment config
│   └── prompts/                 # LLM prompt templates
│       ├── intent_analysis.txt
│       ├── entity_extraction.txt
│       ├── answer_generation.txt
│       └── ...
├── ontology/
│   ├── fibo.ttl                 # FIBO standard (subset)
│   ├── miraeasset.ttl           # MiraeAsset custom classes
│   └── constraints.yaml         # Validation rules
├── tests/
│   ├── test_intent.py
│   ├── test_retrieval.py
│   ├── test_validation.py
│   └── test_e2e.py              # 30 questions + 5 unanswerable
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## Key Cypher Patterns

### Multi-hop: Ecopro Subsidiary ETFs

```cypher
// "ETFs that include Ecopro's listed subsidiaries, and their operators"
MATCH (eco:Organization {name: '에코프로'})
MATCH (sub:Organization)-[:CLASSIFIED_AS]->(:Classification {type: 'SUBSIDIARY'})
WHERE (eco)-[:CONTROLS]->(sub)
  AND (sub)-[:LISTED_AS]->(:Listing)
MATCH (f:Fund)-[:HAS_HOLDING]->(sub)
MATCH (f)-[:MANAGED_BY]->(mgr:Organization)
RETURN DISTINCT mgr.name AS operator, f.name AS etf_name
```

### Filter + Snapshot: Quarterly-Dividend Low-Fee ETFs

```cypher
// "Top 5 domestic quarterly-dividend ETFs by lowest fee"
MATCH (f:Fund {dividendFrequency: 'QUARTERLY'})
MATCH (f)-[:HAS_UNIT]->(u:FundUnit)-[:LISTED_AS]->(l:Listing)-[:ON_MARKET]->(m:Market {code: 'KR'})
MATCH (f)-[:HAS_OBSERVATION]->(s:FundSnapshot {asOf: '2026-07-11'})
RETURN f.name, f.feeRate, s.returnYtd, l.ticker
ORDER BY f.feeRate ASC
LIMIT 5
```

### Vector + Graph: Theme Search

```cypher
// "Secondary battery theme ETFs" — Vector search then expand with Graph
CALL db.index.vector.queryNodes('fund_embedding', 10, $embedding)
YIELD node, score
WITH node AS f, score
MATCH (f)-[:TRACKS]->(b:Benchmark)
MATCH (f)-[:MANAGED_BY]->(o:Organization)
RETURN f.name, b.name AS benchmark, o.name AS operator, score
ORDER BY score DESC
LIMIT 5
```

---

## Competition Details

| Item | Detail |
|------|--------|
| **Data cutoff date** | July 11, 2026 |
| **Product domains** | Domestic bonds, ETFs, domestic/overseas mutual funds |
| **Evaluation** | 30 questions (10 easy / 10 medium / 10 hard) + 5 unanswerable |
| **Scoring** | Source code (20pts) + Tech proposal (40pts) + API answers (40pts) |
| **Response time** | Target: ~15s per question, 60s soft limit |
| **Answer rules** | Must include evidence (provenance); "Cannot be verified" for non-existent data |
| **Penalties** | Hallucinated products, unfounded recommendations, post-cutoff data, answering unanswerable questions |

---

## License

Private — MiraeAsset × Naver AI Festival 2026
