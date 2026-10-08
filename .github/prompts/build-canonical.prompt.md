---
description: Build and validate the canonical model and canonical OpenAPI spec of a region from approved decisions
agent: canonical-model
---
Build the canonical model for region ${input:region:EU} from `api-catalog/regions/${input:region:EU}.yaml`.
Loop on validation. If review items are pending, list them and stop. Release only if I say "release": ${input:release:no}.
