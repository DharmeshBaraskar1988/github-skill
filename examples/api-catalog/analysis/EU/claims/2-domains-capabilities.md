# Domains and capabilities - claims (EU)

## Claims

Claims handling from first notice of loss to settlement

| Capability | Status | Operations |
|---|---|---|
| Search Claims | catalogue | `GET /api/v1/claims` (listClaims, high) |
| Register Claim | catalogue | `POST /api/v1/claims` (createClaim, high)<br>`POST /fn/fnol` (submitFnol, high)<br>`GET /fn/fnol/{reference}` (getFnolStatus, confirmed) |
| View Claim | catalogue | `GET /api/v1/claims/{claimId}` (getClaim, high) |
| Update Claim | catalogue | `PUT /api/v1/claims/{claimId}` (updateClaim, high) |
| Close Claim | catalogue | `DELETE /api/v1/claims/{claimId}` (deleteClaim, high) |
| Approve Claim | catalogue | `POST /api/v1/claims/{claimId}/approve` (approveClaim, high) |
| Manage Claimants | catalogue | `GET /api/v1/claims/{claimId}/claimants` (getClaimsClaimants, confirmed) |

Entities: Address, ApprovalRequest, Claim, ClaimStatus, Claimant, CreateClaimRequest, FnolReceipt, FnolSubmission, Money, PolicyHolderInfo, UpdateClaimRequest

## Document Management

Documents attached to business objects

| Capability | Status | Operations |
|---|---|---|
| List Documents | catalogue | `GET /api/v1/claims/{claimId}/documents` (listDocuments, high) |
| Upload Document | catalogue | `POST /api/v1/claims/{claimId}/documents` (uploadDocuments, high) |
| Delete Document | catalogue | `DELETE /api/v1/claims/{claimId}/documents/{documentId}` (deleteDocuments, high) |

Entities: ClaimDocument
