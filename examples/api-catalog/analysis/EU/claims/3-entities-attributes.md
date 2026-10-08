# Entities and attributes - claims (EU)

## Address

- Kind: object  |  Domain: Claims  |  Roles: shared
- Schemas: Address
- Source: src/Claims.Domain/Models/Claim.cs:12
- Description: Postal address.

| Attribute | Type | Required | Description |
|---|---|---|---|
| line1 | string |  |  |
| line2 | string |  |  |
| city | string |  |  |
| postCode | string |  |  |
| country | string |  | ISO 3166 alpha-2 country code. |

Used by: `POST /api/v1/claims`, `GET /api/v1/claims/{claimId}/claimants`, `POST /fn/fnol`, `PUT /api/v1/claims/{claimId}`

## ApprovalRequest

- Kind: object  |  Domain: Claims  |  Roles: request
- Schemas: ApprovalRequest
- Source: src/Claims.Domain/Models/Claim.cs:76
- Description: Approval of a claim with the agreed settlement amount.

| Attribute | Type | Required | Description |
|---|---|---|---|
| approvedBy | string | yes |  |
| settlementAmount | Money | yes |  |
| comment | string |  |  |

Used by: `POST /api/v1/claims/{claimId}/approve`

## Claim

- Kind: object  |  Domain: Claims  |  Roles: response
- Schemas: ClaimDto, ClaimResponse
- Source: src/Claims.Domain/Models/Claim.cs:31, src/Claims.Domain/Models/Claim.cs:44
- Description: Claim summary used in lists.

| Attribute | Type | Required | Description |
|---|---|---|---|
| createdAt | string(date-time) |  |  |
| createdBy | string |  |  |
| claimId | string(uuid) |  |  |
| claimNumber | string | yes | Business claim number, e.g. CLM-2026-000123. |
| policyNumber | string |  |  |
| status | ClaimStatus |  |  |
| reserveAmount | Money |  |  |
| lossDate | string(date) |  |  |

Used by: `POST /api/v1/claims`, `GET /api/v1/claims/{claimId}`, `GET /api/v1/claims`, `PUT /api/v1/claims/{claimId}`

## ClaimDocument

- Kind: object  |  Domain: Document Management  |  Roles: response
- Schemas: ClaimDocument
- Source: src/Claims.Domain/Models/Claim.cs:90
- Description: Document (photo, invoice, report) attached to a claim.

| Attribute | Type | Required | Description |
|---|---|---|---|
| documentId | string(uuid) |  |  |
| claimId | string(uuid) |  |  |
| fileName | string |  |  |
| documentType | string |  |  |
| sizeBytes | integer(int64) |  |  |

Used by: `GET /api/v1/claims/{claimId}/documents`, `POST /api/v1/claims/{claimId}/documents`

## ClaimStatus

- Kind: enum  |  Domain: Claims  |  Roles: enum
- Schemas: ClaimStatus
- Source: src/Claims.Domain/Models/Claim.cs:6
- Description: Lifecycle status of an insurance claim.
- Values: Draft, Submitted, UnderReview, Approved, Rejected, Closed

## Claimant

- Kind: object  |  Domain: Claims  |  Roles: shared
- Schemas: ClaimantDto
- Source: src/Claims.Domain/Models/Claim.cs:79
- Description: Person or organisation claiming under the policy.

| Attribute | Type | Required | Description |
|---|---|---|---|
| claimantId | string(uuid) |  |  |
| firstName | string |  |  |
| lastName | string |  |  |
| email | string(email) |  |  |
| address | Address |  |  |
| policyHolderId | string |  |  |

Used by: `POST /api/v1/claims`, `GET /api/v1/claims/{claimId}/claimants`

## CreateClaimRequest

- Kind: object  |  Domain: Claims  |  Roles: request
- Schemas: CreateClaimRequest
- Source: src/Claims.Domain/Models/Claim.cs:55
- Description: Data needed to register a new claim.

| Attribute | Type | Required | Description |
|---|---|---|---|
| policyNumber | string | yes |  |
| lossDate | string(date) | yes |  |
| description | string |  |  |
| lossLocation | Address |  |  |
| claimants | list of Claimant |  |  |

Used by: `POST /api/v1/claims`

## FnolReceipt

- Kind: object  |  Domain: Claims  |  Roles: response
- Schemas: FnolReceipt
- Source: src/Claims.Functions/FnolFunctions.cs:49
- Description: Acknowledgement returned when a FNOL is accepted.

| Attribute | Type | Required | Description |
|---|---|---|---|
| reference | string |  |  |
| receivedAt | string(date-time) |  |  |

Used by: `GET /fn/fnol/{reference}`, `POST /fn/fnol`

## FnolSubmission

- Kind: object  |  Domain: Claims  |  Roles: request
- Schemas: FnolSubmission
- Source: src/Claims.Functions/FnolFunctions.cs:39
- Description: FNOL payload sent by brokers.

| Attribute | Type | Required | Description |
|---|---|---|---|
| brokerCode | string |  |  |
| policyNumber | string |  |  |
| lossDateTime | string(date-time) |  |  |
| description | string |  |  |
| location | Address |  |  |
| reporter | PolicyHolderInfo |  |  |

Used by: `POST /fn/fnol`

## Money

- Kind: object  |  Domain: Claims  |  Roles: shared
- Schemas: Money
- Source: src/Claims.Domain/Models/Claim.cs:9
- Description: Monetary amount with ISO currency.

| Attribute | Type | Required | Description |
|---|---|---|---|
| amount | number(double) | yes |  |
| currency | string | yes |  |

Used by: `POST /api/v1/claims/{claimId}/approve`, `POST /api/v1/claims`, `GET /api/v1/claims/{claimId}`, `GET /api/v1/claims`, `PUT /api/v1/claims/{claimId}`

## PolicyHolderInfo

- Kind: object  |  Domain: Claims  |  Roles: request
- Schemas: PolicyHolderInfo
- Source: src/Claims.Functions/FnolFunctions.cs:56
- Description: Reporter of the loss.

| Attribute | Type | Required | Description |
|---|---|---|---|
| firstName | string |  |  |
| lastName | string |  |  |
| email | string |  |  |
| address | Address |  |  |

Used by: `POST /fn/fnol`

## UpdateClaimRequest

- Kind: object  |  Domain: Claims  |  Roles: request
- Schemas: UpdateClaimRequest
- Source: src/Claims.Domain/Models/Claim.cs:69
- Description: Changes to an existing claim.

| Attribute | Type | Required | Description |
|---|---|---|---|
| description | string |  |  |
| lossLocation | Address |  |  |
| status | ClaimStatus |  |  |

Used by: `PUT /api/v1/claims/{claimId}`

## Relations

| From | Relation | To | Via | Cardinality |
|---|---|---|---|---|
| ApprovalRequest | has-one | Money | settlementAmount | 1 |
| ClaimDocument | references | Claim | claimId | 0..1 |
| Claim | uses-enum | ClaimStatus | status | 0..1 |
| Claim | has-one | Money | reserveAmount | 0..1 |
| Claimant | has-one | Address | address | 0..1 |
| Claimant | references | PolicyHolderInfo | policyHolderId | 0..1 |
| CreateClaimRequest | has-one | Address | lossLocation | 0..1 |
| CreateClaimRequest | has-many | Claimant | claimants | 0..* |
| FnolSubmission | has-one | Address | location | 0..1 |
| FnolSubmission | has-one | PolicyHolderInfo | reporter | 0..1 |
| PolicyHolderInfo | has-one | Address | address | 0..1 |
| UpdateClaimRequest | has-one | Address | lossLocation | 0..1 |
| UpdateClaimRequest | uses-enum | ClaimStatus | status | 0..1 |
