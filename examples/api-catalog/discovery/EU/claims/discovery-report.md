# Discovery report - claims (EU)

Status: **PASS** (iteration 0)

## Projects

| Project | Kind | Target framework | Path |
|---|---|---|---|
| Claims.Domain | library | net8.0 | src/Claims.Domain |
| Claims.Api | web | net8.0 | src/Claims.Api |
| Claims.Functions | functions-isolated | net8.0 | src/Claims.Functions |

## Counts

- projects: 3
- inventoryEndpoints: 13
- specOperations: 12
- excludedEndpoints: 1
- schemas: 16
- nonHttpFunctions: 1

## Endpoints

| Method | Path | operationId | Style | Source |
|---|---|---|---|---|
| GET | `/api/v1/claims` | listClaims | minimal-api | src/Claims.Api/Endpoints/ClaimEndpoints.cs:11 |
| POST | `/api/v1/claims` | createClaim | minimal-api | src/Claims.Api/Endpoints/ClaimEndpoints.cs:13 |
| GET | `/api/v1/claims/{claimId}` | getClaim | minimal-api | src/Claims.Api/Endpoints/ClaimEndpoints.cs:12 |
| PUT | `/api/v1/claims/{claimId}` | updateClaim | minimal-api | src/Claims.Api/Endpoints/ClaimEndpoints.cs:17 |
| DELETE | `/api/v1/claims/{claimId}` | deleteClaim | minimal-api | src/Claims.Api/Endpoints/ClaimEndpoints.cs:23 |
| POST | `/api/v1/claims/{claimId}/approve` | approveClaim | minimal-api | src/Claims.Api/Endpoints/ClaimEndpoints.cs:22 |
| GET | `/api/v1/claims/{claimId}/claimants` | getClaimsClaimants | minimal-api | src/Claims.Api/Endpoints/ClaimEndpoints.cs:26 |
| GET | `/api/v1/claims/{claimId}/documents` | listDocuments | controller | src/Claims.Api/Controllers/DocumentsController.cs:12 |
| POST | `/api/v1/claims/{claimId}/documents` | uploadDocuments | controller | src/Claims.Api/Controllers/DocumentsController.cs:18 |
| DELETE | `/api/v1/claims/{claimId}/documents/{documentId}` | deleteDocuments | controller | src/Claims.Api/Controllers/DocumentsController.cs:21 |
| POST | `/fn/fnol` | submitFnol | azure-function | src/Claims.Functions/FnolFunctions.cs:11 |
| GET | `/fn/fnol/{reference}` | getFnolStatus | azure-function | src/Claims.Functions/FnolFunctions.cs:24 |

## Non-HTTP functions (not in paths)

| Function | Trigger | Source |
|---|---|---|
| ProcessFnolQueue | ServiceBusTrigger | src/Claims.Functions/FnolFunctions.cs:34 |

## Warnings

- D11 Descriptions missing: 5 operations, 6 schemas, 70 properties
- D12 info fields used by all style examples are missing: ['contact', 'x-audience']
- D12 12 operations lack header parameters ['X-Correlation-ID'] that the style examples always declare
- D12 Style examples give every operation a summary; 5 here have none: ['updateClaim', 'deleteClaim', 'approveClaim', 'getClaimsClaimants', 'deleteDocuments']
