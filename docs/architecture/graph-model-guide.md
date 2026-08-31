# Beginner's guide to the financial-product graph

This guide explains what is in the Neo4j database, why the graph is structured
this way, and how each Excel workbook was converted. It assumes no finance or
ontology background.

The shorter operational record—commands, installed versions, validation totals,
and rerun instructions—is in [`../data/loading-record.md`](../data/loading-record.md).

For a column-by-column explanation of all 207 Excel fields, see
[`../data/xlsx-field-reference.md`](../data/xlsx-field-reference.md).

For the read-only JSON query language proposed for applications and GraphRAG,
see [`query-dsl-spec.md`](query-dsl-spec.md).

For an evidence-based assessment of which contest questions this graph can
currently answer, see
[`../evaluation/historical-data-capabilities-2026-07-11.md`](../evaluation/historical-data-capabilities-2026-07-11.md). Future holdings,
company, XBRL, and document modeling is kept in
[`../external/external-data-plan.md`](../external/external-data-plan.md).

## The two-minute mental model

The graph separates four questions that spreadsheets often put in one row:

1. **What is the financial thing?** A bond, fund, fund unit, or ETN.
2. **How is it identified and traded?** ISINs, source IDs, tickers, listings,
   and markets.
3. **What is true only at a particular time?** Prices, NAV, AUM, returns,
   yields, duration, sale availability, and similar observations.
4. **Where did the assertion come from?** The original file, Excel row, field,
   and snapshot date.

The main structure is:

```text
Fund
  └── HAS_UNIT ──> FundUnit / Security
                       ├── HAS_IDENTIFIER ──> Identifier
                       ├── LISTED_AS ───────> Listing ── ON_MARKET ──> Market
                       │                          └── HAS_OBSERVATION ──> MarketSnapshot
                       ├── HAS_OBSERVATION ─> FundSnapshot
                       └── CLASSIFIED_AS ────> Classification

Bond / ETN
  ├── ISSUED_BY ───────> Organization
  ├── HAS_IDENTIFIER ──> Identifier
  ├── LISTED_AS ───────> Listing
  └── HAS_OBSERVATION ─> BondSnapshot or MarketSnapshot

SourceRecord
  ├── IN_FILE ─────────> SourceFile ── EXTRACT_OF ──> SourceDataset
  └── DESCRIBES ───────> Fund, FundUnit, Bond, or ETN
```

This avoids treating “the fund,” “the share you can buy,” “its ticker,” “today's
price,” and “the spreadsheet row” as the same object.

## Finance primer

### Bond

A bond is essentially a tradable loan.

- The **issuer** borrows money.
- The bond has an **issue date** and usually a **maturity date**, when principal
  is due to be repaid.
- A **coupon rate** determines contractual interest payments for a fixed-coupon
  bond.
- The **market price** can be above or below the amount repaid at maturity.
- **Yield** summarizes return relative to price and future payments. There are
  several yield definitions, so a field simply named “yield” is not enough to
  choose the exact financial meaning.
- **Duration** estimates price sensitivity to changes in interest rates.
- **Convexity** describes curvature in that price/rate relationship and improves
  on a simple duration approximation.
- A **credit rating** describes an agency's opinion of credit risk. It is not a
  customer review score.

The graph therefore keeps permanent contract terms on `Bond`, but puts changing
prices, yields, duration, and convexity in `BondSnapshot`.

### Fund

A fund pools assets under an investment strategy. The fund may own stocks,
bonds, other funds, cash, or combinations of them.

Examples include mutual funds and exchange-traded funds. The abstract fund is
modeled as `Fund`.

### Fund unit or share class

An investor normally owns units or shares in a fund—not the abstract strategy
itself. A fund can have several share classes with different fees, currencies,
distribution policies, investor eligibility, or sales channels.

That investable interest is represented as `FundUnit`. It is also labeled
`Security` and `FinancialInstrument` in this graph.

The current public-fund source does not provide a sufficiently verified parent
fund key, so its first version uses one `Fund` per `itm_no` and connects that fund
to one canonical `FundUnit`. The repeated `prfd_attr_cd` rows are merged as
classifications of the same unit. This is intentionally conservative; it avoids
incorrectly combining distinct share classes.

### ETF

An exchange-traded fund is a fund whose units are listed and traded on an
exchange. An ETF row therefore creates both:

- a `Fund`, describing the managed pool and strategy; and
- a `FundUnit`, describing the security that is identified and listed.

The `Listing` stores the venue-specific ticker and market. The price belongs to
the listing's `MarketSnapshot`, not directly to the abstract fund.

### ETN

An exchange-traded note is not a fund. It is generally a debt obligation issued
by an organization, often with a return linked to an index.

This matters because ETF investors hold an interest in a pooled fund, while ETN
investors have exposure to the issuer's promise and credit risk. The loader
therefore creates `ExchangeTradedNote` nodes without creating `Fund` nodes.

FIBO does not currently supply a dedicated ETN class in the selected modules, so
the local ontology defines `ExchangeTradedNote` as a subclass of FIBO
`DebtInstrument` and `ListedSecurity`. This is classification only; the source
does not describe full payoff terms.

### Security, identifier, listing, and market

These terms are related but not interchangeable:

| Term | Plain-language meaning | Example |
|---|---|---|
| Security | The identifiable financial instrument | One ETF share class |
| Identifier | A name/code assigned under an identification scheme | ISIN `KR7069500007` |
| Listing | A venue-specific trading line for the security | Ticker `A069500` |
| Market | The venue or market associated with the listing | Korean securities market |

One security can have several identifiers. One security can also have several
listings. A ticker is not globally unique without a market.

The overseas dataset demonstrates this directly: fifty securities have two
listings. For example, ISIN `US86280R7879` is represented once as a security but
has these two listing records:

```text
AMX / ESUM.K
102 / EUSM.K
```

### Benchmark

A benchmark is an index or reference portfolio against which a fund or ETN may
be designed or evaluated. `TRACKS` means that the source named that benchmark or
base index. It does not prove perfect replication or guarantee returns.

### AUM, NAV, price, and return

- **AUM** means assets under management: the aggregate amount managed in a fund.
- **NAV** means net asset value: assets minus liabilities, sometimes represented
  for the whole fund and sometimes per unit.
- **Market price** is what a listed unit trades for. It may differ from NAV.
- **Return** describes performance over a stated period, such as one month or
  one year.

Because these values change with time, they live on `FundSnapshot` or
`MarketSnapshot` rather than being treated as timeless identity fields.

### Offering

`Offering` means the broker/distributor's sale availability in this feed. It is
not the same thing as the security or its exchange listing.

A product can continue to exist even if the broker stops selling it. Similarly,
a trading halt is temporary state, not a new security identity.

## How Neo4j labels work

A Neo4j node can have several labels. Labels describe roles or categories; they
do not create duplicate nodes.

For example, one ETF unit can have all of these labels:

```text
FundUnit
Security
FinancialInstrument
Entity
Resource
```

That means:

- it is a unit in a fund;
- it is treated as a security;
- it is a financial instrument;
- it is a canonical business entity; and
- it has a globally unique graph URI.

It is still one node.

Every application node except n10s's `_GraphConfig` is a `Resource` and has a
unique `uri`. The `resource_uri` constraint prevents two `Resource` nodes from
using the same URI.

`Entity` marks canonical business things such as funds and securities. Source
rows, classifications, observations, and identifiers are resources but are not
canonical financial entities.

## Node catalog

Counts below are from the completed load. Because nodes can have several labels,
label counts overlap and must not be added together.

### Source and provenance nodes

| Label | Count | Meaning | Important properties |
|---|---:|---|---|
| `SourceDataset` | 4 | Logical feed, such as domestic bonds | `code`, `name`, `uri` |
| `SourceFile` | 4 | Exact dated workbook that was loaded | `name`, `path`, `snapshotDate`, `sha256`, `rowCount` |
| `SourceRecord` | 145,393 | One Excel data row | `dataset`, `rowNumber`, every nonblank original column |
| `RejectedRecord` | 1 | A source row not converted to a canonical entity | Same properties as `SourceRecord` |
| `FieldDefinition` | 207 | A column described by a schema workbook | `name`, `ordinal`, `sourceDataType`, `koreanName`, `example` |
| `DataQualityIssue` | 1 | Explanation of a rejected/suspicious row | `code`, `message`, `dataset`, `rowNumber` |

`SourceRecord` is deliberately wide. It keeps the original vendor column names
such as `PD_NO`, `du_clpr`, or `prfd_attr_cd`. This is the evidence layer, not the
friendly application interface.

### Canonical financial nodes

| Label | Count | Meaning | Important properties |
|---|---:|---|---|
| `Bond` | 42,394 | One canonical domestic bond security | Names, issue/maturity dates, currency, coupon, outstanding issue amount |
| `Fund` | 17,877 | Managed investment pool or fund-level concept | Name, strategy, fees, base index name, currency, primary FIBO class |
| `FundUnit` | 17,877 | Investable unit/share associated with a fund | Name, source item number, currency, representative source identifiers |
| `ExchangeTradedNote` | 591 | Listed note classified as debt, not a fund | Name, source item, strategy, fee/base-index fields where supplied |
| `Security` | 60,862 | Common label on bonds, fund units, and ETNs | Shared identity role; see more-specific labels for meaning |
| `FinancialInstrument` | 60,862 | Broad instrument role | Common classification label |
| `Entity` | 78,739 | Canonical funds and instruments | Common canonical-entity label |

Why are there the same number of funds and fund units? The current model creates
one canonical unit for every canonical fund identity available in these feeds.
The `HAS_UNIT` relationship is still preserved because future sources may
identify multiple share classes under one parent fund.

### Identification and reference nodes

| Label | Count | Meaning | Important properties |
|---|---:|---|---|
| `Identifier` | 113,199 | A code plus its scheme | `scheme`, `value`, `uri` |
| `Organization` | 8,548 | Issuer or manager | `name` or source `code`, `identityScheme` |
| `Benchmark` | 2,125 | Named base index/reference | `name`, `englishName` |
| `Classification` | 5,264 | Reusable category/code | `scheme`, `code`, `name` |
| `Market` | 8 | Normalized market/venue bucket | `code`, `name` |

An `Identifier` includes its scheme because the same character sequence under
two schemes does not necessarily identify the same thing. Schemes currently
include ISIN, source item, listing ticker, standard item, KSD item, FSS item, and
other source-specific codes.

`Organization` identities are conservative:

- bonds and exchange products use normalized organization names; and
- public funds use `or_co_xtn_itt_cd` source codes because that workbook does not
  provide organization names.

No attempt was made to guess that a code-only organization and a name-only
organization are the same legal entity.

### Trading, sale-state, and temporal nodes

| Label | Count | Meaning | Important properties |
|---|---:|---|---|
| `Listing` | 32,303 | One instrument trading line on a market | `ticker`, `marketCode`, `listingDate`, `listingPrice` |
| `Offering` | 18,518 | Sale/trading availability from the feed | `availableForSale`, `saleStatus`, `tradingHalted`, `asOf` |
| `BondSnapshot` | 42,394 | Dated bond valuation/analytics | Prices, yields, duration, convexity, grade, `asOf` |
| `FundSnapshot` | 17,877 | Dated fund/unit measurements | AUM, NAV, returns, `asOf` |
| `MarketSnapshot` | 7,554 | Dated listing-market measurements | Open/high/low/close, volume/value, currency, `asOf` |
| `Observation` | 67,825 | Common label on all three snapshot types | `asOf`, `dataset`, `uri` |

Listing counts by source:

| Dataset | Listings |
|---|---:|
| Domestic bonds | 24,749 |
| Korean ETF/ETN | 1,733 |
| Overseas ETF/ETN | 5,646 |
| Public funds, inferred ETF listings | 175 |

An `Offering` count can exceed the number of canonical products because an
overseas security with two venue-specific source rows receives two
venue-specific offering records.

### Ontology and technical nodes

| Label | Count | Meaning |
|---|---:|---|
| `OntologyClass` | 34 | FIBO or local application-profile class used for semantic typing |
| `neo4j://graph.schema#Class` | 34 | n10s's lossless physical label for the same ontology-class nodes |
| `_GraphConfig` | 1 | Internal n10s RDF import/export configuration |

The expanded `neo4j://...` label is intentionally retained for n10s. Application
queries should normally use `OntologyClass`.

## Relationship catalog

Relationship arrows describe the stored direction. Cypher can traverse them in
either direction when the query uses an undirected pattern.

### Source and provenance relationships

| Relationship | Count | Pattern | Meaning |
|---|---:|---|---|
| `EXTRACT_OF` | 4 | `SourceFile → SourceDataset` | This physical workbook is an extract of this logical feed |
| `HAS_FIELD` | 207 | `SourceDataset → FieldDefinition` | This feed defines this source column |
| `IN_FILE` | 145,393 | `SourceRecord → SourceFile` | This exact row came from this workbook |
| `DESCRIBES` | 247,799 | `SourceRecord → Entity` | The row contributed information to this canonical entity |
| `HAS_ISSUE` | 1 | `RejectedRecord → DataQualityIssue` | The row has this recorded load/quality problem |

`DESCRIBES` is larger than the source-row count because an ETF or mutual-fund row
usually describes both a `Fund` and its `FundUnit`. A bond or ETN row describes
one canonical instrument.

### Financial-structure relationships

| Relationship | Count | Pattern | Meaning |
|---|---:|---|---|
| `HAS_UNIT` | 17,877 | `Fund → FundUnit` | This security/unit represents an investable interest in this fund |
| `ISSUED_BY` | 42,067 | `Bond or ETN → Organization` | This organization is the issuer according to the source field |
| `MANAGED_BY` | 17,862 | `Fund → Organization` | This organization manages the fund according to the source field/code |
| `TRACKS` | 16,797 | `Fund or ETN → Benchmark` | The source names this base index or benchmark |
| `CLASSIFIED_AS` | 382,663 | `Instrument → Classification` | The source assigns this reusable category or code |

Some relationships are missing where the source field is blank. Absence of
`MANAGED_BY`, for example, means “not supplied or not mapped,” not “the fund has
no manager.”

`CLASSIFIED_AS` is the largest relationship family because the public-fund
workbook repeats each product under many `prfd_attr_cd` values. All original rows
remain in the evidence layer, while the canonical unit accumulates distinct
classification relationships.

### Identification, listing, and state relationships

| Relationship | Count | Pattern | Meaning |
|---|---:|---|---|
| `HAS_IDENTIFIER` | 127,992 | `Security → Identifier` | This identifier/code refers to the instrument |
| `LISTED_AS` | 32,303 | `Security → Listing` | This instrument has this venue-specific trading record |
| `ON_MARKET` | 32,303 | `Listing → Market` | This listing belongs to this market bucket |
| `OFFERS` | 18,518 | `Offering → FundUnit or ETN` | This sale-state record concerns this product |
| `HAS_OBSERVATION` | 67,825 | `Instrument/Listing → Observation` | This dated snapshot measures this subject |

The subject of an observation matters:

- `Bond → BondSnapshot` for bond analytics;
- `FundUnit → FundSnapshot` for NAV/AUM/performance; and
- `Listing → MarketSnapshot` for venue-specific market data.

### Ontology relationships

| Relationship | Count | Pattern | Meaning |
|---|---:|---|---|
| `INSTANCE_OF` | 158,835 | `Entity → OntologyClass` | The entity is semantically typed using stable FIBO/shared and feed-specific classes |
| `SUBCLASS_OF` | 22 | `OntologyClass → OntologyClass` | Friendly application alias for an ontology class hierarchy |
| `neo4j://graph.schema#SCO` | 22 | `OntologyClass → OntologyClass` | n10s's lossless representation of the same subclass statements |

Do not traverse both `SUBCLASS_OF` and `neo4j://graph.schema#SCO` in one query
unless duplicate paths are intentionally handled; they represent the same
logical hierarchy statements.

An entity can have several `INSTANCE_OF` links. An ETN, for example, connects to
the local `ExchangeTradedNote`, FIBO `DebtInstrument`, and FIBO
`ListedSecurity` classes.

## Common conversion mechanics

### Cleaning values

For every workbook:

- leading/trailing whitespace is removed from strings;
- empty strings become absent properties;
- Excel dates and `YYYYMMDD` strings become Neo4j date values;
- selected financial numeric strings become Neo4j floating-point values;
- every nonblank original value is preserved on `SourceRecord`; and
- normalized, human-readable property names are added only to canonical or
  observation nodes.

Boolean mappings are source-aware but share these conversions:

```text
Y / YES / TRUE / 1 / 판매중       → true
N / NO  / FALSE / 0 / 판매완료   → false
```

The target property supplies the meaning. For example, `pd_tr_yn = 1` becomes
`tradingHalted = true`, while `pd_sale_yn = 1` becomes
`availableForSale = true`.

### Deterministic URIs

Every resource receives a deterministic URI. Examples:

```text
urn:miraeasset:security:isin:KR7069500007
urn:miraeasset:listing:domestic_etf_etn:EXG_MKT_NO_001:A069500
urn:miraeasset:source-record:domestic_etf_etn:2026-07-11:2
urn:miraeasset:observation:bond:KR101501DA16:2025-02-03
```

The loader uses `MERGE` on these URIs. Rerunning the same snapshot updates the
same resources rather than creating duplicates.

### Why source rows and canonical entities are both kept

Suppose sixteen public-fund rows have the same `itm_no` and differ only in
`prfd_attr_cd`.

If only raw rows were stored, the graph would look like sixteen separate funds.
If only the canonical fund were stored, the exact input evidence would be lost.

The loader therefore keeps:

```text
16 SourceRecord nodes
      └── DESCRIBES ──> 1 Fund and 1 FundUnit
                              └── CLASSIFIED_AS ──> each distinct attribute code
```

This pattern provides both auditability and useful product identity.

## Detailed conversion: domestic bonds

Input: `PRBD01N001_국내채권마스터_20260711_datarows.xlsx`

Each valid row creates or updates:

```text
SourceRecord
  └── DESCRIBES ──> Bond
                       ├── HAS_IDENTIFIER ──> Identifier
                       ├── ISSUED_BY ───────> Organization, if supplied
                       ├── CLASSIFIED_AS ───> bond categories/risk/grade
                       ├── LISTED_AS ───────> Listing, only for 장내
                       └── HAS_OBSERVATION ─> BondSnapshot
```

### Bond identity and descriptive fields

| Excel field | Graph destination | Interpretation |
|---|---|---|
| `PD_NO` | `Bond.sourceProductNumber`; ISIN identifier when valid | Canonical bond identity |
| `PD_NM` | `Bond.name` | Full Korean name |
| `PD_ABRV_NM` | `Bond.shortName` | Short Korean name |
| `PD_ENG_NM` | `Bond.englishName` | English name |
| `PD_CTRY_CD` | `Bond.countryCode` | Country code |
| `PD_PBCM` | `Organization.name`, `ISSUED_BY` | Source issuer/publisher field |
| `CURR_CD` | `Bond.currency` | Denomination currency |
| `ISU_DT` | `Bond.issueDate` | Issue date |
| `MAT_DT` | `Bond.maturityDate` | Maturity date |
| `SRFC_IRT` | `Bond.couponRate` | Source coupon/rate field |
| `ISU_BAL_AMT` | `Bond.issueOutstandingAmount` | Aggregate issue balance, not per-unit face value |
| `PD_EXG_MKT` | `Bond.exchangeMarket` | `장내` creates a listing; `장외` does not |

### Bond classifications

These fields become separate reusable `Classification` nodes:

- `STD_PD_MCLS_NM`: main bond category;
- `STD_PD_SCLS_NM`: bond subcategory;
- `BD_KND`: bond kind;
- `CRD_GRD` or `PD_EVCO_CRD_GRD`: credit grade; and
- `PD_RISK_GCD`: source risk code.

### Bond snapshot fields

The loader uses `PD_STD_INFO_UPDATE` as the observation date when supplied,
otherwise the file snapshot date.

| Source group | Normalized properties |
|---|---|
| Prices | `evaluationPrice`, `dirtyPrice`, next-day variants |
| Yields | `buyYield`, `appliedYield`, tax variants |
| Interest-rate analytics | `durationRaw`, `convexityRaw`, next-day variants |
| Availability | `buyableQuantity`, `remainingDays` |
| Credit snapshot | `creditGrade`, `creditGradeDate` |

`Raw` is deliberate in `durationRaw` and `convexityRaw`: the column names alone
do not establish whether they are modified, effective, Macaulay, or another
precise analytic definition.

### Worked bond example

The graph contains:

```text
Bond: 국민주택1종채권 20-01
ISIN: KR101501DA16
Issuer: 대한민국
Issue date: 2020-01-31
Maturity date: 2025-01-31
Coupon rate: 1.0
Observation date: 2025-02-03
Evaluation price: 10510.0
```

The source shows a duration value of zero after maturity. The graph preserves
that source result rather than “correcting” it.

## Detailed conversion: Korean ETF/ETN

Input: `PREF01N001_국내ETF마스터_20260711_datarows.xlsx`

`pd_grp_no` splits the file into 1,202 ETF rows and 532 ETN rows.

### ETF row

An ETF row becomes:

```text
SourceRecord
  ├── DESCRIBES ──> Fund ── HAS_UNIT ──> FundUnit
  └── DESCRIBES ───────────────────────> FundUnit

Fund
  ├── MANAGED_BY ──> Organization
  └── TRACKS ──────> Benchmark, when supplied

FundUnit
  ├── HAS_IDENTIFIER ──> ISIN/source item/ticker identifiers
  ├── LISTED_AS ───────> Listing ── ON_MARKET ──> Market
  ├── HAS_OBSERVATION ─> FundSnapshot
  └── CLASSIFIED_AS ───> asset/region/sector/risk categories

Listing ── HAS_OBSERVATION ──> MarketSnapshot
Offering ── OFFERS ──────────> FundUnit
```

### ETN row

An ETN row creates `ExchangeTradedNote`, not `Fund` or `FundUnit`:

```text
SourceRecord ── DESCRIBES ──> ExchangeTradedNote
ExchangeTradedNote
  ├── ISSUED_BY ───────> Organization
  ├── TRACKS ──────────> Benchmark, when supplied
  ├── HAS_IDENTIFIER ──> Identifier
  ├── LISTED_AS ───────> Listing
  └── CLASSIFIED_AS ───> Classification
Offering ── OFFERS ────> ExchangeTradedNote
```

### Main Korean exchange-product mappings

| Excel field | Graph destination |
|---|---|
| `pd_itm_no` | Security identity; ISIN and source-item identifiers |
| `pd_itm_no_ma` | Listing ticker and ticker identifier |
| `pd_nm`, `pd_abrv_nm` | Names on fund/unit or ETN |
| `pd_exg_mkt_cd`, `pd_mkt_id`, `pd_mkt_nm` | Listing and market |
| `cu_fund_mgmt_co` | Fund manager or ETN issuer organization |
| `cu_base_index` | Benchmark |
| `cu_strtegy` | Fund/ETN strategy text |
| `cu_charge_rt`, `cu_charge_etc_rt` | Fee fields |
| `wu_inv_ast_type`, `wu_inv_rgn` | Classifications |
| `pd_sale_yn` | `Offering.availableForSale` |
| `pd_tr_yn` | `Offering.tradingHalted` |

Market fields such as close/high/low, trading value, and volume become a
`MarketSnapshot`. NAV, AUM, and return-window fields become a `FundSnapshot`.

One Korean row lacks market data, so 1,734 rows produce 1,733 listings.

### Worked ETF example

The source row for KODEX 200 becomes approximately:

```text
Fund: 삼성 KODEX200 증권상장지수투자신탁[주식]
  └── HAS_UNIT ──> FundUnit URI urn:miraeasset:security:isin:KR7069500007
                       ├── ISIN: KR7069500007
                       ├── LISTED_AS ──> ticker A069500
                       └── FundSnapshot

Fund ── MANAGED_BY ──> 삼성
Listing ── ON_MARKET ──> 유가증권
Listing ── HAS_OBSERVATION ──> closePrice 136290.0 as of 2026-07-11
Offering ── OFFERS ──> FundUnit, availableForSale = true
```

## Detailed conversion: overseas ETF/ETN

Input: `PREF02N001_해외ETF마스터_20260711_datarows.xlsx`

The ETF/ETN structural split is the same as the Korean file. The important
difference is identity resolution:

- `pd_isin_cd` identifies the security when populated;
- market code plus ticker identifies the listing; and
- rows without ISIN use a source-specific market/ticker security URI.

The file contains 5,587 ETF rows but only 5,537 canonical ETF funds/units because
fifty ISINs appear under two listings. All 5,646 rows still create distinct
`SourceRecord` and `Listing` nodes.

`cu_etn_yn = Y` or `pd_grp_no = ETN` creates an ETN. The 59 ETN rows are not
mistaken for funds.

Useful overseas-specific mappings include:

| Excel field | Graph destination |
|---|---|
| `pd_isin_cd` | ISIN identifier and canonical security key |
| `pd_itm_no`, `pd_itm_no_ma` | Source item and listing ticker |
| `pd_exg_mkt_cd` | Listing market code |
| `pd_trd_ccy` | Trading/market snapshot currency |
| `du_clpr_base_dt` | Market observation date |
| `du_clpr_src` | Closing-price source |
| `cu_index_repl_mthd` | Index replication method |
| `cu_index_tracking_yn` | Index-tracking flag |
| `cu_inverse_short_yn` | Inverse/short flag |

## Detailed conversion: public funds

Input: `PRFD01N001_공모펀드마스터_20260711_datarows.xlsx`

This is the most important deduplication case.

The workbook has 95,619 rows but only 11,139 distinct raw `itm_no` values. One of
those is the malformed `"` value, leaving 11,138 valid canonical fund/unit
identities.

### Why rows repeat

Many rows describe the same item and differ in `prfd_attr_cd`. The source is
effectively expressing a many-valued product-attribute relationship by repeating
the whole row.

For example, one unit currently has these eleven attribute codes:

```text
F103, V102, M111, C103, D102, M109, C101, G110, M112, W101, D106
```

The graph stores one unit and eleven `CLASSIFIED_AS` relationships while retaining
all eleven original `SourceRecord` nodes.

### Public-fund identity rules

- `itm_no` is the canonical source-item key.
- It is not asserted as ISIN even though it has an ISIN-like shape. Valid source
  keys may end with `M`, which a strict ISIN does not.
- `std_itm_no`, `ksd_itm_no`, `rptt_ksd_itm_no`, `fss_itm_no`, and
  `mtco_itm_no` become additional scheme-qualified identifiers.
- Placeholder values consisting only of zeroes are not made into identifiers.
- `rptt_ksd_itm_no` is not yet used as a parent-fund merge key because it has
  frequent zero placeholders and its grouping semantics have not been verified.

### Public-fund field mappings

| Excel field | Graph destination or treatment |
|---|---|
| `itm_no` | Source-specific fund and unit identities |
| `itm_nm`, `itm_abrv_nm`, `itm_eng_nm` | Fund/unit names |
| `curr_cd` | Currency |
| `or_co_xtn_itt_cd` | Code-only manager organization |
| `bmrk_nm`, `bmrk_eng_nm` | Benchmark |
| `prfd_attr_cd` | `product-attribute` classification |
| `kofia_fd_ccd` | KOFIA fund classification |
| `fd_ivst_rgn_desc` | Investment-region classification |
| `or_attr_desc` | Source fund-type classification |
| `zrin_fd_ivst_risk_gcd` | Risk-grade classification |
| `fd_nast_suma` | `FundSnapshot.netAssetTotal` |
| Return-window columns | Corresponding `FundSnapshot.return...` properties |
| `sale_yn` | Offering sale status and availability |
| `thco_sale_yn` | Availability through this firm |

### `exchdg_yn` does not mean exchange traded

The schema workbook gives `exchdg_yn` the Korean description `환헤지여부`, meaning
currency-hedging status. It is therefore mapped to `Fund.currencyHedged`.

ETF status in this file is inferred only from `상장지수` in the Korean product
name or `ETF` in the name/abbreviation. This creates 175 inferred listings. Each
such listing has `listingInferredFromName = true` and uses an unspecified Korean
exchange market because the file does not supply a venue/ticker field.

This is a heuristic, not a fact directly asserted by a dedicated source column.

### Malformed row

Excel row 84,563 has shifted values. Its `itm_no` is `"`, and values from later
columns appear under incorrect headers.

The loader creates:

```text
(SourceRecord:RejectedRecord)
  └── HAS_ISSUE ──> (DataQualityIssue {
        code: "INVALID_ITEM_NUMBER",
        rowNumber: 84563
      })
```

No canonical fund or unit is created from that row.

## Ontology/FIBO conversion

The graph uses FIBO for semantic typing, but it does not copy the entire FIBO
repository into the database.

The modular local application profile defines 34 ontology classes across
`common.ttl`, `bond_kr.ttl`, `etf_kr.ttl`, `etf_gl.ttl`, and `fund_pub.ttl`.
Canonical entities connect to both their stable FIBO/shared type and their
feed-specific local type with `INSTANCE_OF`.

Examples:

```text
Bond ── INSTANCE_OF ──> local KoreanBond ── SUBCLASS_OF ──> FIBO Bond
  └──── INSTANCE_OF ──> FIBO Bond

Korean ETF Fund ── INSTANCE_OF ──> local KoreanExchangeTradedFund
        └───────── INSTANCE_OF ──> FIBO ExchangeTradedFund
ETF Unit ── INSTANCE_OF ──> FIBO TradableFundUnit
ETF Unit ── INSTANCE_OF ──> FIBO ListedSecurity

Public Fund ── INSTANCE_OF ──> local PublicFund
Public Unit ── INSTANCE_OF ──> local PublicFundUnit
           └─ INSTANCE_OF ──> FIBO NonTradableFundUnit when non-listed

ETN ── INSTANCE_OF ──> local ExchangeTradedNote
ETN ── INSTANCE_OF ──> local KoreanExchangeTradedNote or GlobalExchangeTradedNote
ETN ── INSTANCE_OF ──> FIBO DebtInstrument
ETN ── INSTANCE_OF ──> FIBO ListedSecurity
```

The modular typing was applied to the existing database on 2026-08-10 with an
idempotent `uv run mirae-graph load`. It added 72,000 feed-specific
`INSTANCE_OF` links without a reset or duplicate resources.

The primary class URI is also copied to `fiboClassUri` for simple filtering.

The ontology hierarchy allows a query to understand that a bond is a kind of
debt instrument and financial instrument, even if the query starts at a broader
concept.

## Known limitations and non-claims

Understanding what the graph does **not** assert is as important as understanding
what it does assert.

### Public fund grouping remains conservative

The graph does not yet merge several public-fund `itm_no` values into one parent
fund/share-class family. A verified fund-family key or reference-data dictionary
is needed first.

### Cross-feed fund matching is not name-based

An ETF can appear in both the Korean ETF master and public-fund master under
different source identifiers. The loader does not merge them merely because the
names look similar. Name-only merging could combine different share classes or
products.

Such records can be linked later through a reviewed crosswalk using verified
identifiers.

### Organization resolution is incomplete

Public-fund manager codes are not automatically merged with named managers from
the ETF feeds. A manager-code dictionary or LEI/business-entity crosswalk would
be needed.

### Credit ratings lack agency identity

The source contains grades but does not consistently identify rating agencies.
The graph stores grade classifications and snapshot values but does not invent
agency-specific FIBO rating records.

### Analytics retain source-level meaning

`DUR`, `COV`, `BUY_YIELD`, and similar abbreviations are retained and normalized
conservatively. The graph does not claim a more specific formula than the source
documentation supports.

### “Missing” is not “false”

If an optional relationship or property is absent, the feed may not have supplied
it. Absence should not be read as a negative fact.

### No deletion inference

The loader is append/upsert oriented. A product missing from a future snapshot is
not automatically deleted or marked inactive.

### One observation is not a history

Each current bond and fund unit receives one corresponding observation from
this load; a listing receives at most one market observation when its row
supplies market data. The source-provided `asOf` dates vary, but there are not
repeated observations of a given type for the same entity. The graph therefore
cannot establish a six-month holding, theme, classification, AUM, or strategy
history.

### No holdings, control hierarchy, theme assertions, or risk corpus

The four workbooks do not contain ETF portfolio positions, benchmark
constituent weights, corporate parent/subsidiary assertions, sourced temporal
theme relationships, or prospectus risk passages. Current product-name matches
are discovery candidates only. They do not prove holdings or corporate/theme
relationships.

### Source population can be sparse or non-informative

A field definition does not guarantee usable values. In the domestic ETF/ETN
snapshot, dividend frequency and sector name are entirely blank, the main fee
field is populated for only 217 of 1,734 rows, and every populated tracking-error
value is `0.00`. See
[`../evaluation/historical-data-capabilities-2026-07-11.md`](../evaluation/historical-data-capabilities-2026-07-11.md#field-existence-is-not-data-availability)
for the audited coverage table.

### The current TTL profile formalizes classes, not all graph properties

The five TTL modules provide FIBO-aligned classes and subclass relationships.
The operational property-graph relationships and scalar properties are defined
by loader/query conventions; OWL property declarations and SHACL shapes have
not yet been added. This does not invalidate the loaded graph, but it limits how
much of its contract can be validated independently of the Python code.

## Reading Cypher queries

Cypher graph patterns use parentheses for nodes and arrows for relationships:

```cypher
(fund:Fund)-[:HAS_UNIT]->(unit:FundUnit)
```

This means “find a node labeled `Fund`, follow `HAS_UNIT`, and call the target
node `unit` if it is labeled `FundUnit`.”

Properties go in braces:

```cypher
(id:Identifier {scheme: 'ISIN', value: 'KR7069500007'})
```

Use `OPTIONAL MATCH` when a relationship may be missing.

### Find a product by identifier

```cypher
MATCH (instrument:Security)-[:HAS_IDENTIFIER]->(
  id:Identifier {scheme: 'ISIN', value: $isin}
)
RETURN labels(instrument), instrument.name, instrument.uri;
```

### See a complete ETF path

```cypher
MATCH (fund:Fund)-[:HAS_UNIT]->(unit:FundUnit)
MATCH (unit)-[:LISTED_AS]->(listing:Listing)-[:ON_MARKET]->(market:Market)
OPTIONAL MATCH (fund)-[:MANAGED_BY]->(manager:Organization)
OPTIONAL MATCH (fund)-[:TRACKS]->(benchmark:Benchmark)
OPTIONAL MATCH (listing)-[:HAS_OBSERVATION]->(price:MarketSnapshot)
WHERE unit.shortName CONTAINS 'KODEX 200'
RETURN fund.name,
       unit.shortName,
       listing.ticker,
       market.name,
       manager.name,
       benchmark.name,
       price.closePrice,
       price.asOf;
```

### Find bonds by maturity and grade

```cypher
MATCH (bond:Bond)-[:CLASSIFIED_AS]->(
  grade:Classification {scheme: 'credit-grade'}
)
WHERE bond.maturityDate >= date()
  AND bond.maturityDate < date() + duration('P2Y')
RETURN bond.name, bond.maturityDate, grade.code, bond.couponRate
ORDER BY bond.maturityDate;
```

This query does not try to compare rating strength alphabetically. A rating-scale
ordering table would be required for a reliable “AA or better” filter.

### Trace an entity to source rows

```cypher
MATCH (record:SourceRecord)-[:DESCRIBES]->(entity:Entity)
MATCH (record)-[:IN_FILE]->(file:SourceFile)
WHERE entity.uri = $entityUri
RETURN record.dataset,
       record.rowNumber,
       file.name,
       file.snapshotDate,
       file.sha256;
```

### Show all attributes accumulated for a public fund unit

```cypher
MATCH (unit:FundUnit {dataset: 'public_funds'})
MATCH (unit)-[:CLASSIFIED_AS]->(
  attribute:Classification {scheme: 'product-attribute'}
)
WHERE unit.sourceItemNumber = $itmNo
RETURN unit.name, collect(attribute.code) AS attributeCodes;
```

### Find securities with multiple listings

```cypher
MATCH (security:Security)-[:LISTED_AS]->(listing:Listing)
WITH security, collect(listing) AS listings
WHERE size(listings) > 1
OPTIONAL MATCH (security)-[:HAS_IDENTIFIER]->(isin:Identifier {scheme: 'ISIN'})
RETURN security.name,
       isin.value,
       [listing IN listings | [listing.marketCode, listing.ticker]] AS venues;
```

### Traverse the ontology

```cypher
MATCH (entity:Entity)-[:INSTANCE_OF]->(type:OntologyClass)
OPTIONAL MATCH path = (type)-[:SUBCLASS_OF*1..4]->(broader:OntologyClass)
RETURN entity.name,
       type.name,
       [node IN nodes(path) | node.name] AS broaderConcepts
LIMIT 25;
```

## GraphRAG implications

The graph is ready for structured retrieval, but embeddings have not yet been
created.

A sensible GraphRAG setup should:

- embed concise text for funds, securities, benchmarks, and document chunks;
- resolve exact identifiers before vector search when a ticker or ISIN is in the
  question;
- use Cypher for dates, prices, yields, sale flags, maturity, and numeric filters;
- expand only relevant paths such as fund → unit → listing → snapshot;
- return source file/row provenance with financial answers; and
- avoid embedding all 145,393 wide `SourceRecord` nodes as if they were separate
  products.

Ontology nodes can help map broad language such as “debt instrument” to bonds and
ETNs. They should be used as a query-planning/classification layer, not included
indiscriminately in every answer context.

## Quick glossary

| Term | Short meaning |
|---|---|
| AUM | Total assets managed by a fund |
| Benchmark | Index/reference against which a product is designed or evaluated |
| Bond | Tradable debt/loan security |
| Canonical entity | Deduplicated graph representation of the business thing |
| Classification | Reusable source category or code |
| Coupon | Contractual bond interest rate/payment term |
| Duration | Approximate sensitivity of bond price to interest-rate changes |
| ETF | Fund with units traded through exchange listings |
| ETN | Exchange-traded issuer debt note, not a pooled fund |
| Fund | Managed pool or investment vehicle |
| Fund unit | Investor's security/share-class interest in a fund |
| Identifier | Scheme-qualified code such as an ISIN |
| ISIN | International Securities Identification Number |
| Listing | Market-specific trading line and ticker |
| NAV | Assets minus liabilities, often reported per fund or per unit |
| Observation | A fact tied to an as-of date |
| Offering | Distributor/broker sale-availability state |
| Security | Identifiable financial instrument that may be held or traded |
| Source record | Exact original Excel row retained as evidence |
| Yield | Return measure derived from price and expected payments; definition varies |
