# Historical 2026-07-11 XLSX capability and contest-gap assessment

Status: **historical loaded baseline**, reviewed 2026-08-10 and relabeled as
historical 2026-07-11 pending refreshed R1 data.

This document answers a narrow historical question: what was supported by the
four provided `20260711` XLSX data workbooks and the graph loaded from them? It
aligns that answer with the requirements interpretation in
[`../requirements/contest.md`](../requirements/contest.md). Planned external
enrichment is deliberately separate in
[`../external/external-data-plan.md`](../external/external-data-plan.md). It does
not claim refreshed organizer data is present, loaded, diffed, or measured.

## Executive conclusion

The historical loaded graph is a strong product-master and provenance graph. It supports
identity, product type, manager or issuer, listings, classifications, exact
source fields, and many point-in-time product metrics where the XLSX value is
populated.

It did **not** support the three relationship-heavy example
questions end to end:

- Cambricon in China semiconductor ETFs requires dated ETF holdings and a
  security-to-company identity crosswalk.
- A six-month aerospace-theme history requires repeated historical snapshots
  and an evidence-backed, time-bounded theme relationship.
- ETFs holding EcoPro subsidiaries require both dated holdings and dated
  corporate-control relationships; the requested risk factors additionally
  require prospectus/disclosure text.

Those are data-evidence gaps as well as ontology gaps. Adding columns or edges
without authoritative observations would only create unsupported assertions.

## What is actually loaded

All four physical files have a snapshot date of 2026-07-11.

| Dataset | Source rows | Current canonical result |
|---|---:|---|
| Domestic bonds | 42,394 | 42,394 bonds |
| Korean ETF/ETN | 1,734 | 1,202 ETFs and 532 ETNs |
| Overseas ETF/ETN | 5,646 | 5,537 ETFs and 59 ETNs; 50 securities have two listings |
| Public funds | 95,619 | 11,138 conservatively identified funds and 11,138 units; one malformed row rejected |
| **Total** | **145,393** | **145,392 linked source rows** |

The graph contains 67,825 observation nodes: one `BondSnapshot` for each bond,
one `FundSnapshot` for each fund unit, and at most one `MarketSnapshot` for a
listing when market data was supplied. Different `asOf` values come from source
update fields and fallbacks; they do **not** form a historical time series for
an individual product. In particular, the files cannot establish that a theme
or holding relationship existed repeatedly during the last six months.

Every nonblank source cell is preserved on its `SourceRecord`, and normalized
fields are promoted to canonical nodes where the mapping is sufficiently clear.
See [`../data/loading-record.md`](../data/loading-record.md) for graph totals and
[`../data/xlsx-field-reference.md`](../data/xlsx-field-reference.md) for field semantics.

## Field existence is not data availability

The most consequential Korean ETF/ETN field populations are:

| Field | Populated rows | Consequence |
|---|---:|---|
| `pd_itm_no`, `pd_nm`, `cu_fund_mgmt_co` | 1,734 / 1,734 | Product identity and manager/provider lookup are reliable within the snapshot |
| `pd_risk_nm` | 1,734 / 1,734 | Current source risk labels are available; observed grades run from 1 through 6 |
| `wu_inv_ast_type`, `wu_inv_rgn` | 1,734 / 1,734 | Current broad asset/region classification is available |
| `cu_strtegy` | 1,579 / 1,734 | A short replication/active-strategy value is often available, not a strategy history |
| `du_last_aum` | 1,453 / 1,734 | AUM ranking is possible only over rows with a value and a comparable date/currency |
| `pd_net_tamt` | 1,551 / 1,734 | Total-net-asset ranking has similar missing-value constraints |
| `cu_charge_rt` | 217 / 1,734 | Main fee filtering is too sparse for a complete market recommendation |
| `cu_base_index` | 58 / 1,734 | A benchmark relationship is not generally available for domestic products |
| `pd_dvid_cycl` | 0 / 1,734 | Quarterly-distribution filtering is impossible from the supplied data |
| `pd_sect_nm` | 0 / 1,734 | A named sector cannot be recovered from this column |
| `pd_divd_amt_pshr`, `pd_dvid_yield` | 1,551 / 1,734, all `0.00` | These values cannot substantiate dividend behavior |
| `du_chas_errt` | 1,551 / 1,734, all `0.00` | The snapshot does not provide meaningful cross-product tracking-error evidence |

Other important boundaries are:

- only 881 of 42,394 bond rows populate `BUYABLE_QUANTITY`; 325 are positive;
- bond grades are present, but the source does not supply a rating-agency
  identity or an authoritative ordering/codebook;
- the overseas feed is much more complete for benchmark, strategy, fee, and
  CIK-like identifiers, but still has no portfolio positions; and
- public-fund repetition mostly represents attributes and sale variants, while
  verified parent-fund/share-class grouping remains unavailable.

Blank means “not supplied,” not zero, false, or not applicable. A suspicious or
internally inconsistent source value is retained with provenance; the loader's
successful structural validation is not a guarantee of financial correctness.

## Three independent capability layers

The earlier architecture discussion tended to group all limitations under “the
ontology.” They are more usefully separated as follows:

| Layer | Current state | Example failure |
|---|---|---|
| Semantic contract | The TTL modules define a small class/subclass application profile; operational relationship and datatype properties are currently conventions in loader code, and no SHACL shapes are present | There is no formal, validated `HoldingPosition` or time-bounded corporate-control assertion |
| Evidence | Only the supplied XLSX product masters are loaded | No row says that an ETF holds Cambricon or an EcoPro subsidiary |
| Query execution | Cypher and load/validation paths exist; the proposed DSL compiler and evaluation API do not | A valid natural-language-to-DSL-to-evidence route is still design work |

Improving only the first layer makes missing facts representable, not true.
Loading external facts without the first layer makes them difficult to validate
and explain. The planned work therefore expands the semantic contract and the
evidence pipeline together.

## Contest alignment

[`../requirements/contest.md`](../requirements/contest.md) says the system should model semantics,
connect heterogeneous facts, retrieve evidence with the appropriate mechanism,
return provenance, and abstain when evidence is insufficient. The current graph
already contributes to the first, second, and provenance goals for the supplied
product masters. The correct contest-aligned behavior for unsupported questions
is an explicit `insufficient_evidence` or snapshot-scoped empty result—not a
guess from a product name.

The examples in the contest document are target queries, not proof that all
required facts were included in the provided XLSX files. Likewise, illustrative
deck rules such as a `1–5` risk scale cannot be applied blindly: the current
Korean ETF source contains six named grades.

## Evaluation of all sample questions

Status meanings:

- **Supported**: the supplied data contains the required, sufficiently defined
  evidence.
- **Partial**: some requested facts are supported, but the full answer is not.
- **Empty**: the query is supported, but no exact entity/value matches this
  snapshot.
- **Unsupported**: a required evidence type is absent or unusable.

| # | Question | Current decision | Evidence and correct behavior |
|---:|---|---|---|
| 1 | 현재 판매 가능한 원화채권 중 AA- 이상 종목 알려줘 | **Partial** | KRW, positive buyable quantity, bond category, and exact grade are available. “AA- 이상” requires an authoritative rating scale and agency/order semantics. Until loaded, do not implement lexical comparison. |
| 2 | 국민성장펀드의 구조와 투자전략 동향 등 찾아서 알려줘 | **Partial** | Current name-matched records, risk, benchmark, region, sale state, and metrics may be returned with row provenance. Verified share-class/fund-family structure, detailed strategy text, and trends are absent. |
| 3 | 캠브리콘이 편입된 중국 반도체 ETF를 알려줘 | **Unsupported** | Product names can produce China-semiconductor candidates, but there are no holdings or Cambricon security/entity links. Do not infer a holding from an ETF name or benchmark title. |
| 4 | 최근 6개월 동안 우주항공 테마와 연결 이력이 있는 관련 ETF를 정리해줘 | **Unsupported as written** | Current names/classifications can produce present-day keyword candidates. One observation per entity cannot prove six-month history, and no sourced temporal theme assertions exist. |
| 5 | 에코프로의 자회사를 편입한 ETF 중 순자산이 큰 상품의 위험요인 알려줘 | **Unsupported as written** | Current data has some organization names and AUM/net assets. It lacks parent/subsidiary assertions, ETF holdings, and prospectus risk passages, so the candidate set cannot be established or explained. |
| 6 | 신용등급 AAAA인 채권 찾아줘 | **Empty; validity unresolved** | No raw grade matches `AAAA` in this snapshot. Calling it an invalid rating rather than simply no-match requires the missing rating vocabulary/codebook. |
| 7 | Kimi 관련 투자 상품 있어? | **Empty within current text fields** | No exact match was found. Report a snapshot-scoped empty result; do not claim that no such product exists outside the supplied data. |
| 8 | KODEX AI로봇 ETF 정보 알려줘 | **Empty exact entity** | Similar robot products exist, but the exact requested product name does not. Near matches may be offered only as clearly labeled suggestions, never silently substituted. |
| 9 | 국내 배당형 ETF 중 분기배당이고 운용보수 0.1% 이하인 상품을 추천해줘 | **Unsupported** | Dividend frequency is empty and fee coverage is sparse. “Recommend” also needs an explicit ranking/suitability policy beyond product filtering. |
| 10 | 국내 배당형 ETF 중 분기배당이고 운용보수가 낮은 상품 추천해줘 | **Unsupported** | Same missing dividend-frequency evidence; “low” and the recommendation objective must be defined. |
| 11 | TIGER 2차전지테마의 보수율과 추적오차 위험을 같이 알려줘 | **Unsupported for the requested metrics** | The target row has blank `cu_charge_rt` and `du_chas_errt = 0.00`; all populated domestic tracking-error values are `0.00`. The current risk grade is not a substitute for a tracking-error risk explanation. |

The compact checklist in [`historical-sample-questions-regression.md`](historical-sample-questions-regression.md) mirrors
these decisions.

## Safe answer contract

The answer layer should distinguish at least these outcomes:

| Outcome | Meaning | User-facing behavior |
|---|---|---|
| `answered` | Required facts were retrieved and evidenced | Answer with snapshot/as-of and row/source provenance |
| `partial` | Some requested clauses are supported | Return supported facts and enumerate the missing clauses |
| `empty` | Supported lookup/filter produced zero exact matches | Say no match was found in the 2026-07-11 supplied snapshot |
| `invalid` | A validated controlled vocabulary rejects the request | Explain the valid values and cite the vocabulary version |
| `unsupported` | Required relation, history, document, or populated field is absent | State what evidence must be fetched; do not improvise |
| `ambiguous` | Multiple entity resolutions or undefined terms remain | Ask for or expose the necessary disambiguation |

This distinction is especially important for contest “unanswerable” questions:
zero results, invalid input, and missing evidence are not interchangeable.
