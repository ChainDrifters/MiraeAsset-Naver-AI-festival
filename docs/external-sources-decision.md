# External sources stop/go decision — Phase 3, D+1

Status: **decision record**, decided 2026-08-19.

This document records the Phase 3 D+1 license stop/go decision required by
the work plan (Phase 3.1) under the source hierarchy of
[`external-data-plan.md`](external-data-plan.md). It changes no code and loads
no data. It records decisions and verified facts only.

| Reference | Value |
|---|---|
| Decision date | 2026-08-19 |
| Contest data reference snapshot | 2026-07-11 |
| Backfill window | 2026-01-11 → 2026-07-11 |

## Decision table

| # | Source path | Decision | Reason |
|---|---|---|---|
| 1 | KRX automated ETF basket/PDF/API acquisition | **NEEDS-CONTRACT** (not GO) | The official KRX service flow requires login, approval, and an API key. Index-information and fund-information licenses, including constituent files, are contract-governed. Until written approval exists: no scraping, no automation, no redistribution of KRX-sourced data. |
| 2 | Korean manager-published holdings/baskets | **GO** (fallback path) | Managers publish holdings/basket files on their official product pages without a contract gate. Every snapshot from this path is labeled `evidenceBasis="manager_published"` and preserves the source URL, publication date, and checksum. This is manager-published evidence; it is not regulatory evidence. |
| 3 | SEC Form N-PORT public data sets | **GO** | No authentication. Automated access must send a real identifying User-Agent and stay within 10 requests per second under current fair-access guidance. Public data only, quarterly under the current cadence; dissemination lag is recorded per snapshot. |

## Official references

Read 2026-08-19. These are the exact URLs the decisions above are based on.

KRX:

- Open API license — fund information:
  https://openapi.krx.co.kr/contents/OPP/DATA/OPPDATA004.jsp
- Open API license — index information:
  https://openapi.krx.co.kr/contents/OPP/DATA/OPPDATA005.jsp
- ETF basket PDF explanation (global site):
  https://global.krx.co.kr/contents/GLB/03/0303/0303090203/GLB0303090203.jsp
- Open API usage flow (login/approval/key):
  https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp

KOFIA:

- Fund portal: https://fund.kofia.or.kr/fs/fund/html/index.html

SEC:

- Form N-PORT data sets:
  https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets
- Fair access / developer resources:
  https://www.sec.gov/about/developer-resources

## Verified facts vs candidate availability

Verified on official pages, 2026-08-19:

- The KRX license and flow pages above describe an approval-based,
  contract-governed service for fund/index information including constituent
  files (decision 1 basis).
- Every product in the target universe below has an official issuer page with
  live or downloadable holdings information.
- The closest dated holdings files found so far are dated around 2026-06-30
  and 2026-07-31 for KraneShares and PLUS products; some live pages carry
  August-dated data without a dated archive link.

Candidate availability, **not** verified facts:

- Whether each target product has archived, dated holdings files covering the
  full backfill window 2026-01-11 → 2026-07-11. No claim is made that six
  monthly historical files exist for any product until the archived files are
  verified. Per-month coverage is recorded per snapshot as it is confirmed.

## Target product universe

Issuer pages verified 2026-08-19. A dash means the identifier was not recorded
at verification time; it is filled by the Phase-2 crosswalk, not by inference.

| Product | Code | Listing venue | ISIN | Official issuer page |
|---|---|---|---|---|
| KraneShares KSTR (US) | KSTR | NYSE Arca | US5007676944 | https://kraneshares.com/etf/kstr/ |
| KraneShares KSTR UCITS | — | LSE | IE00BKPJY434 | https://kraneshares.eu/etf/kstrln/ |
| VanEck China Semiconductor ETF | SMHC | Nasdaq | — | https://www.vaneck.com/us/en/investments/china-semiconductor-etf-smhc |
| Global X China Semiconductor ETF | HKEX 3191/9191 | HKEX | HK0000637832 | https://www.globalxetfs.com.hk/funds/global-x-china-semiconductor-etf/ |
| PLUS K방산 | 449450 | KRX | — | https://www.plusetf.co.kr/product/detail?n=006192 |
| PLUS 우주항공 | 421320 | KRX | — | https://www.plusetf.co.kr/product/detail?n=006344 |
| PLUS 글로벌방산 | 496770 | KRX | — | https://www.plusetf.co.kr/product/detail?n=006377 |
| PLUS 글로벌HBM반도체 | 442580 | KRX | — | https://www.plusetf.co.kr/product/detail?n=006236 |
| PLUS 일본반도체소부장 | 464920 | KRX | — | https://www.plusetf.co.kr/product/detail?n=006366 |

## Adapter normalized minimum fields

Every holdings/basket record, regardless of source path, normalizes to at
least the following. Missing source values stay null; they are never imputed.

| Field | Minimum content |
|---|---|
| `fund_isin` | ISIN of the fund unit after reviewed identity resolution; never a name-only join |
| `constituent_isin` | ISIN of the held security when the source supplies it; otherwise the reviewed crosswalk resolves it |
| `constituent_name` | Source-published name, retained verbatim as provenance; not a merge key |
| `weight` | Portfolio weight normalized to a fraction; derived when the source publishes only value or quantity |
| `as_of` | Holdings date stated by the source (snapshot date) |
| `source_quantity` | Quantity as published, nullable |
| `source_currency` | Currency of `source_market_value`, nullable |
| `source_market_value` | Market value as published, nullable |
| `weight_source` | How weight was obtained: `source_published` or `derived_from_value` |
| `identifier_method` | How constituent identity was established: `source_isin`, `crosswalk`, or `unresolved` |
| `published_at` | Publication timestamp of the file/filing; the cutoff-freeze key |
| `accession` / `source_document_id` | Filing accession number or document/file identifier of the source document |
| `source_url` | Exact URL the raw artifact was fetched from |

## Binding rule at D+2

- The fallback path (decision 2 + decision 3) proceeds regardless of KRX
  approval status. It is the pre-approved path.
- KRX automation — scraping, automated basket/PDF/API acquisition, and
  redistribution — remains disabled until written approval exists. Only a
  recorded written approval flips decision 1 to GO.
