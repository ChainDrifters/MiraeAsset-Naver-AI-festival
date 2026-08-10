# Planned external-data and ontology enrichment

Status: **future plan; no source below is currently loaded**. Source availability
and official documentation were reviewed on 2026-08-10.

This plan covers evidence that the four supplied XLSX workbooks do not contain.
It does not change the current capability claims in
[`current-data-capabilities.md`](current-data-capabilities.md).

## Design decision: separate modules, linked to current entities

Use both approaches, but for different kinds of data:

- add stable external identifiers and a few clearly defined current projections
  to existing `Fund`, `FundUnit`, `Security`, and `Organization` nodes;
- add separate ontology modules for many-valued, time-varying, multidimensional,
  or document-derived facts; and
- link those modules to the current canonical URIs after reviewed identity
  resolution.

Do **not** add one column per holding, subsidiary, reporting period, or XBRL
concept. Holdings and corporate relationships change over time, while XBRL
facts are qualified by entity, period, unit, taxonomy, and dimensions.

Proposed modules:

| Module | Main concepts | Why it is separate |
|---|---|---|
| `ontology/portfolio.ttl` | `PortfolioSnapshot`, `HoldingPosition`, `BenchmarkConstituentSnapshot` | Holdings are repeated and dated, with weight/quantity/value and security identity |
| `ontology/corporate.ttl` | `Company`, `EquitySecurity`, `CorporateRelationshipAssertion` | Parent/subsidiary/control is time-varying and requires an evidence basis |
| `ontology/reporting.ttl` | `Filing`, `Taxonomy`, `XbrlFact`, `XbrlContext`, `ReportingUnit` | XBRL facts are multidimensional and filings can be amended or restated |
| `ontology/disclosure.ttl` | `DisclosureDocument`, `DocumentSection`, `RiskFactor`, `EvidencePassage` | Risk and strategy evidence is narrative, versioned, and passage-addressable |
| optional `ontology/theme.ttl` | `Theme`, `ThematicAssociation`, `AssociationBasis` | Theme membership needs a definition, source, confidence, and validity interval |

`common.ttl` can import the new modules after they are implemented. Existing
product-domain modules should remain focused on the four contest feeds.

## What must be fetched

### ETF and fund detail

For each fund, unit/share class, and listing:

- authoritative identifiers: ISIN, ticker plus market/MIC, regulator filing ID,
  fund/series/share-class IDs, and issuer/manager IDs;
- full portfolio holdings or creation basket with security identifier, issuer,
  quantity, market value, currency, portfolio weight, and `asOf` date;
- benchmark identity and dated constituent weights;
- NAV, total net assets/AUM, fee components, distribution policy/history,
  tracking error and its formula/window, listing status, and currency;
- prospectus, summary prospectus, annual/semiannual or asset-management reports,
  amendments, and specifically addressable risk/strategy sections; and
- repeated snapshots at a cadence adequate for the question. Six-month
  “connection history” needs backfill across that interval, not just today's
  holdings.

### Company and organization detail

For each issuer, manager, and holding company:

- legal name, aliases and former names, jurisdiction, incorporation/registry
  number, LEI where available, regulator ID, exchange security codes, and CIK,
  DART corporation code, EDINET code, or local equivalent;
- issued securities and the security-to-legal-entity relationship;
- direct and indirect parent/subsidiary/control assertions, ownership
  percentage, relationship type, control basis, and validity dates;
- original filing/accession/report identifiers and amendment lineage; and
- XBRL/iXBRL financial facts with their complete contexts, plus relevant
  non-XBRL tables and narrative notes.

An “investment in another corporation” is evidence of ownership, not by itself
proof of subsidiary control. Control should be derived from the consolidated
subsidiary note or another explicit authoritative disclosure and recorded with
its basis.

### Controlled vocabularies and comparison data

Fetch these before adding business rules:

- rating-agency identities, symbols, scale ordering, outlook/watch status, and
  effective dates;
- the source vendor's code dictionaries and precise formulas/units for the 207
  current XLSX fields;
- ETF risk-grade scales and their versions;
- fund-family/share-class and organization-code crosswalks;
- market/MIC, currency, country, and security-identifier dictionaries; and
- dated FX rates if AUM values in different currencies will be ranked together.

These items are small compared with holdings, but they unlock safe validation
of questions such as “AA- 이상” and eliminate several current ambiguities.

## Reliable source hierarchy

Use the original regulator, exchange, filing repository, index administrator,
or fund manager before an aggregator. Store the exact source URL and access
date, and review licensing before redistributing data.

### Korea

| Need | Preferred official source | Notes |
|---|---|---|
| Company identity and filings | [OpenDART corporation-code API](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019018) and [disclosure search/original filings](https://opendart.fss.or.kr/guide/main.do?apiGrpCd=DS001) | Requires an API key; preserve `corp_code`, receipt number, filing date, and amendment status |
| Financial facts | [OpenDART XBRL financial-statement APIs and original XBRL](https://opendart.fss.or.kr/guide/main.do?apiGrpCd=DS003) | Values can change after corrected filings; retain taxonomy and report versions |
| Ownership candidates | [OpenDART 타법인 출자현황](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2019015) | Useful seed with ownership ratios, but verify subsidiary/control in the original consolidated filing |
| Korean ETF baskets and tracking | [KRX ETF disclosure description](https://regulation.krx.co.kr/contents/RGL/03/03060102/RGL03060102.jsp), [KRX Data Marketplace](https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd?locale=ko), and the manager's official product page | KRX describes PDF baskets, NAV, index composition, tracking error, and reports; verify automation and redistribution terms before ingestion |
| Fund prospectus and reports | [DART fund disclosures](https://dart.fss.or.kr/dsac001/mainF.do) and [KOFIA disclosure service manual](https://dis.kofia.or.kr/doc/dis_manual.pdf) | Capture original documents and stable section/page anchors, not only extracted summaries |

OpenDART documents a general request-limit error around 20,000 requests, while
noting that limits may differ. Use bulk endpoints, caching, retries, and a
source-specific rate policy rather than assuming an unlimited API.

KRX access through a public screen does not automatically grant downstream
redistribution. Review the applicable
[KRX market-data usage policy](https://data.krx.co.kr/inc/datasale/Market%20Data%20Usage%20Polices_ko.pdf)
for the intended service and cache/export behavior.

### United States

| Need | Preferred official source | Notes |
|---|---|---|
| Company identity and XBRL facts | [SEC EDGAR submissions and XBRL APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | No API key; use CIK and accession IDs, preserve custom-taxonomy facts from original filings when aggregated APIs omit them |
| Registered-fund holdings | [SEC Form N-PORT data sets](https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets) | N-PORT is XML/flattened filing data, not XBRL; public dissemination and update cadence must be respected |
| Subsidiaries and narrative risks | Original EDGAR filing, exhibits such as the subsidiary list, and prospectus/annual-report sections | These relationships and narratives are often outside standardized XBRL facts |

SEC automated access must use an identifying user agent and stay within the
[current fair-access guidance](https://www.sec.gov/about/developer-resources),
which limits aggregate traffic to no more than 10 requests per second.

### Japan, European Union, United Kingdom, and China

There is no single cross-country equivalent with uniform coverage or access
semantics. Use jurisdiction adapters behind one internal contract.

| Jurisdiction | Official starting point | Constraint to encode |
|---|---|---|
| Japan | [FSA EDINET](https://disclosure2.edinet-fsa.go.jp/week0020.aspx), its API v2, taxonomy, and code lists | API use requires registration/key; preserve EDINET document and filer codes and original XBRL |
| EU/EEA | [ESMA ESEF reporting guidance](https://www.esma.europa.eu/issuer-disclosure/electronic-reporting) and the issuer's national Officially Appointed Mechanism | ESEF defines XHTML/iXBRL requirements and taxonomy, but filings are obtained through national repositories rather than assuming one universal ESMA data API |
| United Kingdom | [Companies House XBRL/iXBRL accounts bulk data](https://www.gov.uk/guidance/companies-house-data-products) and [FCA National Storage Mechanism](https://www.fca.org.uk/markets/primary-markets/regulatory-disclosures/national-storage-mechanism) | Companies House coverage depends on electronic filing; NSM is the listed-issuer disclosure source and exposes tagged annual reports |
| China | The issuer's official home exchange and original filings; for SSE issuers, [SSE XBRL-derived company information](https://english.sse.com.cn/markets/dataservice/xbrl/companyinfo/) | SSE itself warns that displayed XBRL-derived values are for reference and the corresponding report is controlling; test programmatic access and licensing before committing to automation |

For Cambricon specifically, begin entity resolution with its
[official SSE security record](https://star.sse.com.cn/star/en/marketdata/snapshot/c/5485110.shtml)
and filing identifiers, then attach Korean/English/Chinese aliases. Do not use a
translated name alone as the holdings join key.

Official fund-manager holdings files may fill timing or coverage gaps, but they
should be labeled as manager-published evidence and reconciled against
regulatory filings rather than silently replacing them.

## XBRL is an ingestion format, not the whole domain ontology

XBRL and RDF/OWL solve different problems:

- XBRL/iXBRL communicates filing facts according to a reporting taxonomy;
- the application ontology defines product, portfolio, company, control, theme,
  and evidence relationships used by retrieval; and
- a versioned mapping connects selected XBRL concepts and dimensions to that
  ontology without discarding the original filing semantics.

For each XBRL fact, retain at minimum:

```text
filing/version + taxonomy/version + concept QName + value
+ reporting entity + instant or duration + unit
+ decimals/precision + explicit/typed dimensions + language
+ filing date + period end + amendment/restatement lineage
```

This follows the
[XBRL developer fact model](https://www.xbrl.org/the-standard/how/getting-started-for-developers/):
concept, entity, period, unit, and additional dimensions jointly determine
meaning. Use a conformant XBRL processor and keep the original taxonomy package
and instance/iXBRL document. Do not parse only the rendered HTML or flatten
facts into company columns with their contexts removed.

ETF portfolio disclosures are not necessarily XBRL. KRX baskets, issuer CSVs,
and SEC Form N-PORT XML should remain in their authoritative source formats at
the raw layer, then map into the same `PortfolioSnapshot` model. “XBRL
compliant” must not be used as a reason to relabel non-XBRL data.

## Minimum relationship shapes

Use assertion/snapshot nodes when a bare edge would lose time or provenance:

```text
(FundUnit)-[:HAS_PORTFOLIO_SNAPSHOT]->(PortfolioSnapshot)
(PortfolioSnapshot)-[:HAS_POSITION]->(HoldingPosition)
(HoldingPosition)-[:OF_SECURITY]->(Security)
(Security)-[:ISSUED_BY]->(Company)

(CorporateRelationshipAssertion)-[:PARENT]->(Company)
(CorporateRelationshipAssertion)-[:CHILD]->(Company)

(ThematicAssociation)-[:SUBJECT]->(Fund|Security)
(ThematicAssociation)-[:THEME]->(Theme)

(DisclosureDocument)-[:HAS_SECTION]->(DocumentSection)
(DocumentSection)-[:DESCRIBES_RISK_OF]->(Fund|FundUnit)
```

Every snapshot/assertion must carry source, `asOf` or validity interval,
publication time, retrieval time, and extraction method. Derived theme or
control assertions should also carry rule/model version and confidence; facts
explicitly stated by an authoritative source should be distinguishable from
inference.

## Evidence needed for the three difficult questions

| Question | Minimum new evidence |
|---|---|
| Cambricon in China semiconductor ETFs | Cambricon legal entity and listed-security identifiers/aliases; dated ETF holdings or benchmark constituents; ETF identity and region/sector evidence |
| Six-month aerospace-theme history | A controlled theme definition; at least six months of holdings, benchmark, methodology, and/or official objective snapshots; time-bounded association evidence and change detection |
| Largest ETF holding an EcoPro subsidiary and its risks | Dated EcoPro control hierarchy; security-to-subsidiary mapping; same-date ETF holdings; comparable AUM/net assets; current prospectus risk sections with passage provenance |

For the third question, rank only after the qualifying ETF set is proven. Use a
declared AUM metric/date/currency and do not mix `du_last_aum` with
`pd_net_tamt` silently.

## Ingestion and validation gates

```text
official raw source
  -> immutable object + checksum + retrieval metadata
  -> format-specific parser (XBRL, XML, CSV, PDF/document)
  -> source-schema validation
  -> identity resolution with reviewed crosswalk
  -> ontology mapping and SHACL/business-rule validation
  -> versioned graph/fact/document indexes
  -> answerability and provenance tests
```

Required gates before a source is called production-reliable:

- terms, licensing, redistribution rights, authentication, and rate limits are
  recorded;
- coverage and publication lag are measured, not assumed;
- amendments, deletions, and restatements are reproducible;
- raw-to-normalized lineage reaches the exact filing row/fact/passage;
- entity matches are deterministic or reviewable, never name-only merges;
- temporal queries cannot see evidence published after their cutoff; and
- source outages return stale/partial status rather than fabricated freshness.

For a contest cutoff, freeze the external evidence set by `publishedAt` and
retain `effectiveAt` and `retrievedAt` separately. A later correction may be
stored, but must not silently leak into a historical answer.

## Recommended delivery order

1. Obtain the current vendor field/code dictionaries and rating scales; add
   property declarations and SHACL for already loaded data.
2. Add canonical company/security identifiers and reviewed crosswalks.
3. Add Korean ETF holdings, fee/distribution/tracking data, and official fund
   disclosure documents.
4. Add Korean corporate-control evidence from OpenDART original filings.
5. Add overseas holdings adapters, starting with SEC N-PORT/EDGAR because most
   current overseas rows already expose a CIK-like value.
6. Backfill monthly or event-driven portfolio/theme snapshots and add document
   passage retrieval.
7. Add EDINET, ESEF/OAM, Companies House/FCA, and Chinese-exchange adapters as
   actual product coverage requires them.

Each phase should extend the answerability matrix and test abstention before it
adds more natural-language claims.
