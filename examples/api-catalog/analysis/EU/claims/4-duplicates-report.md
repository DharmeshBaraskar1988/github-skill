# Duplicate entities - claims (EU)

## Group 1: ClaimDto / ClaimResponse

- Match: **exact** (similarity 1.0)
- Decision: **merge** -> canonical `Claim`

| Schema | Role | Project | Source | Used by |
|---|---|---|---|---|
| ClaimDto | response | Claims.Domain | src/Claims.Domain/Models/Claim.cs:31 | GET /api/v1/claims<br>PUT /api/v1/claims/{claimId} |
| ClaimResponse | response | Claims.Domain | src/Claims.Domain/Models/Claim.cs:44 | GET /api/v1/claims/{claimId}<br>POST /api/v1/claims |

## Group 2: ClaimantDto / PolicyHolderInfo

- Match: **near** (similarity 1.0)
- Decision: **keep-separate**
- Note: PolicyHolderInfo is the FNOL reporter (may not be a claimant); ClaimantDto has ClaimantId/PolicyHolderId identity
- Only in ClaimantDto: claimantid, policyholderid

| Schema | Role | Project | Source | Used by |
|---|---|---|---|---|
| ClaimantDto | shared | Claims.Domain | src/Claims.Domain/Models/Claim.cs:79 | GET /api/v1/claims/{claimId}/claimants<br>POST /api/v1/claims |
| PolicyHolderInfo | request | Claims.Functions | src/Claims.Functions/FnolFunctions.cs:56 | POST /fn/fnol |

## Schema -> canonical entity mapping

| Schema | Canonical entity |
|---|---|
| ClaimDto | Claim |
| ClaimResponse | Claim |
