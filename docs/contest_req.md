> **Document role — requirements interpretation, not implementation status.**
> The concepts and examples below summarize the contest material and describe a
> target system. Verified capability of the supplied XLSX snapshot is assessed
> in [`current-data-capabilities.md`](current-data-capabilities.md); planned
> external sources are isolated in
> [`external-data-plan.md`](external-data-plan.md).

# 1. Core concept: Why Ontology for AI?

The presentation frames ontology not as a universal solution, but as a **semantic foundation for domains where precise meaning, relationships, and validation matter**.

> Ontology helps AI interpret complex knowledge by explicitly defining concepts, relationships, rules, and constraints.

### Main benefits

| Function                        | Purpose                                                   | Example                                                         |
| ------------------------------- | --------------------------------------------------------- | --------------------------------------------------------------- |
| **Terminology standardization** | Normalize different organizational terms into one concept | `운용사`, `자산운용사`, `AMC` → `ManagementCompany`                     |
| **Intelligent inference**       | Derive connections by following relationships/rules       | Even if only `운용사 → 상품` is stored, answer a `상품 → 운용사` question |
| **Data integrity**              | Validate business rules                                   | An illustrative versioned risk scale rejects values outside its allowed set |
| **AI reliability**              | Ground LLM answers in enterprise knowledge                | Question → evidence graph → generated answer                    |

Important qualification from the slide:

**Ontology does not have to be applied everywhere.** It should be introduced incrementally, starting with domains where semantic connections and precision are important.

---

# 2. What an Ontology actually consists of

The conceptual stack shown is:

| Layer                 | Technology         | Role                                              |
| --------------------- | ------------------ | ------------------------------------------------- |
| **Identifier**        | URI / IRI / Prefix | Give every concept a globally unique identity     |
| **Data Model**        | RDF                | Express facts as subject–predicate–object triples |
| **Schema Vocabulary** | RDFS               | Define classes and property types                 |
| **Ontology Language** | OWL                | Declare logical relationships and constraints     |
| **Validation**        | SHACL / ShEx       | Check whether actual data follows the rules       |

A useful way to interpret the stack:

* Lower layers describe **how facts are represented**.
* Higher layers describe **what those facts are allowed to mean / what is valid**.

## Serialization formats

The presentation explicitly distinguishes ontology semantics from file format.

### Turtle (`.ttl`)

* Human-readable.
* Presented as the practical default.
* Used throughout the presentation examples.

### RDF/XML

* Older standardized representation.
* Often used for inter-system exchange.

### JSON-LD

* Web/API-friendly.
* Can be manipulated naturally as JSON.

All three can represent the **same RDF semantics**.

The main message:

> **Ontology is a semantic layer, not a file format.**

---

# 3. Turning natural language into machine-checkable facts

Example sentence:

> “TIGER 코스피는 미래에셋자산운용이 운용하는 ETF이며, 위험등급은 2등급이다.”

This becomes separate RDF triples:

```text
TIGER_코스피
    isManagedBy
        미래에셋자산운용
```

and:

```text
TIGER_코스피
    hasRiskGrade
        2등급
```

So:

**1 human-readable sentence → 2 machine-readable facts.**

Then OWL/SHACL rules can validate the facts, for example:

```text
riskGrade ∈ {1, 2, 3, 4, 5}
```

This is a conceptual deck example, not a validation rule for the supplied data.
The current Korean ETF/ETN workbook contains named risk grades 1 through 6. A
production constraint must come from the applicable, versioned source
vocabulary rather than copying the example range.

and:

```text
ETF must have exactly one isManagedBy relationship
```

Valid:

```text
TIGER_코스피 isManagedBy 미래에셋자산운용
```

Invalid:

```text
TIGER_코스피 hasRiskGrade 99등급
```

The invalid value can therefore be rejected **before it is stored**.

The conceptual point is:

> Natural-language statements are decomposed into atomic facts that software can validate.

---

# 4. What the `.ttl` ontology is supposed to contain

Current-repository note: the five submitted TTL modules presently form a small
class/subclass application profile. They do not yet declare the loader's
operational relationships as `owl:ObjectProperty`/`owl:DatatypeProperty`, and
they contain no SHACL shapes. The examples in this section therefore describe
the desired semantic-contract maturity, not the current TTL feature set.

The example ontology contains three major things:

### 4.1 Class

```ttl
etf:ETF a owl:Class ;
    rdfs:label "상장지수펀드(ETF)"@ko ;
    rdfs:subClassOf fibo:FinancialInstrument ;
    owl:disjointWith etf:ETN .
```

Meaning:

* ETF is a financial instrument.
* ETF and ETN are explicitly distinct.

### 4.2 Property

```ttl
etf:hasStrategy
    a owl:ObjectProperty,
      owl:FunctionalProperty ;
    rdfs:domain etf:ETF ;
    rdfs:range etf:Strategy .
```

Meaning:

```text
ETF ──hasStrategy──> Strategy
```

### 4.3 Constraint

A SHACL shape roughly expresses:

```ttl
sh:path etf:hasStrategy ;
sh:minCount 1 ;
sh:maxCount 1 ;
sh:in (etf:Passive etf:Active) .
```

Meaning:

* An ETF must have exactly **one** strategy.
* It must be either:

  * `Passive`
  * `Active`

Hence the deck's description of TTL:

> It is not just a table/schema structure; it contains **meaning and rules together**.

---

# 5. Simplified ETF ontology model

The presentation simplifies the full ontology into a human-readable ERD-like representation.

Central entity:

```text
ETF
```

Connected concepts:

```text
AssetType
  └─ Equity

Strategy
  └─ Passive

Region
  └─ Korea

Distribution
  └─ Quarterly
```

Equivalent relationships:

```text
ETF
├─ hasAssetType ───> Equity
├─ hasStrategy ────> Passive
├─ hasRegion ──────> Korea
└─ hasDistribution -> Quarterly
```

The slide emphasizes that a real ontology can contain **hundreds or thousands of entities**, while diagrams should display only the relationships necessary for human understanding.

---

# 6. Ontology as the Semantic Layer of enterprise AI

The deck proposes this end-to-end progression:

```text
Business Goal
    ↓
Competency Question
    ↓
Ontology
    ↓
Knowledge Graph
    ↓
GraphRAG
    ↓
LLM
```

In terms of responsibilities:

```text
Business Goal
= 업무 목적

Competency Question
= AI가 답해야 하는 질문

Ontology
= 개념 + 관계 + 규칙

Knowledge Graph
= 실제 지식/데이터 연결

GraphRAG
= 근거 검색

LLM
= 최종 답변 생성
```

Four semantic functions are highlighted.

### Query Decomposition

Break a natural-language question into semantic components.

### Entity Resolution

Identify equivalent entities and ambiguous expressions.

### Answer Validation

Validate answers against business rules.

### Semantic Grounding

Anchor LLM output to company knowledge.

The slide summarizes this as:

> “LLM은 언어를 이해하고, Ontology는 의미(Semantics)를 이해한다.”

A somewhat more technically precise interpretation would be:

**The LLM handles natural-language interpretation, while the ontology supplies explicit domain semantics and constraints.**

---

# 7. Knowledge graph construction: Manual Age → Generative Age

## Traditional pipeline

```text
Raw Text
  ↓
NER / Entity Extraction
  ↓
RE / Relation Extraction
  ↓
Entity Linking
  ↓
Triples
```

Problem:

### Error propagation

An error in one stage affects later stages, so longer extraction pipelines accumulate errors.

---

## LLM-based extraction

```text
Raw Text
   ↓
  LLM
   ↓
Triples
```

This greatly simplifies extraction but introduces different risks:

### Hallucination

The model may add facts absent from the source.

### Vocabulary fragmentation

The LLM may invent slightly different relationship/property names on different runs.

Therefore:

> LLMs make extraction easier, but make **ontology-constrained schema enforcement and validation more important**, not less important.

---

# 8. Document-centric LLM vs Semantic AI

The presentation compares two retrieval approaches.

## Document-centric LLM / conventional RAG

```text
Question
  ↓
LLM
  ↓
Document Search
  ↓
Embedding
  ↓
Relevant document chunks
  ↓
LLM answer
```

Primary abstraction:

**document chunks**

---

## Semantic AI

```text
Question
  ↓
LLM / AI Agent
  ↓
Ontology interpretation
  ↓
Graph traversal/search
  ↓
RDB validation & filtering
  ↓
LLM reasoning / answer
```

Primary abstractions:

**meaning + relationships + validation**

Example query used throughout the slides:

> 국내 배당형 ETF 중 분기배당이고 운용보수 0.1% 이하인 상품을 추천해줘.

The deck's argument is that giving an LLM only relevant text chunks is fundamentally different from giving it:

```text
Ontology
+ Graph
+ RDB evidence
```

even when the underlying LLM is identical.

---

# 9. Conventional RAG and the “fragmented retrieval” problem

Conventional RAG flow:

```text
Question
  ↓
Embedding Search
  ↓
Vector DB
  ↓
Top-k
  ↓
LLM
  ↓
Answer
```

The presentation gives an ETF example where information belonging to one logical product is distributed over multiple document chunks.

### Chunk #1

Contains:

* Product name:
  `미래에셋TIGER2차전지테마증권상장지수투자신탁`
* Manager:
  `미래에셋자산운용`
* Benchmark:
  `WISE 2차전지 테마 지수`

### Chunk #2

Contains fee information:

* 판매수수료: `-`
* 총보수: `0.5%`
* 총보수·비용: `0.55%`

But **does not contain the product name**.

### Chunk #3

Contains risks:

* 주식가격변동위험
* 추적오차 위험

Again, **no product name**.

Question:

> “TIGER 2차전지테마의 보수율과 추적오차 위험을 같이 알려줘”

A vector search may retrieve chunk #1 because it contains the product name while failing to retrieve #2 and #3.

This is presented as:

### Fragmented Retrieval

The underlying evidence is related structurally, but semantic/vector similarity alone does not guarantee that all related fragments are retrieved.

---

# 10. Proposed Federated Query Architecture

Current-repository note: this is the deck's target architecture. The repository
currently implements the Neo4j graph/load/provenance path only. It has no
PostgreSQL retrieval store, document/vector index, federated router, or
natural-language evaluation endpoint. See
[`README.md`](../README.md) for the status map.

The core retrieval architecture shown is:

```text
Natural-language question
        ↓
Query Understanding
        ↓
Ontology Grounding
        ↓
Plan & Routing
     /     |      \
   RDB   Graph   Vector
    \      |      /
     Integration
     + Validation
        ↓
      Evidence
        ↓
    LLM Answer
```

## Storage/search roles

### RDB

For:

* numbers
* exact filters
* conditional search

### Graph

For:

* relationships
* connected entities
* traversal / relationship exploration

### Vector

For:

* semantic similarity
* related document retrieval

After retrieving:

```text
Integration / validation
- integrity
- permissions
- quality
```

Then:

```text
Evidence
→ LLM
→ Answer
```

The slide identifies the particularly important orchestration stages as:

```text
Decomposition
→ Routing
→ Mapping
```

and says these require a reliable **metadata layer**.

---

# 11. Example of question decomposition and routing

Question:

> 국내 배당형 ETF 중 분기배당이고 운용보수가 낮은 상품 추천해줘.

After:

```text
Query Understanding
+
Ontology Grounding
```

the presentation decomposes it approximately as follows:

| Question component | Routed to |
| ------------------ | --------- |
| 국내 ETF             | Graph     |
| 배당형                | Graph     |
| 분기배당               | Graph     |
| 운용보수               | RDB       |
| “추천”               | Vector    |

Then execution proceeds through:

```text
RDB
Graph
Vector
↓
LLM
↓
Final Answer
```

The stated division of labor is:

> **Graph finds relationships, RDB filters numbers, Vector searches meaning.**

---

# 12. Experimental findings presented in the deck

The experiment is described as:

* **Domain:** Korean ETFs
* **Benchmark:** internally created **72 questions**
* Semantic Layer components added incrementally.

Four findings are shown.

## 12.1 Executable SQL ≠ correct answer

```text
SQL execution success: ~100%
Actual answer accuracy: 45%
```

Interpretation:

Generating syntactically valid SQL is comparatively easy, but choosing the correct:

* columns
* values
* filters/conditions

is considerably harder.

---

## 12.2 Ontology should participate in execution, not merely prompt description

Ontology used as prompt description:

```text
+2.4 percentage points
```

Ontology used for runtime identification:

```text
+20 percentage points
```

Conclusion on the slide:

> Ontology should be a **runtime control layer**, not simply documentation.

---

## 12.3 Graph solves queries the RDB cannot express directly

Example:

```text
RDB:
"테마" column does not exist
→ 0 results
```

Graph:

```text
이차전지 테마 ETF
→ 36 results
```

Conclusion:

> Relationship/theme-oriented questions are naturally handled by the graph.

---

## 12.4 A single retrieval mechanism has a ceiling

Best single retriever:

```text
~66%
```

Combination:

```text
RDB + Graph
→ most stable
```

The presentation therefore argues:

> Federation is not merely optional; multiple evidence sources are necessary.

It additionally cites an NL2SQL comparison:

```text
Schema only: 8.3%
Business semantics supplied: 78.3%
```

attributed on the slide to:

**Painter et al., JAMIA Open 2025.**

---

# 13. Architecture summary from the presentation

The entire Semantic AI approach is reduced to four verbs:

```text
Define
→ Connect
→ Retrieve
→ Reason
```

### Define — Ontology

Define concepts and relationships.

### Connect — Knowledge Graph

Connect actual data.

### Retrieve — Federated Query

Find evidence appropriate to the question.

### Reason — LLM / GraphRAG

Generate an answer based on the evidence.

The presentation's central thesis is:

> AI needs to move from **document search** toward **meaning-based retrieval**.

And:

```text
Ontology       = design/specification
Knowledge Graph = connected data
Retrieval       = engine for finding the answer/evidence
```

---

# 14. Contest evaluation structure

The preliminary evaluation totals **100 points**.

| Item                         |  Weight | Main evaluation criteria                                                                 |
| ---------------------------- | ------: | ---------------------------------------------------------------------------------------- |
| **Source code**              | **20%** | implementation, reproducible development environment, README, domain ontology TTL        |
| **Technical proposal**       | **40%** | problem definition, proposed method, system architecture, expected impact, extensibility |
| **Evaluation API + answers** | **40%** | accuracy on hidden questions, evidence/reference quality, response latency               |

So technically:

```text
Implementation quality     20
Design/explanation         40
Actual QA performance      40
                         ----
                          100
```

---

# 15. Evaluation questions

The slides currently say:

```text
Total questions: 30
```

planned as:

```text
High difficulty:   10
Medium difficulty: 10
Low difficulty:    10
```

The exact number may change.

Also:

**response latency is evaluated per question.**

The precise weighting by difficulty is to be announced before preliminary evaluation.

---

# 16. “Unanswerable” questions are explicitly part of the evaluation

The deck says approximately **5 questions** are planned where the answer cannot be determined from the provided data.

For these:

* Do **not hallucinate** an answer.
* Generating an unsupported answer results in a penalty.
* Correct behavior includes:

  * explicitly stating **“확인할 수 없음”**, or
  * asking for the missing condition/information where appropriate.

This is a significant design requirement because the system needs an explicit **abstention / answerability-detection path**.

---

# 17. Required source-code submission

Submission package:

```text
Implementation source code
+
reproducible development environment
  e.g. requirements.txt
+
README.md
+
domain-specific Ontology.ttl
```

The ontology files are **new mandatory deliverables**.

Current-repository note: the five required modular TTL files, the
`pyproject.toml`/`uv.lock` environment, and the repository-root `README.md` are
present. The DSL compiler and evaluation API described later remain to be
implemented.

## Required domain ontology files

```text
국내채권
ontology/bond_kr.ttl

국내 ETF
ontology/etf_kr.ttl

해외 ETF
ontology/etf_gl.ttl

공모펀드
ontology/fund_pub.ttl
```

A shared upper-level ontology may be separated into:

```text
ontology/common.ttl
```

The repository currently has all five modular files. Their verified scope and
loaded class counts are documented in
[`data-loading.md`](data-loading.md#fibo-application-profile).

For example a common:

```text
fp:Product
```

class.

## Suggested repository structure

```text
repo/
├── src/                     # implementation source
├── ontology/
│   ├── common.ttl           # common upper-level classes
│   ├── bond_kr.ttl          # Korean bonds
│   ├── etf_kr.ttl           # Korean ETFs
│   ├── etf_gl.ttl           # global ETFs
│   └── fund_pub.ttl         # public funds
├── requirements.txt
└── README.md
```

Example shown for `etf_gl.ttl` is roughly:

```ttl
@prefix fp: <http://mafest.ai/product#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

fp:ForeignETFs a owl:Class ;
    rdfs:subClassOf fp:ETF ;
    rdfs:label "해외 ETF"@ko .

fp:expenseRatio a owl:DatatypeProperty ;
    rdfs:domain fp:ETF ;
    rdfs:range xsd:decimal .
```

---

# 18. Technical proposal: recommended structure

Format:

**free-form, PDF recommended.**

The recommended outline is:

### 1. Overall architecture and differentiated functions

Explain:

* overall system architecture
* differentiation / unique points

### 2. Proposed methodology

Explicitly answer:

1. **What specialized data did you collect, and how did you clean/process it?**
2. **What ontology engineering did you apply?**
3. **What retrieval methodology did you select, and why was it designed that way?**

### 3. System architecture

Suggested pipeline:

```text
Ingestion
→ Indexing
→ Retrieval
→ Generation
```

### 4. Main functional flow

```text
Data collection
→ Ontology design
→ Graph construction
→ Retrieval
```

### 5. Expected effects and scalability

Describe:

* where the system can be applied operationally
* how it can expand to additional financial-product categories

### 6. Appendix

Include:

* ontology schema
* evaluation reproduction procedure

---

# 19. Evaluation API specification

Current-repository note: the API below is a requirement, not an implemented
endpoint. [`query-dsl-spec.md`](query-dsl-spec.md) and
[`query-dsl.schema.json`](query-dsl.schema.json) specify a proposed internal
read-only query contract, but its compiler and the evaluation API remain to be
built.

## Endpoint

```http
GET /answer
```

Content type:

```http
application/json; charset=utf-8
```

Operating period shown:

```text
09.07 ~ 09.20
```

The endpoint should remain continuously available during that period.

Recommended response time:

```text
≤ 60 seconds per question
```

---

## Request schema

| Parameter     | Type   | Required | Description                                         |
| ------------- | ------ | -------- | --------------------------------------------------- |
| `question_id` | string | yes      | Organizer-provided question ID, e.g. `Q-001`        |
| `question`    | string | yes      | Original evaluation question; URL encoding required |

Example:

```bash
curl -G "https://[endpoint]/answer" \
  --data-urlencode "question_id=Q-001" \
  --data-urlencode "question=평가 질의"
```

Python:

```python
requests.get(
    url,
    params={
        "question_id": "Q-001",
        "question": "평가 질의",
    },
)
```

Additional requirements:

* No authentication header.
* No POST body.
* Unknown/unexpected parameters must **not cause HTTP 500**.

---

# 20. API response schema

Expected:

```http
200 OK
Content-Type: application/json
```

Fields:

| Field               | Type   | Required | Meaning                                             |
| ------------------- | ------ | -------- | --------------------------------------------------- |
| `question_id`       | string | yes      | Return request value unchanged                      |
| `question`          | string | yes      | Return request value unchanged                      |
| `retrieved_context` | string | yes      | Tables/documents used as evidence                   |
| `think_trace`       | string | yes      | Reasoning/tool-use process as required by evaluator |
| `answer`            | string | yes      | Final answer                                        |

Example from the slide is approximately:

```json
{
  "question_id": "Q-001",
  "question": "평가 질의 원문",
  "retrieved_context": "해외ETF마스터 · 2026-07-11",
  "think_trace": "조건 파싱 → 필터 → 정렬 → 상위 3종",
  "answer": "총보수 0.03%인 A... (근거: 해외ETF마스터)"
}
```

For an unanswerable question, the endpoint must still return:

```text
HTTP 200
+
same JSON schema
```

rather than failing.

For implementation purposes, I would interpret `think_trace` as an **audit trace of routing/retrieval/tool actions**, e.g. `entity resolution → graph query → filter → evidence check`, rather than storing unrestricted hidden model reasoning.

---

# 21. Example evaluation questions

## Normal questions

| # | Example question                          | Category | Difficulty |
| - | ----------------------------------------- | -------- | ---------- |
| 1 | 현재 판매 가능한 회사채권 중 AA- 이상 종목 알려줘            | 채권       | 하          |
| 2 | 국민성장펀드의 구조와 투자전략 동향 등 찾아서 알려줘             | 펀드       | 중          |
| 3 | 캠브리콘이 편입된 중국 반도체 ETF를 알려줘                 | 해외 ETF   | 중          |
| 4 | 최근 6개월 동안 우주항공 테마와 연결 이력이 있는 관련 ETF를 정리해줘 | ETF      | 상          |
| 5 | 에코프로의 자회사를 편입한 ETF 중 순자산이 큰 상품의 위험요인 알려줘  | 국내 ETF   | 상          |

These examples are quite informative because they imply several query capabilities:

```text
exact filters
+ entity relationships
+ holdings
+ corporate relationships
+ temporal relationships
+ ranking
+ risk-document lookup
+ multi-hop joins
```

They do not imply that all of those evidence types are present in the supplied
XLSX files. The evidence-by-question assessment is in
[`sample_questions.md`](sample_questions.md).

---

# 22. Example deliberately unanswerable questions

These should **not** receive fabricated answers.

| # | Example               | Category |
| - | --------------------- | -------- |
| 1 | 신용등급 AAAA인 채권 찾아줘     | 채권       |
| 2 | Kimi 관련 투자 상품 있어?     | 전체       |
| 3 | KODEX AI로봇 ETF 정보 알려줘 | ETF      |

The evaluation is therefore testing not only retrieval accuracy but also:

```text
answerability detection
+
evidence sufficiency
+
abstention
```

---

# 23. The whole presentation condensed into one system model

Removing the explanatory duplication, the architecture the slides are advocating is essentially:

```text
                    ┌──────────────────────┐
                    │   Domain Ontology    │
                    │ classes / relations  │
                    │ rules / constraints  │
                    └──────────┬───────────┘
                               │
Question                       │ semantic grounding
   │                           │
   ▼                           ▼
┌───────────────┐     ┌─────────────────┐
│ Query         │────▶│ Query Planner / │
│ Understanding │     │ Router          │
└───────────────┘     └────────┬────────┘
                               │
                ┌──────────────┼──────────────┐
                ▼              ▼              ▼
             Graph            RDB           Vector
          relationships   exact values     documents
          / traversal      / filters       / semantics
                │              │              │
                └──────────────┼──────────────┘
                               ▼
                    ┌───────────────────┐
                    │ Evidence merge &  │
                    │ validation        │
                    └─────────┬─────────┘
                              ▼
                            LLM
                              │
                              ▼
                     grounded answer
                     + evidence/context
```

With ingestion roughly:

```text
Raw financial data / documents
            ↓
Extraction / normalization
            ↓
Ontology-constrained mapping
            ↓
Validation
            ↓
Knowledge Graph / structured stores / document index
```

And the philosophy is:

```text
Define → Connect → Retrieve → Reason
```

---

# 24. What the judges are implicitly asking teams to demonstrate

Combining the evaluation slides with the technical slides, the actual task can be distilled to six capabilities:

1. **Model financial-product semantics explicitly** using the required four domain ontologies.
2. **Connect heterogeneous financial data** into those semantics instead of treating everything as isolated text.
3. **Understand and decompose complex natural-language financial questions.**
4. **Retrieve evidence using the appropriate mechanism** rather than forcing every question through one retrieval engine.
5. **Generate grounded answers with provenance.**
6. **Recognize when the supplied data cannot answer a question and abstain correctly.**

That is probably the cleanest single interpretation of all 18 images.

One particularly important distinction in the deck is that **Ontology, Knowledge Graph, retrieval stores, and LLM are not interchangeable components**:

```text
Ontology       → defines meaning
Knowledge Graph → instantiates relationships
RDB             → stores/filter exact structured values
Vector index    → retrieves semantic document evidence
LLM             → interprets questions and synthesizes answers
```
