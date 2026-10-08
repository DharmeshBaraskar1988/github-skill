# Domain catalogue (Excel) format

First sheet (or `--sheet`). Headers are matched loosely; only **Domain** is required.

| Domain | Capability | Description | Keywords | Region | Application |
|---|---|---|---|---|---|
| Claims | | Claims handling from FNOL to settlement | claim, fnol, loss, claimant, settlement | | |
| Claims | Register Claim | Create a claim / first notice of loss | create claim, register, fnol, submit | | |
| Claims | Approve Claim | | approve, settle | | |
| Policy | | Policy administration | policy, coverage, premium, policyholder | EU, UK | |

- Row without Capability = the domain itself (description, domain keywords).
- Row with Capability = a capability of that domain (its own keywords help capability matching).
- **Keywords drive the mapping.** List the nouns that appear in your routes, operationIds and DTO names
  (`fnol`, `claimant`, `endorsement`). Plurals and camelCase are normalised automatically.
- Region / Application (comma separated) restrict a row; empty means everywhere.
- Aliases accepted: "Business Domain", "Bounded Context", "Business Capability", "Synonyms", "Terms", "Project", "System".

## How mapping works
Each endpoint is tokenised: static path segments (x2), tags (x2), operationId, request/response schema business names,
summary (x0.5). Score per domain = matches with domain name + domain keywords, plus half for capability keywords.
- best score ≥ `minDomainScore` and ahead of the runner-up by `minDomainMargin` → **high** confidence
- otherwise → **low** confidence (warning A04, error if `strictDomains`)
- no match → **unclassified** (error A02 until decided)

Capability: derived from verb + resource (`GET /claims` → List Claims, `POST /claims/{id}/approve` → Approve Claim),
then matched to the domain's catalogue capabilities by tokens with verb synonyms (get/view/read, list/search/find,
create/register/submit/add, update/modify, delete/remove/close, upload/attach). No match → **proposed**.
