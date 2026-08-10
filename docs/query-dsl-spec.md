# Financial-product query DSL specification

Status: **version 1.0 design contract**. This document specifies the language a
query planner and Neo4j compiler should implement. The repository does not yet
contain that compiler or a DSL execution endpoint.

The machine-readable request grammar is
[`query-dsl.schema.json`](query-dsl.schema.json). The graph model behind the
language is documented in [`graph-model-guide.md`](graph-model-guide.md), and
the original Excel fields are documented in
[`xlsx-field-reference.md`](xlsx-field-reference.md).

The data-dependent answerability baseline is
[`current-data-capabilities.md`](current-data-capabilities.md). A syntactically
valid DSL request is not necessarily supported by populated source evidence.

## Purpose

The DSL is a read-only, JSON query language for the financial-product graph. It
sits between a natural-language planner and Neo4j:

```text
question -> entity/intent extraction -> DSL -> validation -> Cypher -> evidence
```

It is intentionally smaller than Cypher. A planner may choose supported fields,
operators, relations, and limits, but cannot supply executable Cypher text. This
makes generated queries easier to validate, cache, test, and audit.

Version 1.0 is intended to support:

- exact product and identifier lookup;
- text search over products, organizations, and benchmarks;
- graph relationship filters such as manager, issuer, market, and benchmark;
- numeric/date filters and ranking over normalized product observations;
- aggregation;
- bounded neighborhood and ontology traversal;
- exact source-row access when a fact was not normalized; and
- source-file and row-level provenance for GraphRAG.

It does not define mutations, arbitrary graph patterns, arbitrary expressions,
or unrestricted Cypher passthrough.

The words **MUST**, **SHOULD**, and **MAY** below state required, recommended,
and optional behavior for an implementation.

## Minimal example

This finds saleable ETFs with a fee no greater than 0.10 percentage points,
ranks them by their latest AUM, and requests source-row evidence:

```json
{
  "dsl_version": "1.0",
  "query_id": "Q-001",
  "operation": "find",
  "entity": "etf",
  "select": [
    "entity.uri",
    "entity.name",
    "fund.fee_rate",
    "fund_metric.assets_under_management",
    "fund_metric.as_of"
  ],
  "where": {
    "all": [
      {
        "field": "offering.available_for_sale",
        "op": "eq",
        "value": true
      },
      {
        "field": "fund.fee_rate",
        "op": "lte",
        "value": 0.1
      }
    ]
  },
  "observations": {
    "fund": {
      "mode": "latest"
    }
  },
  "order_by": [
    {
      "field": "fund_metric.assets_under_management",
      "direction": "desc",
      "nulls": "last"
    }
  ],
  "page": {
    "limit": 10,
    "offset": 0
  },
  "evidence": {
    "mode": "rows",
    "required": true,
    "max_source_rows_per_result": 5
  }
}
```

Rates in these feeds are stored in percentage points. The value `0.1` above
means 0.10%, not 10% and not the decimal fraction 0.001.

This example demonstrates language semantics, not complete-market coverage:
`cu_charge_rt` is populated for only 217 of 1,734 domestic ETF/ETN rows in the
current snapshot. A returned ranking must disclose that coverage limitation.

## Processing order

An implementation MUST evaluate a request in this order:

1. Validate the JSON structure against `query-dsl.schema.json`.
2. Validate entity, field, relationship, operator, and type combinations against
   this specification's semantic catalog.
3. Bind the logical entity to one or more fixed graph patterns.
4. Apply exact identity resolution and/or text-search candidate generation.
5. Select observations according to `observations`.
6. Apply `where` predicates to the selected observations and relationships.
7. Project or aggregate, then order, then paginate.
8. Attach provenance and enforce the requested evidence policy.

The ordering of steps 5 and 6 is important: a `latest` query means “select the
latest observation, then test its value,” not “find the latest historical
observation that happens to satisfy the filter.”

## Request object

| Member | Required | Meaning |
|---|---:|---|
| `dsl_version` | yes | Exact language version; version 1 requests use `"1.0"`. |
| `query_id` | no | Caller-supplied correlation ID, returned unchanged. |
| `operation` | yes | `find`, `aggregate`, `neighbors`, or `provenance`. |
| `entity` | yes | Logical starting entity from the entity catalog. |
| `select` | no | Fields to return. Defaults to `entity.uri`, `entity.kind`, and `entity.name`. |
| `text_search` | no | Candidate lookup through exact, contains, or Neo4j full-text search. |
| `where` | no | Recursive Boolean predicate tree. |
| `observations` | no | Selection rules for dated fund, market, and bond observations. |
| `group_by` | aggregate only | Fields used to group aggregate results. |
| `aggregates` | aggregate only | Aggregate calculations. At least one is required for `aggregate`. |
| `traversal` | neighbors only | Allowed relationship families and bounded traversal depth. |
| `order_by` | no | Stable result ordering over selected or aggregate fields. |
| `page` | no | `limit` and `offset`; defaults to 20 and 0. |
| `evidence` | no | Provenance detail and enforcement. Defaults to summary evidence required. |
| `options` | no | Execution controls such as deduplication and timeout. |

Unknown members MUST be rejected. Missing optional members use the defaults
specified here; clients should not need to serialize defaults.

## Operations

### `find`

Returns flat projected rows. To avoid accidental multiplication, the compiler
MUST return distinct rows by default. Selecting a many-valued field such as
`classification.code`, an interval of observations, or individual source rows
may intentionally produce more than one row per root entity.

### `aggregate`

Returns grouped calculations. Supported functions are:

| Function | Field required | Result |
|---|---:|---|
| `count` | no | Number of result rows |
| `count_distinct` | yes | Number of distinct non-null field values |
| `min` | yes | Minimum non-null value |
| `max` | yes | Maximum non-null value |
| `avg` | yes | Average non-null numeric value |
| `sum` | yes | Sum of non-null numeric values |

Each aggregate requires a safe result alias matching
`^[A-Za-z_][A-Za-z0-9_]*$`. `avg` and `sum` MUST be rejected for nonnumeric
fields.

### `neighbors`

Starts with roots selected by `text_search` and/or `where`, then follows only
the relationship families listed in `traversal.relations`. The result can be
returned as paths or deduplicated nodes. `max_depth` is capped at 4.

This operation is for relationship exploration, not for expressing unrestricted
Cypher. Every hop still has to match the relation catalog and a valid domain and
range.

### `provenance`

Returns source records and source files supporting the selected roots. This is
equivalent to the logical path:

```text
entity <- described_by - source_record - in_file -> source_file
```

It MUST not return unrelated source rows merely because they came from the same
file.

## Logical entity catalog

The DSL exposes business-level roots rather than requiring the caller to know
all physical Neo4j labels.

| DSL entity | Logical result grain | Neo4j binding |
|---|---|---|
| `product` | Buyable/identifiable product | Union of `Bond`, `FundUnit`, and `ExchangeTradedNote`; abstract `Fund` nodes are excluded to prevent duplicates. |
| `security` | Security | Union of nodes carrying the `Security` label. |
| `bond` | Bond security | `(root:Bond)` |
| `etf` | ETF unit/share class | `(fund:Fund)-[:HAS_UNIT]->(root:FundUnit)` where the fund is typed as FIBO `ExchangeTradedFund`. |
| `etn` | Exchange-traded note | `(root:ExchangeTradedNote)` |
| `mutual_fund` | Non-ETF public-fund unit/share class | `(fund:Fund)-[:HAS_UNIT]->(root:FundUnit)` where the fund is typed as FIBO `MutualFund`. |
| `fund` | Abstract fund vehicle | `(root:Fund)`; this may have one or more units. |
| `fund_unit` | Fund unit/share class | `(root:FundUnit)` |
| `organization` | Manager or issuer | `(root:Organization)` |
| `benchmark` | Tracked index/reference | `(root:Benchmark)` |
| `listing` | Market-specific trading line | `(root:Listing)` |
| `source_record` | Exact input row | `(root:SourceRecord)` |
| `ontology_class` | FIBO/local class | `(root:OntologyClass)` |

`entity.kind` is derived, not read from a single stored property. Its normalized
values are `bond`, `etf`, `etn`, `mutual_fund`, `fund`, `fund_unit`,
`organization`, `benchmark`, `listing`, `source_record`, and `ontology_class`.

For `product`, `security`, `etf`, and `mutual_fund`, the compiler MAY use a
`CALL { ... UNION ... }` implementation, but every branch MUST produce the same
logical field names and value types.

## Projection syntax

A projection is either a field name or a field-plus-alias object:

```json
[
  "entity.name",
  {
    "field": "listing.ticker",
    "as": "ticker"
  }
]
```

Without `as`, the response key is the complete field name. Alias names MUST use
the same safe identifier rule as aggregate aliases. Duplicate output keys MUST
be rejected.

An object projection may also carry a `scope` when more than one related node
of the same family is bound. Scope behavior is defined under the predicate
language.

## Field catalog

DSL names use `snake_case`; physical Neo4j properties use the existing
`camelCase` names. The compiler MUST map only the fields below and MUST NOT
interpolate an unrecognized name into Cypher.

### Common entity fields

| DSL field | Type | Physical value or derivation |
|---|---|---|
| `entity.uri` | string | `Resource.uri` |
| `entity.kind` | string | Derived from logical binding/type |
| `entity.name` | string | `name` |
| `entity.short_name` | string | `shortName` |
| `entity.english_name` | string | `englishName` |
| `entity.currency` | string | `currency` |
| `entity.dataset` | string | `dataset` |
| `entity.source_item_number` | string | `sourceItemNumber`, or bond `sourceProductNumber` |
| `entity.fibo_class_uri` | string | `fiboClassUri` |
| `entity.updated_at` | datetime | `updatedAt` |

Not every kind has every common field. A missing property is null/unknown; it is
not an empty string, zero, or false.

### Bond fields

| DSL field | Type | Neo4j property |
|---|---|---|
| `bond.country_code` | string | `Bond.countryCode` |
| `bond.currency` | string | `Bond.currency` |
| `bond.issue_outstanding_amount` | number | `Bond.issueOutstandingAmount` |
| `bond.issue_date` | date | `Bond.issueDate` |
| `bond.maturity_date` | date | `Bond.maturityDate` |
| `bond.coupon_rate` | number | `Bond.couponRate` |
| `bond.exchange_market` | string | `Bond.exchangeMarket` |
| `bond.issuer_display_name` | string | `Bond.issuerDisplayName` |

### Fund and fund-unit fields

For an ETF, mutual fund, or fund-unit root, `fund.*` fields are read from its
parent `Fund`. For a `fund` root they are read directly.

| DSL field | Type | Neo4j property |
|---|---|---|
| `fund.strategy` | string | `Fund.strategy` |
| `fund.base_index_name` | string | `Fund.baseIndexName` |
| `fund.leverage_factor` | number | `Fund.leverageFactor` |
| `fund.fee_rate` | number | `Fund.feeRate` |
| `fund.other_fee_rate` | number | `Fund.otherFeeRate` |
| `fund.index_replication_method` | string | `Fund.indexReplicationMethod` |
| `fund.index_tracking` | boolean | `Fund.indexTracking` |
| `fund.inverse_or_short` | boolean | `Fund.inverseOrShort` |
| `fund.country_code` | string | `Fund.countryCode` |
| `fund.currency_hedged` | boolean | `Fund.currencyHedged` |
| `fund.overseas_fund` | boolean | `Fund.overseasFund` |
| `fund.private_fund_description` | string | `Fund.privateFundDescription` |
| `fund.public_private_description` | string | `Fund.publicPrivateDescription` |
| `fund.exchange_traded_classification` | string | `Fund.exchangeTradedClassification` |
| `fund_unit.representative_ksd_item_number` | string | `FundUnit.representativeKsdItemNumber` |

Exchange-product ETNs store the common strategy and fee properties directly on
the ETN. When `entity` is `etn`, the same semantic fields are addressed as
`fund.strategy`, `fund.base_index_name`, `fund.leverage_factor`,
`fund.fee_rate`, `fund.other_fee_rate`, `fund.index_replication_method`,
`fund.index_tracking`, and `fund.inverse_or_short`. This deliberate logical
alias lets a cross-product query use one vocabulary.

### Identifier, organization, benchmark, classification, and listing fields

| DSL field | Type | Graph binding/property |
|---|---|---|
| `identifier.uri` | string | `HAS_IDENTIFIER -> Identifier.uri` |
| `identifier.scheme` | string | `Identifier.scheme` |
| `identifier.value` | string | `Identifier.value` |
| `manager.uri` | string | `MANAGED_BY -> Organization.uri` |
| `manager.name` | string | Manager `Organization.name` |
| `manager.code` | string | Manager `Organization.code` |
| `manager.identity_scheme` | string | Manager `Organization.identityScheme` |
| `issuer.uri` | string | `ISSUED_BY -> Organization.uri` |
| `issuer.name` | string | Issuer `Organization.name` |
| `issuer.code` | string | Issuer `Organization.code` |
| `issuer.identity_scheme` | string | Issuer `Organization.identityScheme` |
| `benchmark.uri` | string | `TRACKS -> Benchmark.uri` |
| `benchmark.name` | string | `Benchmark.name` |
| `benchmark.english_name` | string | `Benchmark.englishName` |
| `classification.uri` | string | `CLASSIFIED_AS -> Classification.uri` |
| `classification.scheme` | string | `Classification.scheme` |
| `classification.code` | string | `Classification.code` |
| `classification.name` | string | `Classification.name` |
| `listing.uri` | string | `LISTED_AS -> Listing.uri` |
| `listing.ticker` | string | `Listing.ticker` |
| `listing.market_code` | string | `Listing.marketCode` |
| `listing.market_name` | string | `Listing.marketName` |
| `listing.listing_date` | date | `Listing.listingDate` |
| `listing.listing_price` | number | `Listing.listingPrice` |
| `listing.listed_share_count` | number | `Listing.listedShareCount` |
| `listing.inferred_from_name` | boolean | `Listing.listingInferredFromName` |
| `market.uri` | string | `Listing-[:ON_MARKET]->Market.uri` |
| `market.code` | string | `Market.code` |
| `market.name` | string | `Market.name` |

For a fund-unit root, `manager` and `benchmark` are reached through the parent
fund. For an ETN, `manager` is not a valid semantic relation; the available
provider was modeled as `issuer`.

### Offering fields

The physical relationship is `(Offering)-[:OFFERS]->(product)`, but the DSL
exposes it naturally from the product as `has_offering`.

| DSL field | Type | Neo4j property |
|---|---|---|
| `offering.uri` | string | `Offering.uri` |
| `offering.available_for_sale` | boolean | `Offering.availableForSale` |
| `offering.available_through_firm` | boolean | `Offering.availableThroughFirm` |
| `offering.trading_halted` | boolean | `Offering.tradingHalted` |
| `offering.sale_status` | string | `Offering.saleStatus` |
| `offering.sale_control_type` | string | `Offering.saleControlType` |
| `offering.as_of` | date | `Offering.asOf` |

### Bond observation fields

| DSL field | Type | `BondSnapshot` property |
|---|---|---|
| `bond_metric.as_of` | date | `asOf` |
| `bond_metric.buy_yield` | number | `buyYield` |
| `bond_metric.corporate_pretax_yield` | number | `corporatePretaxYield` |
| `bond_metric.corporate_after_tax_yield` | number | `corporateAfterTaxYield` |
| `bond_metric.after_tax_yield` | number | `afterTaxYield` |
| `bond_metric.preferential_tax_yield` | number | `preferentialTaxYield` |
| `bond_metric.average_annual_tax_yield` | number | `averageAnnualTaxYield` |
| `bond_metric.deposit_equivalent_yield_154` | number | `depositEquivalentYield154` |
| `bond_metric.buyable_quantity` | number | `buyableQuantity` |
| `bond_metric.remaining_days` | number | `remainingDays` |
| `bond_metric.duration_raw` | number | `durationRaw` |
| `bond_metric.convexity_raw` | number | `convexityRaw` |
| `bond_metric.next_day_duration_raw` | number | `nextDayDurationRaw` |
| `bond_metric.next_day_convexity_raw` | number | `nextDayConvexityRaw` |
| `bond_metric.evaluation_price` | number | `evaluationPrice` |
| `bond_metric.applied_yield` | number | `appliedYield` |
| `bond_metric.dirty_price` | number | `dirtyPrice` |
| `bond_metric.next_day_evaluation_price` | number | `nextDayEvaluationPrice` |
| `bond_metric.next_day_applied_yield` | number | `nextDayAppliedYield` |
| `bond_metric.next_day_dirty_price` | number | `nextDayDirtyPrice` |
| `bond_metric.credit_grade` | string | `creditGrade` |
| `bond_metric.credit_grade_date` | date | `creditGradeDate` |

Names ending in `_raw` intentionally preserve the source's ambiguous analytic
definition. The DSL MUST NOT silently reinterpret them as Macaulay duration,
modified duration, effective duration, or a particular convexity scale.

### Fund observation fields

| DSL field | Type | `FundSnapshot` property |
|---|---|---|
| `fund_metric.as_of` | date | `asOf` |
| `fund_metric.assets_under_management` | number | `assetsUnderManagement` |
| `fund_metric.net_asset_value` | number | `netAssetValue` |
| `fund_metric.previous_nav` | number | `previousNav` |
| `fund_metric.nav_change_amount` | number | `navChangeAmount` |
| `fund_metric.net_asset_total` | number | `netAssetTotal` |
| `fund_metric.nav_per_share` | number | `navPerShare` |
| `fund_metric.net_assets_per_share` | number | `netAssetsPerShare` |
| `fund_metric.net_profit_per_share` | number | `netProfitPerShare` |
| `fund_metric.net_return_assets_per_share` | number | `netReturnAssetsPerShare` |
| `fund_metric.return_1d` | number | `return1d` |
| `fund_metric.return_1w` | number | `return1w` |
| `fund_metric.return_1m` | number | `return1m` |
| `fund_metric.return_3m` | number | `return3m` |
| `fund_metric.return_6m` | number | `return6m` |
| `fund_metric.return_18m` | number | `return18m` |
| `fund_metric.return_1y` | number | `return1y` |
| `fund_metric.return_2y` | number | `return2y` |
| `fund_metric.return_3y` | number | `return3y` |
| `fund_metric.return_5y` | number | `return5y` |
| `fund_metric.return_ytd` | number | `returnYtd` |

### Market observation fields

| DSL field | Type | `MarketSnapshot` property |
|---|---|---|
| `market_metric.as_of` | date | `asOf` |
| `market_metric.source_date` | date | `sourceDate` |
| `market_metric.currency` | string | `currency` |
| `market_metric.base_price` | number | `basePrice` |
| `market_metric.open_price` | number | `openPrice` |
| `market_metric.high_price` | number | `highPrice` |
| `market_metric.low_price` | number | `lowPrice` |
| `market_metric.close_price` | number | `closePrice` |
| `market_metric.premium_discount_rate` | number | `priceChangeRate` |
| `market_metric.trading_value_1d` | number | `tradingValue1d` |
| `market_metric.trading_volume_1d` | number | `tradingVolume1d` |
| `market_metric.average_volume_5d` | number | `averageVolume5d` |
| `market_metric.average_volume_1m` | number | `averageVolume1m` |
| `market_metric.realtime_market_price` | number | `realtimeMarketPrice` |
| `market_metric.realtime_market_volume` | number | `realtimeMarketVolume` |
| `market_metric.realtime_indicative_nav` | number | `realtimeIndicativeNav` |
| `market_metric.realtime_market_difference_rate` | number | `realtimeMarketDifferenceRate` |
| `market_metric.close_price_source` | string | `closePriceSource` |

The logical name `premium_discount_rate` corrects the overly generic current
Neo4j property name `priceChangeRate`; the XLSX schema describes `du_diff_rt` as
a market/NAV divergence. `low_price` retains the loader's current mapping, but
the domestic XLSX description conflicts with that mapping. Consumers SHOULD
carry the warning documented in `xlsx-field-reference.md` when returning it.

### Source and provenance fields

| DSL field | Type | Neo4j property |
|---|---|---|
| `source.uri` | string | `SourceRecord.uri` |
| `source.dataset` | string | `SourceRecord.dataset` |
| `source.row_number` | integer | `SourceRecord.rowNumber` |
| `source.loaded_at` | datetime | `SourceRecord.loadedAt` |
| `file.uri` | string | `SourceFile.uri` |
| `file.name` | string | `SourceFile.name` |
| `file.path` | string | `SourceFile.path` |
| `file.snapshot_date` | date | `SourceFile.snapshotDate` |
| `file.sha256` | string | `SourceFile.sha256` |
| `file.row_count` | integer | `SourceFile.rowCount` |

Every original nonblank value is available as `source.raw.<COLUMN>`, where
`<COLUMN>` is the exact case-sensitive XLSX header, for example
`source.raw.PD_NO` or `source.raw.du_chas_errt`.

Raw-field access has special rules:

- the request MUST constrain `source.dataset` with `eq` or `in`;
- the compiler MUST validate the column against that dataset's
  `FieldDefinition` nodes or a generated registry;
- raw values preserve source types and semantics; and
- selecting raw fields changes the result grain to at least one row per
  supporting `SourceRecord` unless they are explicitly aggregated.

For `entity: "source_record"`, `raw.<COLUMN>` is accepted as shorthand for
`source.raw.<COLUMN>`.

### Ontology fields

| DSL field | Type | Neo4j property |
|---|---|---|
| `ontology.uri` | string | `OntologyClass.uri` |
| `ontology.name` | string | `OntologyClass.name` |

Ontology traversal MUST use the stable application relationship
`SUBCLASS_OF`. It MUST NOT traverse both `SUBCLASS_OF` and the n10s-generated
`neo4j://graph.schema#SCO` relationship in the same request, because that would
duplicate paths.

## Predicate language

A leaf predicate has a field, operator, and—except for existence operators—a
value:

```json
{
  "field": "bond.maturity_date",
  "op": "between",
  "value": [
    "2026-08-10",
    "2028-08-10"
  ]
}
```

Predicates combine recursively with exactly one of `all`, `any`, or `not`:

```json
{
  "all": [
    {
      "field": "offering.available_for_sale",
      "op": "eq",
      "value": true
    },
    {
      "any": [
        {
          "field": "classification.name",
          "op": "contains",
          "value": "주식"
        },
        {
          "field": "fund.strategy",
          "op": "contains",
          "value": "주식"
        }
      ]
    }
  ]
}
```

| Operator | Valid types | Meaning |
|---|---|---|
| `eq`, `neq` | all | Equality/inequality; use existence operators for null. |
| `in`, `not_in` | all | Membership in a nonempty scalar array. |
| `gt`, `gte`, `lt`, `lte` | number, date, datetime | Ordered comparison. |
| `between` | number, date, datetime | Inclusive lower and upper bounds. |
| `contains` | string | Case-insensitive literal substring. |
| `starts_with`, `ends_with` | string | Case-insensitive literal prefix/suffix. |
| `exists`, `not_exists` | all | Property/path presence; no `value` member. |

`regex`, scripts, functions, arithmetic expressions, and raw Cypher fragments
are not part of version 1. String operators are literal, not regular
expressions. Values MUST be passed to Neo4j as parameters.

### Correlating repeated relationships

Related values such as classifications, identifiers, listings, source records,
and observations can be many-valued. Predicates that are meant to describe the
same related node MUST use the same optional `scope`:

```json
{
  "all": [
    {
      "field": "classification.scheme",
      "scope": "grade",
      "op": "eq",
      "value": "credit-grade"
    },
    {
      "field": "classification.code",
      "scope": "grade",
      "op": "eq",
      "value": "AA-"
    }
  ]
}
```

This means one classification must have both `scheme = credit-grade` and
`code = AA-`. It must not match those values on two different classification
nodes. An omitted scope is the implicit `default` scope. Different scope names
request independent bindings, which is useful when a product must have two
different classifications.

`scope` is valid on predicate leaves and on object forms of `select`,
`aggregates`, and `order_by`. It is invalid for a scalar property that does not
traverse a repeatable relation. A projection using a named scope should use an
explicit `as` so its output is unambiguous.

Dates use ISO `YYYY-MM-DD`; datetimes use RFC 3339. Relative phrases such as
“within two years” MUST be resolved by the planner to explicit date bounds and
recorded with the query time so the request is reproducible.

### Missing-value semantics

Missing is unknown, not false. In particular:

- `eq: false` matches an explicit stored false only;
- `not_exists` matches absent/null data;
- `neq` MUST NOT implicitly match absent data; and
- a missing optional relation is not evidence that the relation is false.

## Text search

`text_search` generates root candidates before structured predicates:

```json
{
  "query": "KODEX 200",
  "mode": "fulltext",
  "fields": [
    "entity.name",
    "entity.short_name"
  ]
}
```

Modes are:

- `exact`: case-insensitive equality after trimming;
- `contains`: case-insensitive literal substring; and
- `fulltext`: Neo4j full-text search through `financial_entity_search`.

Valid search fields are `entity.name`, `entity.short_name`,
`entity.english_name`, `identifier.value`, `manager.name`, `issuer.name`,
`benchmark.name`, and `listing.ticker`. When `fields` is omitted, the compiler
uses fields relevant to the selected entity. An organization root uses
`entity.name`.

`fulltext` is valid only for name fields currently covered by
`financial_entity_search`: entity names, organization/manager/issuer names, and
benchmark names. `identifier.value` and `listing.ticker` support `exact` and
`contains`; a compiler MUST reject `fulltext` for them unless a suitable index
has been added. Field restrictions are applied after the index call when Neo4j
cannot enforce them within the index itself.

An identifier-like question SHOULD use structured exact predicates on
`identifier.scheme` and `identifier.value` before full-text search. The
compiler MUST treat full-text scores as relevance signals, not financial ranks.

## Observation selection

Each referenced observation family has an independent selector:

```json
{
  "observations": {
    "fund": {
      "mode": "latest"
    },
    "market": {
      "mode": "at_or_before",
      "date": "2026-07-11"
    }
  }
}
```

| Mode | Required values | Semantics per observation owner |
|---|---|---|
| `latest` | none | Greatest non-null `asOf`; URI ascending breaks ties. |
| `on` | `date` | Exact `asOf` date. |
| `at_or_before` | `date` | Latest observation with `asOf <= date`. |
| `between` | `from`, `to` | All observations in the inclusive interval. |
| `all` | none | All observations, including undated observations. |

If a query references an observation field but omits its selector, `latest` is
the default. Null/undated observations rank after dated observations and are
selected by `latest` only when the owner has no dated observation.

## Ordering and pagination

```json
{
  "order_by": [
    {
      "field": "fund_metric.return_1y",
      "direction": "desc",
      "nulls": "last"
    }
  ],
  "page": {
    "limit": 20,
    "offset": 0
  }
}
```

`direction` defaults to `asc`; `nulls` defaults to `last`. The compiler MUST
append `entity.uri ASC` as a deterministic final key when the caller's keys are
not unique.

The default limit is 20 and the maximum is 100. The maximum offset is 10,000.
A later DSL version may introduce cursor pagination; version 1 uses bounded
offsets because GraphRAG retrieval sets should remain small.

## Relationship catalog

The catalog records logical direction. The physical direction is shown so the
compiler can generate the correct fixed pattern.

| DSL relation | Domain -> range | Physical graph pattern |
|---|---|---|
| `has_unit` | Fund -> FundUnit | `(Fund)-[:HAS_UNIT]->(FundUnit)` |
| `of_fund` | FundUnit -> Fund | `(FundUnit)<-[:HAS_UNIT]-(Fund)` |
| `managed_by` | Fund/FundUnit -> Organization | Fund `(Fund)-[:MANAGED_BY]->(Organization)`; unit goes through `of_fund`. |
| `issued_by` | Bond/ETN -> Organization | `(Security)-[:ISSUED_BY]->(Organization)` |
| `tracks` | Fund/FundUnit/ETN -> Benchmark | Fund/ETN `-[:TRACKS]->`; unit goes through `of_fund`. |
| `classified_as` | Bond/FundUnit/ETN -> Classification | `(Entity)-[:CLASSIFIED_AS]->(Classification)` |
| `has_identifier` | Bond/FundUnit/ETN -> Identifier | `(Security)-[:HAS_IDENTIFIER]->(Identifier)` |
| `listed_as` | Bond/FundUnit/ETN -> Listing | `(Security)-[:LISTED_AS]->(Listing)` |
| `on_market` | Listing -> Market | `(Listing)-[:ON_MARKET]->(Market)` |
| `has_offering` | FundUnit/ETN -> Offering | `(Product)<-[:OFFERS]-(Offering)` |
| `has_observation` | Bond/FundUnit/Listing -> Observation | `(Owner)-[:HAS_OBSERVATION]->(Observation)` |
| `instance_of` | Entity -> OntologyClass | `(Entity)-[:INSTANCE_OF]->(OntologyClass)` |
| `subclass_of` | OntologyClass -> OntologyClass | `(OntologyClass)-[:SUBCLASS_OF]->(OntologyClass)` |
| `described_by` | Entity -> SourceRecord | `(Entity)<-[:DESCRIBES]-(SourceRecord)` |
| `in_file` | SourceRecord -> SourceFile | `(SourceRecord)-[:IN_FILE]->(SourceFile)` |

Invalid domain/range combinations MUST be rejected rather than compiled to a
query that merely returns no rows. In `neighbors`, `min_depth` defaults to 1 and
`max_depth` defaults to 1. A path may revisit neither the same relationship nor
the same node.

## Evidence and provenance

The default evidence policy is:

```json
{
  "mode": "summary",
  "required": true,
  "max_source_rows_per_result": 5
}
```

Modes are:

- `none`: no source metadata;
- `summary`: source dataset/file, snapshot date, SHA-256, and supporting-row
  count; and
- `rows`: summary plus source-record URI and row number, capped per result.

For financial answer generation, callers SHOULD keep `required: true`. When no
supporting `SourceRecord -> DESCRIBES -> entity` path exists, an implementation
MUST mark that result as insufficiently evidenced rather than manufacture a
citation. Ontology-only explanatory results may cite the ontology resource
instead of an XLSX row.

Provenance proves that a source row contributed to the canonical entity. It
does not, by itself, prove that every canonical property came from every linked
row. Where property-level attribution matters, return the specific raw field
from the source row.

## Expected response envelope

The DSL executor returns structured retrieval data, not a prose answer:

```json
{
  "dsl_version": "1.0",
  "query_id": "Q-001",
  "status": "ok",
  "answerable": true,
  "rows": [
    {
      "entity.uri": "urn:miraeasset:security:isin:KR7069500007",
      "entity.name": "example",
      "fund.fee_rate": 0.03
    }
  ],
  "evidence": [],
  "warnings": [],
  "page": {
    "limit": 10,
    "offset": 0,
    "returned": 1
  },
  "meta": {
    "query_time": "2026-08-10T00:00:00+09:00",
    "elapsed_ms": 18
  }
}
```

Valid `status` values are:

| Status | `answerable` | Meaning |
|---|---:|---|
| `ok` | true | Query executed and returned evidenced rows. |
| `empty` | false | Query is supported but no matching evidence exists. |
| `unsupported` | false | Requested concept/relation is not in this graph/DSL. |
| `insufficient_evidence` | false | Candidate data exists but the required evidence policy failed. |
| `invalid` | false | Request failed structural or semantic validation. |
| `error` | false | Execution failed after validation; no raw database error is exposed to an LLM. |

Validation errors SHOULD include a stable code, JSON path, and safe message, for
example:

```json
{
  "status": "invalid",
  "answerable": false,
  "errors": [
    {
      "code": "UNKNOWN_FIELD",
      "path": "$.where.all[1].field",
      "message": "holdings.weight is not supported by DSL version 1.0"
    }
  ]
}
```

Recommended error codes are `INVALID_SCHEMA`, `UNKNOWN_ENTITY`,
`UNKNOWN_FIELD`, `TYPE_MISMATCH`, `INVALID_OPERATOR`, `INVALID_RELATION_PATH`,
`RAW_DATASET_REQUIRED`, `LIMIT_EXCEEDED`, `UNSUPPORTED_SEMANTICS`, and
`QUERY_TIMEOUT`.

## Compilation requirements

A conforming Neo4j compiler MUST:

- run the generated statement in a read-only transaction;
- select labels, properties, relationship types, and sort fields only from
  static compiler maps;
- send every caller value as a Cypher parameter;
- reject unknown fields instead of treating them as raw properties;
- generate `OPTIONAL MATCH` only for projections whose absence should retain the
  root, and required `MATCH`/existence subqueries for relationship predicates;
- prevent multiple many-valued joins from multiplying counts, using subqueries
  or pre-aggregation where needed;
- apply observation selection per owner before metric predicates;
- cap traversal depth, result count, offset, and transaction timeout;
- return stable ordering and deduplicated roots by default; and
- attach the exact DSL request and compiler version to an audit log without
  logging secrets or unrestricted hidden model reasoning.

The compiler MUST NOT use `apoc.cypher.run`, concatenate caller values into a
query, accept a `cypher` member, or expose write operations.

### Example compilation shape

This DSL fragment:

```json
{
  "dsl_version": "1.0",
  "operation": "find",
  "entity": "bond",
  "select": [
    "entity.name",
    "bond.maturity_date",
    "bond_metric.buy_yield"
  ],
  "where": {
    "field": "bond.maturity_date",
    "op": "between",
    "value": [
      "2026-08-10",
      "2028-08-10"
    ]
  },
  "observations": {
    "bond": {
      "mode": "latest"
    }
  }
}
```

may compile to the following *shape*; exact variable names are implementation
details:

```cypher
MATCH (root:Bond)
WHERE root.maturityDate >= date($p0)
  AND root.maturityDate <= date($p1)
CALL (root) {
  OPTIONAL MATCH (root)-[:HAS_OBSERVATION]->(metric:BondSnapshot)
  WITH metric
  ORDER BY metric.asOf DESC, metric.uri ASC
  LIMIT 1
  RETURN metric
}
RETURN DISTINCT root.name AS `entity.name`,
                root.maturityDate AS `bond.maturity_date`,
                metric.buyYield AS `bond_metric.buy_yield`,
                root.uri AS `_stable_uri`
ORDER BY `_stable_uri`
LIMIT $limit
```

The values `2026-08-10`, `2028-08-10`, and the limit remain parameters. They
are not inserted into the Cypher source.

## Examples

### Exact ISIN lookup

```json
{
  "dsl_version": "1.0",
  "operation": "find",
  "entity": "security",
  "select": [
    "entity.uri",
    "entity.kind",
    "entity.name",
    "identifier.scheme",
    "identifier.value"
  ],
  "where": {
    "all": [
      {
        "field": "identifier.scheme",
        "op": "eq",
        "value": "ISIN"
      },
      {
        "field": "identifier.value",
        "op": "eq",
        "value": "KR7069500007"
      }
    ]
  },
  "evidence": {
    "mode": "rows",
    "required": true
  }
}
```

### Bonds maturing in a fixed interval with an exact grade

```json
{
  "dsl_version": "1.0",
  "operation": "find",
  "entity": "bond",
  "select": [
    "entity.name",
    "bond.maturity_date",
    {
      "field": "classification.code",
      "scope": "grade",
      "as": "credit_grade"
    },
    "bond_metric.buy_yield",
    "bond_metric.as_of"
  ],
  "where": {
    "all": [
      {
        "field": "bond.maturity_date",
        "op": "between",
        "value": [
          "2026-08-10",
          "2028-08-10"
        ]
      },
      {
        "field": "classification.scheme",
        "scope": "grade",
        "op": "eq",
        "value": "credit-grade"
      },
      {
        "field": "classification.code",
        "scope": "grade",
        "op": "eq",
        "value": "AA-"
      }
    ]
  },
  "observations": {
    "bond": {
      "mode": "latest"
    }
  },
  "order_by": [
    {
      "field": "bond.maturity_date",
      "direction": "asc"
    }
  ]
}
```

“AA- or better” is intentionally not shown. The loaded graph lacks an
authoritative rating-agency scale, so ordinal rating comparison is unsupported
until such a scale is loaded.

### Count products by manager

```json
{
  "dsl_version": "1.0",
  "operation": "aggregate",
  "entity": "fund_unit",
  "where": {
    "field": "offering.available_for_sale",
    "op": "eq",
    "value": true
  },
  "group_by": [
    "manager.name"
  ],
  "aggregates": [
    {
      "function": "count_distinct",
      "field": "entity.uri",
      "as": "product_count"
    }
  ],
  "order_by": [
    {
      "field": "product_count",
      "direction": "desc"
    }
  ]
}
```

### Query an unnormalized XLSX field

Tracking error is retained only on the source record:

```json
{
  "dsl_version": "1.0",
  "operation": "find",
  "entity": "etf",
  "select": [
    "entity.uri",
    "entity.name",
    "source.row_number",
    "source.raw.du_chas_errt",
    "file.name",
    "file.snapshot_date"
  ],
  "where": {
    "all": [
      {
        "field": "source.dataset",
        "op": "eq",
        "value": "domestic_etf_etn"
      },
      {
        "field": "source.raw.du_chas_errt",
        "op": "exists"
      }
    ]
  },
  "order_by": [
    {
      "field": "source.raw.du_chas_errt",
      "direction": "asc",
      "nulls": "last"
    }
  ]
}
```

This is a structural/provenance example, not a useful current ranking query.
All 1,551 populated `du_chas_errt` values in the supplied domestic snapshot are
`0.00`, and the calculation window is undocumented.

### Bounded ontology neighborhood

```json
{
  "dsl_version": "1.0",
  "operation": "neighbors",
  "entity": "ontology_class",
  "select": [
    "ontology.uri",
    "ontology.name"
  ],
  "where": {
    "field": "ontology.name",
    "op": "eq",
    "value": "Bond"
  },
  "traversal": {
    "relations": [
      "subclass_of"
    ],
    "min_depth": 1,
    "max_depth": 4,
    "return": "paths"
  }
}
```

## Current answerability boundaries

The DSL validator should distinguish an empty supported query from a question
that the loaded graph cannot answer.

| Capability | Current status |
|---|---|
| Names, identifiers, types, currencies, and dates | Supported |
| Manager/issuer, benchmark, listing, market, offering, classifications | Supported where the feed supplied them |
| Canonical prices, NAV/AUM, returns, yields, and maturity filters | Supported with source-definition cautions |
| Exact source rows and all 207 XLSX columns | Supported through raw fields and provenance |
| Exact credit-grade equality | Supported |
| “AA- or better” and cross-agency grade ordering | Unsupported until a rating scale is loaded |
| ETF holdings and constituent weights | Unsupported; no holdings data was loaded |
| Corporate parent/subsidiary relationships | Unsupported |
| Per-product history | Unsupported; this load has one observation per entity, not repeated snapshots |
| Theme/news/history relationships | Unsupported; product-name candidates do not establish a sourced temporal relationship |
| Prospectus risk narratives and document passages | Unsupported; no document corpus/vector index was loaded |
| Reliable dividend-frequency reasoning | Unsupported in this snapshot; `pd_dvid_cycl` is blank for all 1,734 domestic ETF/ETN rows |
| Domestic ETF tracking-error comparison | Unsupported in practice; all 1,551 populated `du_chas_errt` values are `0.00`, and the formula/window is undocumented |
| Complete domestic ETF fee comparison | Unsupported; `cu_charge_rt` is populated for only 217 of 1,734 rows |

An external query router MAY send unsupported holdings, corporate, or document
subquestions to another store. It MUST not relabel such evidence as if it came
from this Neo4j graph.

## GraphRAG use

For GraphRAG, the natural-language model should produce the DSL—not Cypher—and
receive the validated response plus provenance. A recommended audit trace is a
short record of actions such as:

```text
resolved ISIN -> selected ETF unit -> latest fund observation
-> filtered fee -> attached source rows
```

That is an operational trace, not unrestricted hidden chain-of-thought. The
answer generator should be given:

- the original question;
- the normalized DSL request;
- structured result rows;
- evidence metadata and selected raw fields;
- warnings about ambiguous source semantics; and
- an explicit `answerable` value.

If the executor returns `empty`, `unsupported`, or `insufficient_evidence`, the
answer layer should abstain or explain the missing data instead of filling the
gap from model memory.

## Versioning

`dsl_version` is a major/minor string. Additive fields and operators require a
minor version; changed semantics, removed names, or incompatible response
changes require a major version. A compiler MUST reject versions it does not
support and MUST include its supported version range in service metadata.

The physical Neo4j property names may be migrated without changing the DSL when
the logical meaning is unchanged. For example, renaming the physical
`priceChangeRate` property to `premiumDiscountRate` would not change the DSL
field `market_metric.premium_discount_rate`.
