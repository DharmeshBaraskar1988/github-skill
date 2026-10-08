# Canonical validation codes

| Code | Severity | Meaning |
|---|---|---|
| C01 | error (warning with allowPending) | Pending or changed review items |
| C02 | error | Reference to an entity that is not approved |
| C03 | error | Canonical OpenAPI invalid / unresolved $ref |
| C04 | error / warning | Conflicting types merged; duplicate operationId or path (error); merged contract variants (warning) |
| C05 | error | Endpoint uses a rejected entity (when not auto-dropped) |
| C06 | error | Baseline entity/attribute removed or retyped |
| C07 | error / warning | Missing lineage row (error); canonical attribute without source (warning) |
| C08 | error / warning | approvals.yaml missing or not written by import_review.py (error); stale approval keys (warning) |
| C09 | error | Secret-like content |
| C10 | warning | Missing descriptions |
| C11 | error / warning | Breaking change on a released version (error) / before release (warning) |
| C12 | error | Alignment regenerated after the build |
| C13 | error | Outputs missing, YAML/JSON differ, or a released version differs from the current build |

## Global (validate_global.py)
| Code | Severity | Meaning |
|---|---|---|
| G01 | error / warning | Region not approved / not released (error); skipped regions (warning) |
| G02 | error | Regions disagree on an entity or attribute type |
| G03 | error | Global OpenAPI invalid, unresolved $ref, YAML ≠ JSON, outputs missing |
| G04 | error | Something from a region model is missing in the global model |
| G05 | warning | operationId renamed because two regions used it for different endpoints |
| G06 | error | Secret-like content |
