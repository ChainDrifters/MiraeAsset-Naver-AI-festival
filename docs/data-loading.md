# Financial-product graph load

This document records how the 2026-07-11 Excel snapshots in `금융상품/` were
loaded into the Compose-managed `neo4j-2` database on 2026-08-04.

For a beginner-oriented explanation of the finance concepts, every application
node and relationship, and the detailed row-to-graph conversion, see
[`graph-model-guide.md`](graph-model-guide.md).

## Result

The load completed successfully and is idempotent for the same snapshot.

| Metric | Loaded |
|---|---:|
| Source rows | 145,393 |
| Linked, non-rejected source rows | 145,392 |
| Rejected source rows | 1 |
| Bonds | 42,394 |
| Deduplicated funds | 17,877 |
| Deduplicated fund units | 17,877 |
| ETNs | 591 |
| Listings | 32,303 |
| Dated observations | 67,825 |
| Total nodes | 472,165 |
| Total relationships | 1,236,466 |
| Duplicate `Resource.uri` values | 0 |

The relationship total includes ten normalized `SUBCLASS_OF` links added after
the initial load report. The one rejected record is public-fund Excel row 84,563,
whose columns are visibly shifted and whose `itm_no` value is `"`.

Per-source validation:

| Dataset | Source rows | Canonical-link coverage | Notes |
|---|---:|---:|---|
| Domestic bonds | 42,394 | 42,394 | All product numbers unique |
| Korean ETF/ETN | 1,734 | 1,734 | 1,202 ETFs and 532 ETNs |
| Overseas ETF/ETN | 5,646 | 5,646 | 5,587 ETF rows and 59 ETNs |
| Public funds | 95,619 | 95,618 | One malformed row quarantined |

The overseas ETF rows resolve to 5,537 distinct ETF fund/unit resources. Fifty
securities have two listings, accounting for the difference between ETF rows and
canonical ETF entities.

## Runtime and n10s installation

The target is the `neo4j-2` service defined in `docker-compose.yaml`. The other
running instance, `neo4j-1`, was not modified.

Installed components:

- Neo4j Community `2026.06.0`
- Neosemantics `2025.06.1`
- n10s JAR: `plugins/neosemantics-2025.06.1.jar`
- JAR SHA-256: `4c461087e08405c7cb472ecfefc043e9e8ed93628ed74988e4fda1f1bac54b3e`
- uv `0.11.3`
- Python `3.14.3` in `.venv`
- Neo4j Python driver `6.2.0`

The n10s JAR metadata says it was built against Neo4j `2025.06.2`. It has been
runtime-tested here against Neo4j `2026.06.0`: the database starts healthy,
55 `n10s.*` procedures are registered, the RDF `/rdf/ping` endpoint responds,
and the local ontology imports successfully. Recheck compatibility before any
future Neo4j upgrade.

The Compose service bind-mounts `./plugins` into `/plugins` and enables:

```yaml
NEO4J_dbms_security_procedures_unrestricted: "n10s.*"
NEO4J_dbms_security_procedures_allowlist: "n10s.*"
NEO4J_server_unmanaged__extension__classes: "n10s.endpoint=/rdf"
```

Installation/restart command:

```bash
docker compose up -d --force-recreate neo4j-2 neo4j-proxy-2
```

Procedure verification:

```cypher
SHOW PROCEDURES YIELD name
WHERE name STARTS WITH 'n10s.'
RETURN count(*) AS procedureCount;
```

## Python environment

Dependencies are declared in `pyproject.toml` and locked in `uv.lock`. Do not
install packages directly with `pip`.

```bash
uv sync
uv run mirae-graph dry-run
uv run mirae-graph prepare
uv run mirae-graph load --batch-size 500
uv run mirae-graph validate
```

Connection values are read from `.env`:

- `NEO4J_PASSWORD`
- `NEO4J_BOLT_PORT`
- optional `NEO4J_USER`, `NEO4J_URI`, and `NEO4J_DATABASE`

`dry-run` reads and transforms every row but does not connect to or mutate
Neo4j. `prepare` initializes n10s, imports the ontology profile, and creates
indexes. `load` runs `prepare`, upserts all requested files, and validates the
result. A subset can be selected, for example:

```bash
uv run mirae-graph load --dataset domestic_bonds
uv run mirae-graph load \
  --dataset domestic_etf_etn \
  --dataset overseas_etf_etn
```

## Load architecture

The graph has source, canonical, semantic, and observational layers:

```text
(SourceDataset)-[:HAS_FIELD]->(FieldDefinition)
       ^
       |
  (SourceFile)<-[:IN_FILE]-(SourceRecord)-[:DESCRIBES]->(canonical entity)

(Fund)-[:HAS_UNIT]->(FundUnit:Security)-[:LISTED_AS]->(Listing)
                                      |                 |
                                      |                 +--[:ON_MARKET]->(Market)
                                      |                 +--[:HAS_OBSERVATION]->(MarketSnapshot)
                                      +--[:HAS_IDENTIFIER]->(Identifier)
                                      +--[:HAS_OBSERVATION]->(FundSnapshot)

(Bond:Security)-[:ISSUED_BY]->(Organization)
       +--[:HAS_OBSERVATION]->(BondSnapshot)

(canonical entity)-[:INSTANCE_OF]->(OntologyClass)-[:SUBCLASS_OF]->(...)
```

Every nonblank source value is retained as a property on `SourceRecord`, using
the original column name. Canonical nodes contain normalized fields used for
queries. Consequently, uncertain semantics can be corrected later without
rereading or losing the source assertion.

The source schema workbooks add 207 `FieldDefinition` nodes containing column
order, source type, Korean name, and example where supplied. The derived
`axis_*` sample classifications were not treated as authoritative source data.

## FIBO application profile

The loader does not import all of FIBO. It imports the deliberately small
`ontology/mirae-financial-products.ttl` profile using
`n10s.onto.import.inline`. The profile contains 63 parsed ontology triples and
references these main FIBO concepts:

- `Bond`
- `DebtInstrument`
- `ExchangeTradedFund`
- `MutualFund`
- `FundUnit`
- `TradableFundUnit`
- `NonTradableFundUnit`
- `ListedSecurity`
- `Listing`

It adds the local `ExchangeTradedNote` class as a subclass of FIBO
`DebtInstrument` and `ListedSecurity`. It does not claim complete ETN payoff
semantics.

n10s is configured with full vocabulary URIs (`handleVocabUris: KEEP`), arrays
for multivalued properties, language-tag preservation, and custom datatype
preservation. n10s therefore retains its expanded physical labels and `SCO`
relationship. The loader adds stable `OntologyClass` and `SUBCLASS_OF` aliases
for ordinary Cypher and GraphRAG traversal; it does not remove the n10s form.

Canonical entities retain their primary alignment in `fiboClassUri` and connect
to one or more ontology classes through `INSTANCE_OF`.

## Identity and mapping rules

### Domestic bonds

- `PD_NO` identifies the canonical bond and is treated as ISIN when it matches
  the ISIN shape.
- `PD_PBCM` creates the issuer organization by normalized name.
- `PD_EXG_MKT = 장내` creates a listing in a generic Korean bond market.
- Issue balance is `issueOutstandingAmount`, not per-unit nominal value.
- Issue date, maturity, coupon, currency, names, and categories are normalized
  onto the bond.
- Price, yield, duration, convexity, buyability, and credit-grade fields go into
  one dated `BondSnapshot` per bond.
- Ambiguous fields such as `DUR`, `COV`, and `APPLIED_YIELD` use names such as
  `durationRaw` rather than claiming a more specific analytic subtype.

### Korean ETFs and ETNs

- `pd_grp_no` splits 1,202 ETF rows from 532 ETN rows.
- `pd_itm_no` is the security/ISIN identity.
- `pd_itm_no_ma` is the listing ticker identity.
- ETFs create separate `Fund`, `FundUnit`, and `Listing` nodes.
- ETNs create an `ExchangeTradedNote` and a listing, without a fund node.
- Manager/issuer, benchmark, strategy, fees, classifications, offering status,
  market snapshot, and fund snapshot are separated.
- The single row without market information has no listing; this explains
  1,733 listings for 1,734 rows.

### Overseas ETFs and ETNs

- `pd_isin_cd` identifies a security when populated.
- Market plus ticker identifies the listing.
- Multiple rows with one ISIN become one security with multiple listings.
- Rows lacking ISIN use a source-specific market/ticker identity.
- `pd_grp_no` and `cu_etn_yn` distinguish ETFs from ETNs.

### Public funds

- `itm_no` is a vendor source key. Although it resembles an ISIN, it is not
  asserted as an ISIN because 17,360 rows have valid 12-character keys ending
  in `M`.
- The 95,618 valid rows collapse to 11,138 fund/unit identities.
- Each `prfd_attr_cd` becomes a repeatable `Classification` relationship rather
  than a duplicate fund.
- `rptt_ksd_itm_no` is retained as an identifier but is not yet used to merge
  share classes into a shared parent fund; its semantics require confirmation.
- `exchdg_yn` is mapped as currency-hedging status, following the schema
  workbook's Korean field label. It is not interpreted as “exchange traded.”
- ETF status is inferred only when the Korean product name contains `상장지수`
  or the name/abbreviation contains `ETF`. This produced 175 public-fund
  listings and is explicitly stored as a name-based heuristic.
- Sale state belongs to an `Offering`, while AUM and returns belong to a dated
  `FundSnapshot`.
- `or_co_xtn_itt_cd` creates an organization by source code. No organization
  name is invented.

## Database constraints and indexes

The canonical identity guarantee is:

```cypher
CREATE CONSTRAINT resource_uri IF NOT EXISTS
FOR (resource:Resource)
REQUIRE resource.uri IS UNIQUE;
```

Additional indexes:

- Composite range index on `SourceRecord(dataset, rowNumber)`
- Range index on `Identifier.value`
- Range index on `Observation.asOf`
- Full-text `financial_entity_search` index over names and tickers on bonds,
  funds, securities, organizations, and benchmarks

## Validation and example queries

Run the built-in validation:

```bash
uv run mirae-graph validate
```

Full-text product lookup:

```cypher
CALL db.index.fulltext.queryNodes('financial_entity_search', 'KODEX 200')
YIELD node, score
RETURN labels(node), node.name, node.shortName, score
ORDER BY score DESC
LIMIT 10;
```

Inspect a fund, unit, listing, market, and price snapshot:

```cypher
MATCH (fund:Fund)-[:HAS_UNIT]->(unit:FundUnit)-[:LISTED_AS]->(listing:Listing)
MATCH (listing)-[:ON_MARKET]->(market:Market)
OPTIONAL MATCH (listing)-[:HAS_OBSERVATION]->(snapshot:MarketSnapshot)
RETURN fund.name, unit.uri, listing.ticker, market.name,
       snapshot.closePrice, snapshot.asOf
LIMIT 20;
```

Find securities represented by multiple listings:

```cypher
MATCH (security:Security)-[:LISTED_AS]->(listing:Listing)
WITH security, collect(listing) AS listings
WHERE size(listings) > 1
RETURN security.name,
       [(listing IN listings) | [listing.marketCode, listing.ticker]] AS venues;
```

Trace an answer back to its exact Excel row:

```cypher
MATCH (record:SourceRecord)-[:DESCRIBES]->(entity:Entity)
WHERE entity.uri = $entityUri
MATCH (record)-[:IN_FILE]->(file:SourceFile)
RETURN record.dataset, record.rowNumber, file.name, file.sha256;
```

Use the ontology hierarchy:

```cypher
MATCH (entity:Entity)-[:INSTANCE_OF]->(type:OntologyClass)
OPTIONAL MATCH path = (type)-[:SUBCLASS_OF*1..4]->(parent:OntologyClass)
RETURN entity.name, type.name, [node IN nodes(path) | node.name] AS hierarchy
LIMIT 20;
```

## Reruns and later snapshots

The loader uses deterministic URIs and `MERGE`, so rerunning the same snapshot
does not duplicate resources or relationships. A later dated workbook creates
new source-file, source-record, and observation identities while updating the
canonical entity's current descriptive properties.

The loader is append/upsert oriented. It does not delete entities that disappear
from a later source file. If absence must mean deletion or inactivation, add a
separate, reviewed reconciliation step rather than changing this evidence-
preserving loader.

Embeddings and vector indexes are not part of this load. They should be added in
a separate GraphRAG enrichment step over product summaries and document chunks;
numeric/date filtering should continue to use Cypher over canonical properties
and observations.
