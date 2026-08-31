# Historical sample-question regression checklist

This is the preserved regression view for the historical four supplied
`20260711` XLSX workbooks. These outcomes remain golden/regression expectations
for the old loaded baseline; they do not override the current plan or claim
refreshed organizer data is loaded. Detailed evidence, field populations, and
status definitions are in
[`historical-data-capabilities-2026-07-11.md`](historical-data-capabilities-2026-07-11.md).
Planned external evidence is in
[`../external/external-data-plan.md`](../external/external-data-plan.md).

| # | Question | Current status | Missing evidence or rule |
|---:|---|---|---|
| 1 | 현재 판매 가능한 원화채권 중 AA- 이상 종목 알려줘 | Partial | Authoritative rating scale/agency ordering for “AA- 이상” |
| 2 | 국민성장펀드의 구조와 투자전략 동향 등 찾아서 알려줘 | Partial | Verified fund-family/share-class structure, detailed strategy documents, repeated history |
| 3 | 캠브리콘이 편입된 중국 반도체 ETF를 알려줘 | Unsupported | Dated ETF holdings/benchmark constituents and Cambricon security-company identity |
| 4 | 최근 6개월 동안 우주항공 테마와 연결 이력이 있는 관련 ETF를 정리해줘 | Unsupported as written | Six months of snapshots plus sourced, time-bounded theme associations |
| 5 | 에코프로의 자회사를 편입한 ETF 중 순자산이 큰 상품의 위험요인 알려줘 | Unsupported as written | Corporate-control hierarchy, holdings, comparable AUM, prospectus risk passages |
| 6 | 신용등급 AAAA인 채권 찾아줘 | Empty in snapshot; validity unresolved | Rating vocabulary needed to label the value invalid rather than merely unmatched |
| 7 | Kimi 관련 투자 상품 있어? | Empty in current text fields | External evidence would be needed to make a claim beyond this snapshot |
| 8 | KODEX AI로봇 ETF 정보 알려줘 | Empty exact entity | Similar names must not be silently substituted for the requested product |
| 9 | 국내 배당형 ETF 중 분기배당이고 운용보수 0.1% 이하인 상품을 추천해줘 | Unsupported | Dividend-cycle field is entirely blank; fee is sparse; recommendation policy undefined |
| 10 | 국내 배당형 ETF 중 분기배당이고 운용보수가 낮은 상품 추천해줘 | Unsupported | Same data gaps; “low” and recommendation objective undefined |
| 11 | TIGER 2차전지테마의 보수율과 추적오차 위험을 같이 알려줘 | Unsupported for requested metrics | Target fee is blank; tracking field is `0.00` and no tracking-risk narrative is loaded |

For unsupported or partial cases, return the supported snapshot facts and name
the missing evidence. For empty cases, say “no exact match in the supplied
2026-07-11 snapshot”; do not turn that into a global nonexistence claim.
