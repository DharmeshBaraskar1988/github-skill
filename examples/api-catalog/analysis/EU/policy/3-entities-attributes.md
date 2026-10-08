# Entities and attributes - policy (EU)

## Address

- Kind: object  |  Domain: Policy  |  Roles: shared
- Schemas: Address
- Source: src/Policy.Api/Program.cs:34

| Attribute | Type | Required | Description |
|---|---|---|---|
| line1 | string |  |  |
| line2 | string |  |  |
| city | string |  |  |
| postCode | string |  |  |
| country | string |  |  |

Used by: `GET /api/policies/{policyNumber}`, `GET /api/policyholders/{id}`, `POST /api/policies`, `POST /api/policies/{policyNumber}/renew`

## Coverage

- Kind: object  |  Domain: Policy  |  Roles: response
- Schemas: Coverage
- Source: src/Policy.Api/Program.cs:24

| Attribute | Type | Required | Description |
|---|---|---|---|
| code | string |  |  |
| name | string |  |  |
| limit | Money |  |  |
| deductible | Money |  |  |

Used by: `GET /api/policies/{policyNumber}`, `POST /api/policies`, `POST /api/policies/{policyNumber}/renew`

## IssuePolicyRequest

- Kind: object  |  Domain: Policy  |  Roles: request
- Schemas: IssuePolicyRequest
- Source: src/Policy.Api/Program.cs:37

| Attribute | Type | Required | Description |
|---|---|---|---|
| quoteReference | string |  |  |
| inceptionDate | string(date) |  |  |
| holder | PolicyHolder |  |  |

Used by: `POST /api/policies`

## Money

- Kind: object  |  Domain: Policy  |  Roles: response
- Schemas: Money
- Source: src/Policy.Api/Program.cs:35

| Attribute | Type | Required | Description |
|---|---|---|---|
| amount | number(double) | yes |  |
| currency | string | yes |  |

Used by: `GET /api/policies/{policyNumber}`, `POST /api/policies`, `POST /api/policies/{policyNumber}/renew`

## PolicyDetails

- Kind: object  |  Domain: Policy  |  Roles: response
- Schemas: PolicyDetails
- Source: src/Policy.Api/Program.cs:13
- Description: Full policy.

| Attribute | Type | Required | Description |
|---|---|---|---|
| policyNumber | string |  |  |
| productCode | string |  |  |
| status | PolicyStatus |  |  |
| inceptionDate | string(date) |  |  |
| expiryDate | string(date) |  |  |
| premium | Money |  |  |
| holder | PolicyHolder |  |  |
| coverages | list of Coverage |  |  |

Used by: `GET /api/policies/{policyNumber}`, `POST /api/policies`, `POST /api/policies/{policyNumber}/renew`

## PolicyHolder

- Kind: object  |  Domain: Policy  |  Roles: shared
- Schemas: PolicyHolder
- Source: src/Policy.Api/Program.cs:26
- Description: Insured person or company.

| Attribute | Type | Required | Description |
|---|---|---|---|
| policyHolderId | string(uuid) |  |  |
| firstName | string |  |  |
| lastName | string |  |  |
| email | string |  |  |
| address | Address |  |  |

Used by: `GET /api/policies/{policyNumber}`, `GET /api/policyholders/{id}`, `POST /api/policies`, `POST /api/policies/{policyNumber}/renew`

## PolicyStatus

- Kind: enum  |  Domain: Policy  |  Roles: enum
- Schemas: PolicyStatus
- Source: src/Policy.Api/Program.cs:36
- Values: Quoted, Active, Lapsed, Cancelled, Expired

## PolicySummary

- Kind: object  |  Domain: Policy  |  Roles: response
- Schemas: PolicySummary
- Source: src/Policy.Api/Program.cs:11
- Description: Lightweight policy row for search results.

| Attribute | Type | Required | Description |
|---|---|---|---|
| policyNumber | string | yes |  |
| productCode | string | yes |  |
| status | PolicyStatus | yes |  |
| holderName | string | yes |  |

Used by: `GET /api/policies`

## Relations

| From | Relation | To | Via | Cardinality |
|---|---|---|---|---|
| Coverage | has-one | Money | limit | 0..1 |
| Coverage | has-one | Money | deductible | 0..1 |
| IssuePolicyRequest | has-one | PolicyHolder | holder | 0..1 |
| PolicyDetails | uses-enum | PolicyStatus | status | 0..1 |
| PolicyDetails | has-one | Money | premium | 0..1 |
| PolicyDetails | has-one | PolicyHolder | holder | 0..1 |
| PolicyDetails | has-many | Coverage | coverages | 0..* |
| PolicyHolder | has-one | Address | address | 0..1 |
| PolicySummary | uses-enum | PolicyStatus | status | 1 |
