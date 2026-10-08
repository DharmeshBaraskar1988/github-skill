# EU Canonical Insurance API - canonical model v1.0.0 (approved)

Region EU. References: acord SAMPLE (not ACORD) 0.1
Reviewers: Asha (Claims architect), Marco (Policy architect)

11 entities (0 from baseline, 11 new), 52 attributes (7 extensions), 15 endpoints, 14 relations.

## Entities

### Address ← acord:Address

Postal address.

Approach: reference-as-is · status: approved · domain: Claims · sources: EU/claims:Address, EU/policy:Address

| Attribute | Type | Required | Reference | Extension | Description |
|---|---|---|---|---|---|
| addressLine1 | string | yes | Address.addressLine1 |  | First address line. |
| addressLine2 | string |  | Address.addressLine2 |  | Second address line. |
| city | string | yes | Address.city |  | City or town. |
| postalCode | string |  | Address.postalCode |  | Postal / ZIP code. |
| countryCode | string | yes | Address.countryCode |  | ISO 3166 country code. |

### Claim ← acord:Claim

A demand for payment under a policy following a loss.

Approach: reference-extended · status: approved · domain: Claims · sources: EU/claims:ClaimDto, EU/claims:ClaimResponse, EU/claims:CreateClaimRequest, EU/claims:FnolSubmission, EU/claims:UpdateClaimRequest

| Attribute | Type | Required | Reference | Extension | Description |
|---|---|---|---|---|---|
| creationTimestamp | string(date-time) |  |  | yes |  |
| claimIdentifier | string(uuid) | yes | Claim.claimIdentifier |  | Unique claim id. |
| claimNumber | string | yes | Claim.claimNumber |  | Business claim number. |
| policyNumber | string | yes | Claim.policyNumber |  | Number of the policy claimed against. |
| claimStatusCode | ClaimStatusCode |  | Claim.claimStatusCode |  | Lifecycle status. |
| reserveAmount | MonetaryAmount |  | Claim.reserveAmount |  | Current reserve. |
| lossDate | string(date) | yes | Claim.lossDate |  | Date of loss. |
| lossDescription | string |  | Claim.lossDescription |  | Narrative of the loss. |
| lossLocation | Address |  | Claim.lossLocation |  | Where the loss happened. |
| claimParties | list of ClaimParty |  | Claim.claimParties |  | Parties involved. |
| brokerCode | string |  |  | yes |  |
| reporter | Party |  |  | yes |  |

### ClaimApproval

Approval of a claim with the agreed settlement amount.

Approach: custom · status: approved · domain: Claims · sources: EU/claims:ApprovalRequest

| Attribute | Type | Required | Reference | Extension | Description |
|---|---|---|---|---|---|
| approvedBy | string | yes |  |  |  |
| settlementAmount | MonetaryAmount | yes |  |  |  |
| comment | string |  |  |  |  |

### ClaimParty ← acord:ClaimParty

A party involved in a claim (claimant, witness, ...).

Approach: reference-extended · status: approved · domain: Claims · sources: EU/claims:ClaimantDto

| Attribute | Type | Required | Reference | Extension | Description |
|---|---|---|---|---|---|
| claimPartyIdentifier | string | yes | ClaimParty.claimPartyIdentifier |  | Unique id of the claim party. |
| givenName | string |  | ClaimParty.givenName |  | First name. |
| surname | string |  | ClaimParty.surname |  | Family name. |
| emailAddress | string |  | ClaimParty.emailAddress |  | E-mail address. |
| address | Address |  | ClaimParty.address |  | Postal address. |
| policyHolderId | string |  |  | yes |  |

### ClaimStatusCode ← acord:ClaimStatusCode

Claim lifecycle status.

Approach: reference-extended · status: approved · domain: Claims · sources: EU/claims:ClaimStatus

Values: Open, Submitted, UnderReview, Approved, Denied, Closed, Reopened, Draft, Rejected

### Coverage ← acord:Coverage

A coverage provided by a policy.

Approach: reference-as-is · status: approved · domain: Policy · sources: EU/policy:Coverage

| Attribute | Type | Required | Reference | Extension | Description |
|---|---|---|---|---|---|
| coverageCode | string | yes | Coverage.coverageCode |  | Coverage code. |
| coverageName | string |  | Coverage.coverageName |  | Coverage name. |
| limitAmount | MonetaryAmount |  | Coverage.limitAmount |  | Limit. |
| deductibleAmount | MonetaryAmount |  | Coverage.deductibleAmount |  | Deductible. |

### Document ← acord:Document

A document attached to a business object.

Approach: reference-extended · status: approved · domain: Document Management · sources: EU/claims:ClaimDocument

| Attribute | Type | Required | Reference | Extension | Description |
|---|---|---|---|---|---|
| documentIdentifier | string(uuid) | yes | Document.documentIdentifier |  | Unique document id. |
| claimId | string(uuid) |  |  | yes |  |
| fileName | string | yes | Document.fileName |  | Original file name. |
| documentTypeCode | string |  | Document.documentTypeCode |  | Kind of document. |
| fileSize | integer(int64) |  | Document.fileSize |  | Size in bytes. |

### MonetaryAmount ← acord:MonetaryAmount

An amount of money in a currency.

Approach: reference-as-is · status: approved · domain: Claims · sources: EU/claims:Money, EU/policy:Money

| Attribute | Type | Required | Reference | Extension | Description |
|---|---|---|---|---|---|
| amount | number(double) | yes | MonetaryAmount.amount |  | Numeric value. |
| currencyCode | string | yes | MonetaryAmount.currencyCode |  | ISO 4217 currency code. |

### Party ← acord:Party

A person or organisation with a role in insurance.

Approach: reference-as-is · status: approved · domain: Claims · sources: EU/claims:PolicyHolderInfo, EU/policy:PolicyHolder

| Attribute | Type | Required | Reference | Extension | Description |
|---|---|---|---|---|---|
| givenName | string |  | Party.givenName |  | First name. |
| surname | string |  | Party.surname |  | Family name. |
| emailAddress | string |  | Party.emailAddress |  | E-mail address. |
| address | Address |  | Party.address |  | Main postal address. |
| partyIdentifier | string | yes | Party.partyIdentifier |  | Unique party id. |

### Policy ← acord:Policy

An insurance contract.

Approach: reference-extended · status: approved · domain: Policy · sources: EU/policy:IssuePolicyRequest, EU/policy:PolicyDetails, EU/policy:PolicySummary

| Attribute | Type | Required | Reference | Extension | Description |
|---|---|---|---|---|---|
| quoteReference | string |  |  | yes |  |
| effectiveDate | string(date) | yes | Policy.effectiveDate |  | Start of cover. |
| policyHolder | Party |  | Policy.policyHolder |  | Policy holder. |
| policyNumber | string | yes | Policy.policyNumber |  | Policy number. |
| productCode | string | yes | Policy.productCode |  | Product code. |
| policyStatusCode | PolicyStatusCode |  | Policy.policyStatusCode |  | Status. |
| expirationDate | string(date) | yes | Policy.expirationDate |  | End of cover. |
| premiumAmount | MonetaryAmount |  | Policy.premiumAmount |  | Total premium. |
| coverages | list of Coverage |  | Policy.coverages |  | Coverages. |
| holderName | string | yes |  | yes |  |

### PolicyStatusCode ← acord:PolicyStatusCode

Policy status.

Approach: reference-extended · status: approved · domain: Policy · sources: EU/policy:PolicyStatus

Values: Quoted, InForce, Lapsed, Cancelled, Expired, Active

## Endpoints

| Method | Path | operationId | Sources |
|---|---|---|---|
| GET | `/claims` | SearchClaims | EU/claims:listClaims |
| POST | `/claims` | RegisterClaim | EU/claims:createClaim |
| DELETE | `/claims/{claimId}` | CloseClaim | EU/claims:deleteClaim |
| GET | `/claims/{claimId}` | ViewClaim | EU/claims:getClaim |
| PUT | `/claims/{claimId}` | UpdateClaim | EU/claims:updateClaim |
| POST | `/claims/{claimId}/approve` | ApproveClaim | EU/claims:approveClaim |
| GET | `/claims/{claimId}/claim-parties` | ManageClaimants | EU/claims:getClaimsClaimants |
| GET | `/claims/{claimId}/documents` | ListDocuments | EU/claims:listDocuments |
| POST | `/claims/{claimId}/documents` | UploadDocument | EU/claims:uploadDocuments |
| DELETE | `/claims/{claimId}/documents/{documentId}` | DeleteDocument | EU/claims:deleteDocuments |
| GET | `/parties/{id}` | GetPolicyholder | EU/policy:getPolicyholdersById |
| GET | `/policies` | SearchPolicies | EU/policy:getPolicies |
| POST | `/policies` | IssuePolicy | EU/policy:postPolicies |
| GET | `/policies/{policyNumber}` | ViewPolicy | EU/policy:getPoliciesById |
| POST | `/policies/{policyNumber}/renew` | RenewPolicy | EU/policy:postPoliciesRenew |
