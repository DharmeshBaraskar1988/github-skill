# Discovery report - policy (EU)

Status: **PASS** (iteration 0)

## Projects

| Project | Kind | Target framework | Path |
|---|---|---|---|
| Policy.Api | web | net8.0 | src/Policy.Api |

## Counts

- projects: 1
- inventoryEndpoints: 5
- specOperations: 5
- excludedEndpoints: 0
- schemas: 9
- nonHttpFunctions: 0

## Endpoints

| Method | Path | operationId | Style | Source |
|---|---|---|---|---|
| GET | `/api/policies` | getPolicies | minimal-api | src/Policy.Api/Program.cs:3 |
| POST | `/api/policies` | postPolicies | minimal-api | src/Policy.Api/Program.cs:5 |
| GET | `/api/policies/{policyNumber}` | getPoliciesById | minimal-api | src/Policy.Api/Program.cs:4 |
| POST | `/api/policies/{policyNumber}/renew` | postPoliciesRenew | minimal-api | src/Policy.Api/Program.cs:6 |
| GET | `/api/policyholders/{id}` | getPolicyholdersById | minimal-api | src/Policy.Api/Program.cs:7 |

## Warnings

- D07 POST /api/policies/{policyNumber}/renew: POST without request body
- D11 Descriptions missing: 5 operations, 5 schemas, 36 properties
- D12 info fields used by all style examples are missing: ['contact', 'x-audience']
- D12 5 operations lack header parameters ['X-Correlation-ID'] that the style examples always declare
- D12 Style examples give every operation a summary; 5 here have none: ['getPolicies', 'postPolicies', 'getPoliciesById', 'postPoliciesRenew', 'getPolicyholdersById']
