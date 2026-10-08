# Reference alignment - UK (all)

References: baseline = EU canonical 1.0.0; acord = SAMPLE (not ACORD) 0.1

Overall alignment **96%** - entities 6 (full 6, partial 0, none 0), attributes matched 20/20, ambiguous 0

## Domains

| Domain | Entities | Full | Partial | None | Alignment | Endpoint alignment |
|---|---|---|---|---|---|---|
| Quote | 6 | 6 | 0 | 0 | 96% | 92% |

## Entities

| Entity | Apps | Best match | Alignment | Status | Recommendation | Proposed canonical |
|---|---|---|---|---|---|---|
| Address | UK/quote | Address (baseline) | 100% | full | Reuse baseline canonical | Address |
| Customer | UK/quote | Party (baseline) | 100% | full | Reuse baseline canonical | Party |
| Money | UK/quote | MonetaryAmount (baseline) | 100% | full | Reuse baseline canonical | MonetaryAmount |
| PolicyRef | UK/quote | Policy (baseline) | 99% | full | Reuse baseline canonical | Policy |
| Quote | UK/quote | Quote (acord) | 87% | full | Use reference as-is | Quote |
| QuoteRequest | UK/quote | Quote (acord) | 93% | full | Use reference as-is | Quote |

## Endpoints

| Method | Path | Entities | Alignment | Proposed canonical path |
|---|---|---|---|---|
| POST | `/quotes` | Quote, QuoteRequest | 90% | `/quotes` |
| GET | `/quotes/{quoteRef}` | Quote | 87% | `/quotes/{quoteRef}` |
| POST | `/quotes/{quoteRef}/bind` | PolicyRef | 99% | `/quotes/{quoteRef}/bind` |
