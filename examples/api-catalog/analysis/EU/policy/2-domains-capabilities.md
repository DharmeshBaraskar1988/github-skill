# Domains and capabilities - policy (EU)

## Policy

Policy administration

| Capability | Status | Operations |
|---|---|---|
| Search Policies | catalogue | `GET /api/policies` (getPolicies, high) |
| Issue Policy | catalogue | `POST /api/policies` (postPolicies, high) |
| View Policy | catalogue | `GET /api/policies/{policyNumber}` (getPoliciesById, high) |
| Renew Policy | catalogue | `POST /api/policies/{policyNumber}/renew` (postPoliciesRenew, high) |
| Get Policyholder | proposed | `GET /api/policyholders/{id}` (getPolicyholdersById, high) |

Catalogue capabilities with no endpoint here: Manage Policyholder

Entities: Address, Coverage, IssuePolicyRequest, Money, PolicyDetails, PolicyHolder, PolicyStatus, PolicySummary
