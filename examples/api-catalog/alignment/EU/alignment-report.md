# Reference alignment - EU (all)

References: acord = SAMPLE (not ACORD) 0.1

Overall alignment **75%** - entities 17 (full 7, partial 8, none 2), attributes matched 56/69, ambiguous 0

## Domains

| Domain | Entities | Full | Partial | None | Alignment | Endpoint alignment |
|---|---|---|---|---|---|---|
| Claims | 11 | 5 | 4 | 2 | 71% | 57% |
| Document Management | 1 | 0 | 1 | 0 | 80% | 80% |
| Policy | 5 | 2 | 3 | 0 | 81% | 88% |

## Entities

| Entity | Apps | Best match | Alignment | Status | Recommendation | Proposed canonical |
|---|---|---|---|---|---|---|
| Address | EU/claims, EU/policy | Address (acord) | 100% | full | Use reference as-is | Address |
| ApprovalRequest | EU/claims | - | 16% | none | Custom canonical entity | ApprovalRequest |
| Claim | EU/claims | Claim (acord) | 82% | partial | Extend reference | Claim |
| ClaimStatus | EU/claims | ClaimStatusCode (acord) | 68% | partial | Extend reference | ClaimStatusCode |
| Claimant | EU/claims | ClaimParty (acord) | 88% | partial | Extend reference | ClaimParty |
| CreateClaimRequest | EU/claims | Claim (acord) | 90% | full | Use reference as-is | Claim |
| FnolReceipt | EU/claims | - | 0% | none | Custom canonical entity | FnolReceipt |
| FnolSubmission | EU/claims | Claim (acord) | 46% | partial | Extend reference | Claim |
| Money | EU/claims, EU/policy | MonetaryAmount (acord) | 100% | full | Use reference as-is | MonetaryAmount |
| PolicyHolder | EU/claims, EU/policy | Party (acord) | 100% | full | Use reference as-is | Party |
| UpdateClaimRequest | EU/claims | Claim (acord) | 94% | full | Use reference as-is | Claim |
| ClaimDocument | EU/claims | Document (acord) | 80% | partial | Extend reference | Document |
| Coverage | EU/policy | Coverage (acord) | 90% | full | Use reference as-is | Coverage |
| IssuePolicyRequest | EU/policy | Policy (acord) | 71% | partial | Extend reference | Policy |
| PolicyDetails | EU/policy | Policy (acord) | 91% | full | Use reference as-is | Policy |
| PolicyStatus | EU/policy | PolicyStatusCode (acord) | 76% | partial | Extend reference | PolicyStatusCode |
| PolicySummary | EU/policy | Policy (acord) | 76% | partial | Extend reference | Policy |

## Endpoints

| Method | Path | Entities | Alignment | Proposed canonical path |
|---|---|---|---|---|
| GET | `/api/v1/claims` | Claim, ClaimStatus | 75% | `/claims` |
| POST | `/api/v1/claims` | Claim, CreateClaimRequest | 86% | `/claims` |
| GET | `/api/v1/claims/{claimId}` | Claim | 82% | `/claims/{claimId}` |
| PUT | `/api/v1/claims/{claimId}` | Claim, UpdateClaimRequest | 88% | `/claims/{claimId}` |
| DELETE | `/api/v1/claims/{claimId}` |  | - | `/claims/{claimId}` |
| POST | `/api/v1/claims/{claimId}/approve` | ApprovalRequest | 16% | `/claims/{claimId}/approve` |
| GET | `/api/v1/claims/{claimId}/claimants` | Claimant | 88% | `/claims/{claimId}/claim-parties` |
| GET | `/api/v1/claims/{claimId}/documents` | ClaimDocument | 80% | `/claims/{claimId}/documents` |
| POST | `/api/v1/claims/{claimId}/documents` | ClaimDocument | 80% | `/claims/{claimId}/documents` |
| DELETE | `/api/v1/claims/{claimId}/documents/{documentId}` |  | - | `/claims/{claimId}/documents/{documentId}` |
| POST | `/fn/fnol` | FnolReceipt, FnolSubmission | 23% | `/fnol` |
| GET | `/fn/fnol/{reference}` | FnolReceipt | 0% | `/fnol/{reference}` |
| GET | `/api/policies` | PolicySummary | 76% | `/policies` |
| POST | `/api/policies` | IssuePolicyRequest, PolicyDetails | 81% | `/policies` |
| GET | `/api/policies/{policyNumber}` | PolicyDetails | 91% | `/policies/{policyNumber}` |
| POST | `/api/policies/{policyNumber}/renew` | PolicyDetails | 91% | `/policies/{policyNumber}/renew` |
| GET | `/api/policyholders/{id}` | PolicyHolder | 100% | `/parties/{id}` |
