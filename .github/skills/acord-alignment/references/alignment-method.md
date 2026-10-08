# Alignment method

## Regional entities
Input entities are already de-duplicated per application (api-analysis). Across the applications of a region, entities
that are exact or same-name duplicates (regional view "cross-app duplicates") or share the same name are grouped into one
regional entity. Overrides: `clusters: [{members: ["EU/claims:X", "EU/policy:Y"], decision: merge|separate, name, note}]`.

## Normalisation
camelCase / PascalCase split, lower-cased, singular; generic synonyms (id→identifier, post/zip→postal, inception/start→
effective, expiry/end→expiration, firstName→givenName, lastName→surname, email/emailAddress, money→monetaryAmount,
claimant→claimParty, customer/policyholder/insured→party ...). Attribute names lose the tokens of their own entity name
(`claimNumber` in Claim → `number`) and soft tokens (`code`, `value`) before comparison. Add your own in `synonyms.yaml`.

## Attribute match
- name similarity: 1.0 for the same normalised key, else token Jaccard (≥ 0.6 when one is contained in the other);
  0.6 floor when both reference entities that are themselves aligned (claimants → claimParties).
- type compatibility: same type/format 1.0, date vs date-time 0.7, integer vs number 0.8, both references 1.0 when the
  referenced entities are aligned (second pass), list vs single 0.3, object vs primitive 0.1.
- a pair matches when name ≥ 0.75, or name ≥ 0.5 and type ≥ 0.9. One-to-one greedy assignment by score.
- status: match (name ≥ 0.9, type ≥ 0.9), similar, type-conflict (type < 0.7), no-match.

## Entity score
`0.3 × name similarity + 0.7 × coverage × quality` where coverage = matched / our attributes and quality = mean
attribute match score. Baseline candidates get +0.05. Code lists: `0.4 × name + 0.6 × value coverage`.

| Status | Rule | Recommendation |
|---|---|---|
| full | score ≥ fullMatchThreshold (0.8), all our attributes matched, no type conflict | Use reference as-is / Reuse baseline |
| partial | score ≥ partialMatchThreshold (0.45) | Extend reference / Extend baseline |
| none | below | Custom canonical entity |
| ambiguous | top two different references within ambiguityMargin (0.05) | agent override needed (AL03) |

## Percentages
Entity % = score × 100. Domain / application % = average of their entities. Endpoint % = average of the entities in its
request, 2xx responses and parameters (envelopes such as `PagedResult<ClaimDto>` resolve to their items).

## Review fingerprint (basis)
Every entity / attribute / endpoint row has a `basis` hash (attribute names + types + chosen reference). Approvals store
the basis they were given for. If the alignment changes that row later, the approval shows as **changed** and the
canonical model treats it as pending until re-reviewed.
