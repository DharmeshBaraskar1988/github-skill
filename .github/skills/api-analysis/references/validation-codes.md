# Analysis validation codes

| Code | Severity | Meaning |
|---|---|---|
| A01 | error | An operation of the discovery spec is missing from domains-capabilities |
| A02 | error | Unclassified operation with no decision |
| A03 | error | Domain used is not in the catalogue |
| A04 | warn / error (`strictDomains`) | Low-confidence keyword mapping |
| A05 | warn / error (`strictCapabilities`) | Capability not in the catalogue (proposed) |
| A06 | error | A schema is not represented as entity, merged, or excluded (envelope/problem) |
| A07 | error | Near-duplicate group without a decision |
| A08 | error | Entity name collision or relation to a missing entity |
| A09 | error | Enriched spec invalid or operation count differs from discovery |
| A10 | error | Secret-like content in outputs |
| A11 | warn / error (`requireDescriptions`) | Entities/attributes without description |
| A12 | error | Stale decision (unknown operationId/schema) |
