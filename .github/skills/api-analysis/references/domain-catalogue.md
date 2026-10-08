# Domain catalogue (Excel) format

First sheet (or `--sheet`). Headers are matched loosely; only **Domain** is required. Two layouts are accepted.

## Grouped layout (business capability map) - used by `api-catalog/domains.xlsx`

| Domain | Domain Description | SubCapability | SubCapability Description | Business Outcomes | Domain Keywords | SubCapability Keywords |
|---|---|---|---|---|---|---|
| Claims Management | Registration, assessment ... of claims | FNOL | Captures First Notification of Loss ... | Fair Claims Handling | claim, claims, fnol, loss, claimant | fnol, create claim, register claim |
| | | Settlement | Approves and executes claim payment ... | Loss Control | | approve claim, settle claim, settlement |
| Quotes | ... | Quote Creation | ... | Accurate Pricing | quote, quotation, premium, bind | create quote, new quote |
| (Including Bind) | | Pricing Engine Execution | ... | | | price, calculate premium |

- The domain name is written once; empty Domain cells belong to the domain above (merged cells are fine).
- A `(...)` cell under a domain name is a **scope note**; its words are added to the domain keywords.
- Business Outcomes are collected per domain (shown in the analysis and regional view).
- **Domain Keywords** / **SubCapability Keywords** drive the mapping. Without them, keywords are derived from the names
  and scope notes only (`keywordsDerived: true`, reported by `load_domains.py`) - this maps much less reliably.
- A domain with no subcapabilities is valid; endpoints mapped to it get *proposed* capabilities (A05) to add later.

## Flat layout

| Domain | Capability | Description | Keywords | Region | Application |
|---|---|---|---|---|---|
| Claims | | Claims handling from FNOL to settlement | claim, fnol, loss, claimant, settlement | | |
| Claims | Register Claim | Create a claim / first notice of loss | create claim, register, fnol, submit | | |
| Policy | | Policy administration | policy, coverage, premium, policyholder | EU, UK | |

- Row without Capability = the domain itself (description, domain keywords).
- Row with Capability = a capability of that domain (its own keywords help capability matching).
- Region / Application (comma separated, both layouts) restrict a row; empty means everywhere.
- Aliases accepted: "Business Domain", "Bounded Context", "Business Capability", "SubCapability", "Synonyms", "Terms",
  "Project", "System", "Business Outcomes".

## Writing good keywords
List the **nouns your APIs actually use** in routes, operationIds and DTO names (`fnol`, `claimant`, `endorsement`),
and for subcapabilities the **verb + noun** phrases (`approve claim`, `issue policy`). Plurals and camelCase are
normalised automatically. Avoid generic words (`management`, `data`, `service`) and never put client names, e-mail
addresses or URLs in the workbook.

## How mapping works
Each endpoint is tokenised: static path segments (x2), tags (x2), operationId, request/response schema business names,
summary (x0.5). Score per domain = matches with domain name + domain keywords, plus half for capability keywords.
- best score ≥ `minDomainScore` and ahead of the runner-up by `minDomainMargin` → **high** confidence
- otherwise → **low** confidence (warning A04, error if `strictDomains`)
- no match → **unclassified** (error A02 until decided)

Capability: derived from verb + resource (`GET /claims` → List Claims, `POST /claims/{id}/approve` → Approve Claim),
then matched to the domain's catalogue capabilities by tokens with verb synonyms (get/view/read, list/search/find,
create/register/submit/add, update/modify, delete/remove/close, upload/attach). No match → **proposed**.
