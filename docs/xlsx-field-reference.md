# XLSX field reference

This document explains every column in the four financial-product data
workbooks under `xlsx_data/`. It is written for readers without a finance
background.

The graph structure is explained separately in
[`graph-model-guide.md`](graph-model-guide.md). Loading commands and validation
results are in [`data-loading.md`](data-loading.md).

The normalized fields exposed to applications are specified in
[`query-dsl-spec.md`](query-dsl-spec.md).

Observed field population and contest-question consequences are summarized in
[`current-data-capabilities.md`](current-data-capabilities.md). A column's
presence in this reference does not mean that the current data rows populate it.

## How to read this reference

Every nonblank value from every column is preserved verbatim on its
`SourceRecord`. The **Graph treatment** column below says whether the loader also
promoted the value into a normalized canonical node, relationship, or dated
observation.

Interpretation status:

| Status | Meaning |
|---|---|
| **Source** | The schema workbook supplied a Korean field name; the English explanation translates or clarifies it. |
| **Parallel** | The schema omitted a description, but the same field is explicitly described in the Korean ETF schema. |
| **Inferred** | Meaning is inferred from the abbreviation, values, and financial convention. |
| **Ambiguous** | The broad purpose is apparent, but an exact formula, unit, or code definition requires the vendor's data dictionary. |

“Raw only” does not mean discarded. It means the value is available on
`SourceRecord` under its original field name but was not copied into a friendly
canonical property.

## Important unit and code cautions

The schema workbooks do not provide a complete unit/code dictionary.

- Dates are generally encoded as `YYYYMMDD`, even when the declared type is
  numeric or timestamp.
- Return, fee, yield, tracking-error, and divergence fields appear to use
  **percentage points**, not decimal fractions. For example, `17.10` normally
  means 17.10%, not 1,710%. The loader does not rescale them.
- Price and monetary fields use the product or trading currency unless another
  convention is specified by the source.
- Share counts and quantities are counts, but the vendor may apply lot-size or
  minimum-trade rules not present in these files.
- Codes such as `PD_RISK_GCD_13`, `C103`, `10`, or `1EE11Z...` are opaque source
  codes. Their names should come from an authoritative codebook, not guesses.
- A blank value means “not supplied in this snapshot,” not necessarily zero,
  false, or not applicable.

## Common abbreviations

These patterns make the column names easier to read. Some prefix expansions are
inferred from usage rather than formally documented.

| Abbreviation | Likely meaning |
|---|---|
| `pd_` / `PD_` | Product/security master field |
| `cu_` | Common or relatively static product/fund information |
| `du_` | Daily-updated value |
| `ru_` / `nru_` | Real-time or near-real-time market value |
| `wu_` | Weekly/reference classification value |
| `fd_` | Fund field |
| `itm` | Item/instrument |
| `bmrk` | Benchmark |
| `isu` | Issue/issuance |
| `mat` | Maturity |
| `amt` | Amount |
| `rt` / `r` | Rate or ratio |
| `dt` | Date |
| `nm` | Name |
| `abrv` | Abbreviated/short name |
| `eng` / `eabrv` | English / abbreviated English |
| `cd` | Code |
| `desc` | Description of a code |
| `yn` | Yes/no flag |
| `pshr` | Per share/unit |
| `clpr`, `hpr`, `lpr`, `opr` | Close, high, low, and open price |
| `val`, `vol` | Trading value and trading volume |
| `er` / `ern_r` | Return/earnings rate |
| `wk`, `mm`, `yr` | Week, month, year |
| `YTD` | Year to date |
| `NDY` | Next-day value |
| `AUM` | Assets under management |
| `NAV` | Net asset value |

## Domestic bond master: 40 fields

File: `PRBD01N001_국내채권마스터_20260711_datarows.xlsx`

The bond schema supplies types but no Korean field descriptions. The meanings
below are therefore inferred. Identity, dates, currency, names, and common bond
analytics are high-confidence; exact yield formulas, rating-source distinctions,
and some vendor codes remain ambiguous.

| Field | Type | Plain-language meaning | Status and graph treatment |
|---|---|---|---|
| `PD_NO` | text | Product/security number; values have the shape of Korean ISINs. | **Inferred, high.** Canonical `Bond` key and `Identifier`; scheme is ISIN when valid. |
| `PD_EXG_MKT` | text | Trading-market mode, principally exchange-traded (`장내`) versus over-the-counter (`장외`). | **Inferred, high.** Stored on `Bond`; `장내` creates a `Listing`. |
| `PD_NM` | text | Full product/bond name. | **Inferred, high.** `Bond.name`. |
| `PD_ABRV_NM` | text | Short Korean product name. | **Inferred, high.** `Bond.shortName`. |
| `PD_ENG_NM` | text | Full English product name. | **Inferred, high.** `Bond.englishName`. |
| `PD_ABRV_ENG_NM` | text | Short English product name. | **Inferred, high.** `Bond.shortEnglishName`. |
| `PD_CTRY_CD` | text | Product/issuer country code. | **Inferred, high.** `Bond.countryCode`. |
| `PD_PBCM` | text | Issuing/publishing organization name; e.g. `대한민국` for government bonds. | **Inferred, medium.** Creates `Organization` and `ISSUED_BY`; exact source acronym is undocumented. |
| `STD_PD_MCLS_NM` | text | Standard product main-class name, such as government/public or corporate bond. | **Inferred, high.** `bond-main-category` classification. |
| `STD_PD_SCLS_NM` | text | Standard product subclass name. | **Inferred, high.** `bond-subcategory` classification. |
| `BD_KND` | text | Bond kind/type in the source taxonomy. | **Inferred, high.** `bond-kind` classification. |
| `CURR_CD` | text | Denomination currency code, usually `KRW`. | **Inferred, high.** `Bond.currency`. |
| `ISU_BAL_AMT` | double | Aggregate outstanding issuance balance. | **Inferred, high.** `Bond.issueOutstandingAmount`; not treated as per-bond face value. |
| `ISU_DT` | numeric date | Issue date. | **Inferred, high.** Parsed into `Bond.issueDate`. |
| `MAT_DT` | numeric date | Contractual maturity date. | **Inferred, high.** Parsed into `Bond.maturityDate`. |
| `SRFC_IRT` | number | Stated/surface interest rate, normally the coupon rate. | **Inferred, medium-high.** `Bond.couponRate`; exact treatment for floating/zero-coupon bonds needs terms documentation. |
| `PD_EVCO_CRD_GRD` | text | Product credit grades from evaluation/rating companies; values may contain several grades. | **Ambiguous.** Used as fallback credit-grade classification; rating agencies and ordering are not supplied. |
| `PD_RISK_GCD` | integer/code | Product risk group/grade code. | **Inferred, medium.** Opaque `risk-code` classification; do not treat the number as a score without a codebook. |
| `PD_STD_INFO_UPDATE` | numeric date | Standard product-information update/as-of date. | **Inferred, high.** Preferred `BondSnapshot.asOf` date. |
| `BUY_YIELD` | number | Yield quoted or calculated for a purchase. | **Ambiguous.** `BondSnapshot.buyYield`; exact yield convention is undocumented. |
| `CORP_PRETAX_YIELD` | number | Corporate/customer pre-tax yield. | **Inferred, medium.** `corporatePretaxYield`; formula and customer category require confirmation. |
| `CORP_AFTER_TAX_YIELD` | number | Corporate/customer after-tax yield. | **Inferred, medium.** `corporateAfterTaxYield`; tax assumptions require confirmation. |
| `AFTER_TAX_YIELD` | number | General after-tax yield. | **Inferred, medium.** `afterTaxYield`; taxpayer assumptions are not encoded. |
| `PREF_TAX_YIELD` | number | Yield under preferential-tax treatment. | **Inferred, medium.** `preferentialTaxYield`. |
| `AVG_ANNUAL_TAX_YIELD` | number | Average annual yield after/applying tax. | **Ambiguous.** `averageAnnualTaxYield`; precise annualization/tax formula needs the vendor definition. |
| `DEPO_EQUIV_YIELD_154` | number | Deposit-equivalent yield under an apparent 15.4% tax convention. | **Inferred, medium.** `depositEquivalentYield154`; confirm the `154` convention before financial use. |
| `BUYABLE_QUANTITY` | number | Quantity currently available to purchase through the source channel. | **Inferred, high.** `BondSnapshot.buyableQuantity`; temporary distribution/inventory state. |
| `REMAINING_DAYS` | number | Days remaining to maturity or the relevant end date. | **Inferred, high.** `BondSnapshot.remainingDays`. |
| `DUR` | number | Duration analytic. | **Ambiguous.** `durationRaw`; source does not say modified, effective, Macaulay, etc. |
| `COV` | number | Convexity analytic. | **Inferred, medium-high.** `convexityRaw`; exact scaling/formula is undocumented. |
| `NDY_DUR` | number | Next-day duration analytic. | **Inferred, medium.** `nextDayDurationRaw`. |
| `NDY_COV` | number | Next-day convexity analytic. | **Inferred, medium.** `nextDayConvexityRaw`. |
| `EVAL_PRICE` | number | Evaluated/reference bond price. | **Inferred, high.** `evaluationPrice`; not labeled clean or dirty by the source. |
| `APPLIED_YIELD` | number | Yield applied when calculating the evaluated price. | **Inferred, medium-high.** `appliedYield`; exact convention is undocumented. |
| `DIRTY` | number | Dirty price, normally price including accrued interest. | **Inferred, high.** `dirtyPrice`. |
| `NDY_EVAL_PRICE` | number | Next-day evaluated/reference price. | **Inferred, high.** `nextDayEvaluationPrice`. |
| `NDY_APPLIED_YIELD` | number | Next-day applied yield. | **Inferred, medium.** `nextDayAppliedYield`. |
| `NDY_DIRTY` | number | Next-day dirty price. | **Inferred, high.** `nextDayDirtyPrice`. |
| `CRD_GRD` | text | Current/selected credit grade. | **Ambiguous.** Stored on `BondSnapshot` and as a classification; exact distinction from `PD_EVCO_CRD_GRD` is not documented. |
| `CRD_GRD_DT` | numeric date | As-of date for `CRD_GRD`. | **Inferred, high.** `BondSnapshot.creditGradeDate`. |

## Korean ETF/ETN master: 73 fields

File: `PREF01N001_국내ETF마스터_20260711_datarows.xlsx`

This schema supplies Korean labels for nearly every field. Despite the filename,
the data contains both ETFs and ETNs.

### Common/static fund and strategy fields

| Field | Type | Plain-language meaning | Status and graph treatment |
|---|---|---|---|
| `cu_base_index` | text | Base/underlying index the product is designed around. | **Source.** Creates `Benchmark` and `TRACKS` when populated; name also retained on fund/ETN. Populated in only 58 of 1,734 current rows. |
| `cu_charge_etc_rt` | text/rate | Other-expense rate beyond the main management fee. | **Source.** `otherFeeRate`; likely percentage points. |
| `cu_charge_rt` | text/rate | Total management/expense fee rate. | **Source.** `feeRate`; likely percentage points. Populated in only 217 of 1,734 current rows. |
| `cu_fund_mgmt_co` | text | Fund management company; for ETNs used as the available issuer/provider field. | **Source.** Creates `Organization`; `MANAGED_BY` for funds or `ISSUED_BY` for ETNs. |
| `cu_lev_fector` | text/number | Leverage/inverse multiple, e.g. 1, 2, or -1. | **Source.** `leverageFactor`; spelling `fector` is from source. |
| `cu_strtegy` | text | Investment/management strategy. | **Source.** `strategy`; spelling is from source. |
| `cu_upt_dt` | text date | Last update date for common/static product information. | **Source.** Used as fallback fund-observation date. |

### Daily market, NAV, return, and activity fields

| Field | Type | Plain-language meaning | Status and graph treatment |
|---|---|---|---|
| `du_bpr` | number | Base/reference price (`기준가`). | **Source.** `MarketSnapshot.basePrice`. |
| `du_chas_errt` | number | Tracking-error rate: how much performance deviates from the target index. | **Source.** Raw only; exact formula/window needs confirmation. All 1,551 populated current values are `0.00`, so the field does not support a meaningful comparison in this snapshot. |
| `du_clpr` | number | Closing price. | **Source.** `MarketSnapshot.closePrice`. |
| `du_diff_rt` | number | Market/NAV divergence or premium/discount rate (`괴리율`). | **Source.** `MarketSnapshot.priceChangeRate` in the current loader; the property name is generic and should not be read as ordinary daily return. |
| `du_er_1d` | number | One-day return. | **Source.** `FundSnapshot.return1d`. |
| `du_er_1m` | number | One-month return. | **Source.** `FundSnapshot.return1m`. |
| `du_er_1y` | number | One-year return. | **Source.** `FundSnapshot.return1y`. |
| `du_er_3m` | number | Three-month return. | **Source.** `FundSnapshot.return3m`. |
| `du_er_6m` | number | Six-month return. | **Source.** `FundSnapshot.return6m`. |
| `du_er_ytd` | number | Year-to-date return. | **Source.** `FundSnapshot.returnYtd`. |
| `du_hpr` | number | Daily high price. | **Source.** `MarketSnapshot.highPrice`. |
| `du_last_aum` | number | Latest assets under management. | **Source.** `FundSnapshot.assetsUnderManagement`. |
| `du_last_nav` | number | Latest net asset value, apparently unit-level from its magnitude. | **Source.** `FundSnapshot.netAssetValue`; exact whole-fund/per-unit convention should be confirmed. |
| `du_lpr` | number | Likely daily low price from the `lpr` abbreviation and overseas parallel. The Korean schema says `시가` (opening price), which conflicts with that interpretation. | **Ambiguous.** Current loader maps to `MarketSnapshot.lowPrice`; verify with the vendor before relying on it. |
| `du_nav_rnf_amt` | number | Change amount from the previous day's NAV. | **Source.** `FundSnapshot.navChangeAmount`. |
| `du_nav_yday` | number | Previous day's NAV. | **Source.** `FundSnapshot.previousNav`. |
| `du_upt_dt` | date/timestamp | Daily-data update date. | **Source.** Observation date fallback. |
| `du_val_1d` | number | Trading value/turnover for the day. | **Source.** `MarketSnapshot.tradingValue1d`. |
| `du_val_1m` | number | Average daily trading value over one month. | **Source.** Raw only. |
| `du_val_5d` | number | Average daily trading value over five days. | **Source.** Raw only. |
| `du_vol_1d` | number | Trading volume for the day. | **Source.** `MarketSnapshot.tradingVolume1d`. |
| `du_vol_avg_1m` | number | Average trading volume over one month. | **Source.** `MarketSnapshot.averageVolume1m`. |
| `du_vol_avg_5d` | number | Average trading volume over five days. | **Source.** `MarketSnapshot.averageVolume5d`. |
| `nru_mkt_diff_rt` | number | Intraday market-price/iNAV divergence rate. | **Source.** `MarketSnapshot.realtimeMarketDifferenceRate`. |
| `nru_mkt_inav` | number | Intraday indicative NAV (iNAV). | **Source.** `MarketSnapshot.realtimeIndicativeNav`. |

### Product identity, financials, listing, sale, and classification fields

| Field | Type | Plain-language meaning | Status and graph treatment |
|---|---|---|---|
| `pd_abrv_nm` | text | Short product name. | **Source.** Fund/unit or ETN `shortName`. |
| `pd_circ_net_tamt` | number | Net assets associated with units in circulation. | **Source.** Raw only; distinction from `pd_net_tamt` is vendor-specific. |
| `pd_circ_stk_cnt` | number | Number of units/shares in circulation. | **Source.** Raw only. |
| `pd_curr_cd` | text | Product currency code, often encoded like `CURR_CD_KRW`. | **Source.** Canonical `currency`; code normalization is not expanded. |
| `pd_curr_nm` | text | Product currency name, e.g. Korean won. | **Source.** Raw only. |
| `pd_divd_amt_pshr` | number | Distribution/dividend amount per share. | **Source.** Raw only. All 1,551 populated current values are `0.00`. |
| `pd_dvid_cycl` | text | Distribution/dividend cycle or frequency. | **Source, wording appears truncated (`당주기`).** Raw only and blank for all 1,734 current rows. |
| `pd_dvid_yield` | number | Distribution/dividend yield. | **Source.** Raw only; likely percentage points. All 1,551 populated current values are `0.00`. |
| `pd_exg_mkt_cd` | text | Exchange code. | **Source; schema key.** Part of `Listing` and `Market` identity. |
| `pd_exg_mkt_nm` | text | Exchange name. | **Source.** `Listing.marketName` / `Market.name`. |
| `pd_grp_no` | text | Product group/type: `ETF` or `ETN`. | **Source.** Determines whether a `Fund`/`FundUnit` or `ExchangeTradedNote` is created. |
| `pd_itm_no` | text | Product/security number; Korean rows are ISIN-shaped. | **Source; schema key.** Security identity plus ISIN/source identifier. |
| `pd_itm_no_ma` | text | Mirae Asset item/listing number, used like a ticker (e.g. `A069500`). | **Source; schema key.** `Listing.ticker` and ticker identifier. |
| `pd_lst_price` | number | Product face/par or initial listing price (`상품액면가`). | **Source.** `Listing.listingPrice`; exact convention needs confirmation. |
| `pd_lst_stk_cnt` | number | Number of listed shares/units. | **Source.** `Listing.listedShareCount`. |
| `pd_lste_dt` | text date | Product trading/end-of-listing date. `99991231` commonly means no scheduled end. | **Source.** Raw only. |
| `pd_lstg_dt` | text date | Date from which the product can trade/list. | **Source.** `Listing.listingDate`. |
| `pd_mkt_id` | text | Trading-market identifier, e.g. `STK`. | **Source.** Used as market fallback. |
| `pd_mkt_nm` | text | Human-readable trading market, e.g. `유가증권`. | **Source.** `Market.name`. |
| `pd_nav_pshr` | number | NAV per share/unit. | **Source.** `FundSnapshot.navPerShare`. |
| `pd_net_ast_pshr` | number | Net assets per share/unit. | **Source.** `FundSnapshot.netAssetsPerShare`. |
| `pd_net_prft_pshr` | number | Net profit per share/unit. | **Source.** `FundSnapshot.netProfitPerShare`. |
| `pd_net_rt_ast_pshr` | number | Source-labeled net-asset ratio per share. | **Source but formula unclear.** `FundSnapshot.netReturnAssetsPerShare`; confirm exact metric. |
| `pd_net_tamt` | number | Total net assets. | **Source.** `FundSnapshot.netAssetTotal`. |
| `pd_nm` | text | Full product name. | **Source.** Names on fund/unit or ETN. |
| `pd_pen_risk_nm` | text | Pension-account risk category, e.g. safe/risk asset. | **Source.** Raw only. |
| `pd_pen_tr_yn` | text flag | Whether pension-account trading is allowed. | **Source.** Raw only. |
| `pd_risk_cd` | text | Product risk-grade code. | **Source.** `risk` classification code. |
| `pd_risk_nm` | text | Human-readable product risk grade. | **Source.** `risk` classification name. All current rows are populated and the observed labels span grades 1 through 6; do not apply the contest deck's illustrative 1–5 range. |
| `pd_sale_yn` | text flag | Whether the product is available for sale through the source channel. | **Source.** `Offering.availableForSale`. |
| `pd_sect_cd` | text | ETF sector code. | **Source.** `sector` classification code. |
| `pd_sect_nm` | text | ETF sector name. | **Source.** `sector` classification name, but blank for all 1,734 current rows. |
| `pd_spac_yn` | text flag | SPAC flag inherited from a broader product schema. | **Source.** Raw only; normally not central to ETF analysis. |
| `pd_stk_cnt` | number | Current/outstanding share count. | **Source.** Raw only; distinction from circulating/listed counts is vendor-specific. |
| `pd_tr_yn` | text flag | Product trading-suspension flag (`상품거래정지여부`; schema has a typo). | **Source.** `Offering.tradingHalted`. |
| `ru_mkt_price` | number | Real-time/current market price. | **Source.** `MarketSnapshot.realtimeMarketPrice`; zero can mean unavailable rather than a real zero price. |
| `ru_mkt_volume` | number | Real-time/current market volume. | **Source.** `MarketSnapshot.realtimeMarketVolume`. |
| `wu_core_yn` | text flag | Core-ETF designation. | **Source.** Raw only. |
| `wu_inv_ast_type` | text | Investment asset class/type. | **Source.** `investment-asset-type` classification. |
| `wu_inv_rgn` | text | Investment region. | **Source.** `investment-region` classification. |
| `wu_upt_dt` | text date | Weekly/reference-data update date. | **Source.** Raw only. |

## Overseas ETF/ETN master: 49 fields

File: `PREF02N001_해외ETF마스터_20260711_datarows.xlsx`

This schema provides types but no Korean descriptions. Most fields directly
parallel fields explicitly named in the Korean ETF schema.

### Common/static and daily fields

| Field | Type | Plain-language meaning | Status and graph treatment |
|---|---|---|---|
| `cu_base_index` | text | Base/underlying index. | **Parallel.** Creates `Benchmark` and `TRACKS`. |
| `cu_charge_rt` | number | Total management/expense fee rate. | **Parallel.** `feeRate`; likely percentage points. |
| `cu_etn_yn` | text flag | Whether the row is an ETN. | **Inferred, high.** `Y` forces ETN modeling. |
| `cu_fund_mgmt_co` | text | Fund manager or available ETN issuer/provider name. | **Parallel.** Creates `Organization` and manager/issuer relationship. |
| `cu_index_repl_mthd` | text | Index replication method, e.g. physical, full, sampled, optimized, synthetic. | **Inferred, high.** `indexReplicationMethod`. |
| `cu_index_tracking_yn` | text flag | Whether the product is intended to track an index. | **Inferred, high.** `indexTracking`. |
| `cu_inverse_short_yn` | text flag | Whether the product is inverse or short. | **Inferred, high.** `inverseOrShort`. |
| `cu_lev_fector` | number | Leverage/inverse multiple. | **Parallel.** `leverageFactor`; source spelling retained. |
| `cu_strtegy` | text | Investment strategy/objective text. | **Parallel.** `strategy`. |
| `cu_upt_dt` | text date | Common/static information update date. | **Parallel.** Fund-observation fallback date. |
| `du_base_dt_match_yn` | text flag | Whether relevant daily base/as-of dates match. | **Inferred, medium.** Raw only; exact pair of dates compared is undocumented. |
| `du_bpr` | number | Base/reference price. | **Parallel.** `MarketSnapshot.basePrice`. |
| `du_clpr` | number | Closing price. | **Parallel.** `MarketSnapshot.closePrice`. |
| `du_clpr_base_dt` | text date | As-of/base date for the closing price. | **Inferred, high.** Preferred `MarketSnapshot.asOf`. |
| `du_clpr_src` | text | Source table/provider for the closing price. | **Inferred, high.** `MarketSnapshot.closePriceSource`. |
| `du_diff_rt` | number | Market/NAV divergence or premium/discount rate. | **Parallel.** Stored as `priceChangeRate` in the current loader; interpret as divergence, not ordinary return. |
| `du_er_1d` | number | One-day return. | **Parallel.** `FundSnapshot.return1d`. |
| `du_hpr` | number | Daily high price. | **Parallel.** `MarketSnapshot.highPrice`. |
| `du_last_aum` | number | Latest assets under management. | **Parallel.** `FundSnapshot.assetsUnderManagement`. |
| `du_last_nav` | number | Latest NAV. | **Parallel.** `FundSnapshot.netAssetValue`; confirm whole-fund versus unit convention. |
| `du_lpr` | number | Daily low price. | **Parallel/inferred.** `MarketSnapshot.lowPrice`. |
| `du_nav_base_dt` | date | As-of/base date for NAV. | **Inferred, high.** Raw only. |
| `du_opr` | number | Daily opening price. | **Inferred, high.** `MarketSnapshot.openPrice`. |
| `du_upt_dt` | text date | Daily-data update date. | **Parallel.** Stored as `MarketSnapshot.sourceDate` and date fallback. |
| `du_val_1d` | number | One-day trading value/turnover. | **Parallel.** `MarketSnapshot.tradingValue1d`. |
| `du_vol_1d` | number | One-day trading volume. | **Parallel.** `MarketSnapshot.tradingVolume1d`. |

### Product, identifier, listing, and weekly fields

| Field | Type | Plain-language meaning | Status and graph treatment |
|---|---|---|---|
| `pd_abrv_nm` | text | Short product name. | **Parallel.** Fund/unit or ETN `shortName`. |
| `pd_curr_cd` | text | Product/reference currency code. | **Parallel.** Canonical `currency` fallback. |
| `pd_exg_mkt_cd` | text | Exchange/venue code such as `AMX`, `NAS`, or `NYS`. | **Parallel.** `Listing` and `Market` identity. |
| `pd_grp_no` | text | Product group: ETF or ETN. | **Parallel.** Determines canonical entity type. |
| `pd_isin_cd` | text | ISIN code. | **Inferred, high.** Preferred canonical security identity and ISIN identifier. |
| `pd_itm_no` | text | Source item/trading symbol; schema primary key. | **Inferred, high.** Source identifier and listing-ticker fallback. |
| `pd_itm_no_ma` | text | Mirae Asset item/ticker representation. | **Parallel.** Preferred `Listing.ticker`; often identical to `pd_itm_no`. |
| `pd_lipper_id` | text | Lipper fund identifier. | **Inferred, high.** Raw only; can support later external reconciliation. |
| `pd_lstg_dt` | text date | Listing/trading-start date. | **Parallel.** `Listing.listingDate`. |
| `pd_lst_price` | number | Listing/initial/face price supplied by the source. | **Parallel but exact convention ambiguous.** `Listing.listingPrice`. |
| `pd_lst_stk_cnt` | number | Number of listed shares/units. | **Parallel.** `Listing.listedShareCount`. |
| `pd_mkt_id` | text | Broad market/country identifier, `US` in this snapshot. | **Inferred, high.** Market fallback/reference. |
| `pd_nm` | text | Full product name. | **Parallel.** Fund/unit or ETN name. |
| `pd_sale_yn` | text flag | Whether available for sale through the source channel. | **Parallel.** `Offering.availableForSale`. |
| `pd_trd_ccy` | text | Currency in which the listing trades. | **Inferred, high.** Preferred `MarketSnapshot.currency`. |
| `pd_tr_yn` | text flag | Trading-suspension flag. | **Parallel.** `Offering.tradingHalted`. |
| `pd_us_cik` | text | U.S. SEC Central Index Key associated with the fund/issuer. | **Inferred, high.** Raw only; not assumed to identify the security itself. |
| `ru_mkt_price` | number | Real-time/current market price. | **Parallel.** `MarketSnapshot.realtimeMarketPrice`. |
| `ru_mkt_volume` | number | Real-time/current market volume. | **Parallel.** `MarketSnapshot.realtimeMarketVolume`. |
| `wu_core_yn` | text flag | Core-ETF designation. | **Parallel.** Raw only. |
| `wu_inv_ast_type` | text | Investment asset type/class. | **Parallel.** `investment-asset-type` classification. |
| `wu_inv_rgn` | text | Investment region. | **Parallel.** `investment-region` classification. |
| `wu_upt_dt` | text date | Weekly/reference-data update date. | **Parallel.** Raw only. |

## Public fund master: 45 fields

File: `PRFD01N001_공모펀드마스터_20260711_datarows.xlsx`

The schema provides Korean descriptions for all fields. One product can occupy
many rows because `prfd_attr_cd` is part of the source key. The loader preserves
all rows but merges them into one canonical fund/unit per valid `itm_no`.

### Benchmark, currency, geography, performance, and fund measurements

| Field | Type | Plain-language meaning | Status and graph treatment |
|---|---|---|---|
| `bmrk_eng_nm` | text | English benchmark name. | **Source.** `Benchmark.englishName`; used if Korean name is blank. |
| `bmrk_nm` | text | Benchmark name. | **Source.** Creates `Benchmark` and `TRACKS`. |
| `curr_cd` | text | Fund/unit currency code. | **Source.** `Fund.currency` and `FundUnit.currency`. |
| `exchdg_yn` | text flag | Currency-hedging status (`환헤지여부`). | **Source.** `Fund.currencyHedged`; it does **not** mean exchange traded. |
| `fd_estb_ctry_cd` | text | Country code where the fund was established. | **Source.** `Fund.countryCode`; values like `000` need a codebook. |
| `fd_ivst_rgn_desc` | text | Description of the fund's investment region. | **Source.** `investment-region` classification. |
| `fd_mm18_ern_r` | number | Eighteen-month fund return. | **Source.** `FundSnapshot.return18m`. |
| `fd_mm1_ern_r` | number | One-month fund return. | **Source.** `FundSnapshot.return1m`. |
| `fd_mm3_ern_r` | number | Three-month fund return. | **Source.** `FundSnapshot.return3m`. |
| `fd_mm6_ern_r` | number | Six-month fund return. | **Source.** `FundSnapshot.return6m`. |
| `fd_nast_suma` | number | Fund net-asset amount. | **Source.** `FundSnapshot.netAssetTotal`; currency follows `curr_cd` unless source rules say otherwise. |
| `fd_set_pcd` | text/code | Fund establishment/setup type code. | **Source.** `fund-set-product-code` classification; code meanings require a codebook. |
| `fd_wk1_ern_r` | number | One-week fund return. | **Source.** `FundSnapshot.return1w`. |
| `fd_yr1_ern_r` | number | One-year fund return. | **Source.** `FundSnapshot.return1y`. |
| `fd_yr2_ern_r` | number | Two-year fund return. | **Source.** `FundSnapshot.return2y`. |
| `fd_yr3_ern_r` | number | Three-year fund return. | **Source.** `FundSnapshot.return3y`. |
| `fd_yr5_ern_r` | number | Five-year fund return. | **Source.** `FundSnapshot.return5y`. |

### Product flags, names, and identifiers

| Field | Type | Plain-language meaning | Status and graph treatment |
|---|---|---|---|
| `frc_bpr_itm_yn` | text flag | Whether the item has a foreign-currency base price. | **Source.** Raw only. |
| `fss_itm_no` | text | Financial Supervisory Service item number. | **Source.** `FSS_ITEM` identifier unless all zeroes. |
| `hdge_fd_yn` | text flag | Whether classified as a hedge fund. | **Source.** Raw only; distinct from currency-hedging status. |
| `int_dvd_desc` | text | Description of interest-versus-distribution/dividend classification. | **Source.** Raw only. |
| `itm_abrv_nm` | text | Short item/fund-unit name. | **Source.** Fund/unit `shortName`. |
| `itm_eabrv_nm` | text | Short English item name. | **Source.** Raw only. |
| `itm_eng_nm` | text | Full English item name. | **Source.** Fund/unit `englishName`. |
| `itm_nm` | text | Full item/fund-unit name. | **Source.** Fund/unit `name`; also used by the cautious ETF-name heuristic. |
| `itm_no` | text | Source item number; part of the source primary key. | **Source.** Canonical source-specific fund/unit identity and `SOURCE_ITEM` identifier; not asserted as ISIN. |
| `kofia_fd_ccd` | text/code | Korea Financial Investment Association fund-classification code. | **Source.** `kofia-fund-class` classification. |
| `ksd_itm_no` | text | Korea Securities Depository item number. | **Source.** `KSD_ITEM` identifier unless blank/zero. |
| `mtco_itm_no` | text | Asset-management-company item number. | **Source.** `MIRAE_ITEM` source-scheme identifier unless blank/zero; the scheme name reflects current loader terminology. |
| `ofsfd_yn` | text flag | Offshore-fund flag. | **Source.** `Fund.overseasFund`. |

### Fund classifications, organizations, sales, and risk

| Field | Type | Plain-language meaning | Status and graph treatment |
|---|---|---|---|
| `or_attr_desc` | text | Description of management/operating attribute, e.g. MMF or equity type. | **Source.** `fund-type` classification. |
| `or_co_xtn_itt_cd` | text/code | External institution code for the management company. | **Source.** Creates code-only `Organization` and `MANAGED_BY`; no name is invented. |
| `ovrs_fd_desc` | text | Description of domestic/overseas fund classification. | **Source.** Raw only; overlaps conceptually with investment region/offshore flag but is kept separately. |
| `pers_corp_desc` | text | Individual-versus-corporate investor classification description. | **Source.** `investor-kind` classification. |
| `pfiv_sale_cntl_tcd` | text/code | Professional-investor sales-control type code. | **Source.** `Offering.saleControlType`; requires codebook for exact rules. |
| `prfd_attr_cd` | text/code | Repeating per-fund product-attribute code; part of source primary key. | **Source.** `product-attribute` classification. This field explains most duplicate rows. |
| `prvo_fd_desc` | text | Private-fund classification description. | **Source.** `Fund.privateFundDescription`. |
| `prvo_pbff_desc` | text | Private-versus-public offering description. | **Source.** `Fund.publicPrivateDescription`. |
| `rptt_ksd_itm_no` | text | Representative KSD item number. | **Source.** `REPRESENTATIVE_KSD_ITEM` identifier and unit property; not yet used to merge share classes. |
| `sale_yn` | text/status | Sale status, such as `판매중` or `판매완료`. | **Source.** `Offering.saleStatus` and `availableForSale`. |
| `std_itm_no` | text | Standard item number. | **Source.** `STD_ITEM` identifier; not assumed to be an ISIN without verification. |
| `thco_sale_yn` | text flag | Whether this company currently sells the product. | **Source.** `Offering.availableThroughFirm`. |
| `trusc_xtn_itt_cd` | text/code | External institution code for the trustee/custodian company. | **Source.** Raw only; no trustee relationship is promoted yet. |
| `zrin_fd_ivst_risk_gcd` | text/code | Zeroin fund-investment risk-grade code; part of source primary key. | **Source.** `risk-grade` classification code. Do not compare numerically without the scale definition. |
| `zrin_fd_ivst_risk_grd_nm` | text | Human-readable Zeroin investment risk-grade name. | **Source.** `risk-grade` classification name. |

## Fields that most need authoritative documentation

The current interpretations are sufficient for search, lineage, and exploratory
GraphRAG, but the following should be confirmed before valuation, tax reporting,
compliance, or suitability decisions:

- exact bond yield formulas and tax assumptions;
- whether `DUR` is modified, effective, Macaulay, or another duration;
- convexity scaling;
- distinction between `PD_EVCO_CRD_GRD` and `CRD_GRD`, plus rating agencies;
- the conflicting Korean description for domestic `du_lpr`;
- exact definition of `du_diff_rt` and whether the graph property should be
  renamed from `priceChangeRate` to `premiumDiscountRate`;
- whole-fund versus per-unit convention for `du_last_nav`;
- distinction among listed, circulating, outstanding, and total share counts;
- public-fund code lists (`fd_set_pcd`, `prfd_attr_cd`, risk codes, KOFIA codes,
  and sales-control codes);
- whether `rptt_ksd_itm_no` safely identifies a parent fund/share-class family;
  and
- crosswalks for organization codes, fund families, identifiers, currencies, and
  markets.

Until those definitions are obtained, the graph's `SourceRecord` layer remains
the authoritative representation of what the workbooks actually asserted.
