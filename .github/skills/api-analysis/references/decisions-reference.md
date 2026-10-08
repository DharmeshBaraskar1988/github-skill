# decisions.yaml reference (api-analysis)

```yaml
domainAssignments:                 # operationId -> domain (+ capability)
  GetFnolStatus:
    domain: Claims                 # must exist in the catalogue (A03)
    capability: Register Claim     # catalogue capability, or a new name (stays "proposed")
    note: Status lookup is part of the FNOL journey (FnolFunctions.cs:24)

acceptedUnclassified:              # endpoints with no business domain
  - operationId: GetHealth
    reason: Infrastructure probe

duplicates:                        # decisions for duplicate groups (members as schema names)
  - members: [ClaimDto, ClaimResponse]
    decision: merge                # merge | keep-separate
    canonical: Claim               # business name of the merged entity
    note: Identical shape, both represent the claim aggregate
  - members: [ClaimantDto, PolicyHolderInfo]
    decision: keep-separate
    note: Reporter of a loss is not necessarily a claimant

entityNames:                       # rename a single schema's entity
  FnolSubmission: FirstNoticeOfLoss

descriptions:                      # entity / attribute descriptions (schema or entity name)
  Claim: Insurance claim raised against a policy.
  Claim.lossDate: Date on which the loss occurred.
```

Notes
- Exact duplicates (identical attribute names and types) are merged automatically into their common business name
  (`ClaimDto` + `ClaimResponse` → `Claim`). Add a `keep-separate` decision to undo.
- Near duplicates (attribute containment ≥ `nearDuplicateThreshold`, Jaccard ≥ 0.75, or same business name with
  overlap ≥ 0.4) need a decision (A07).
- Decisions referring to operationIds/schemas that disappeared are reported as A12.
