---
description: Discover all HTTP endpoints and models of this .NET repository and produce a validated OpenAPI spec
agent: api-discovery
---
Run API discovery for this repository using `api-catalog.config.yaml`
(region: ${input:region:EU}, application: ${input:application}).

1. Scan, build and validate as described in the api-discovery skill.
2. Loop on `validation.json` until it passes or the iteration limit is reached; record every correction in
   `overrides.yaml` with a note citing file:line.
3. Report projects, endpoint and schema counts, non-HTTP functions, overrides added and open warnings.
