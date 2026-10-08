---
description: Build the regional API catalogue (HTML + Excel) from all analysis outputs and dumped OpenAPI specs
agent: regional-view
---
Build the regional view from `${input:inputDir:api-catalog}`.

- List the applications found (region, application, validated analysis or external spec) before building.
- Build, validate, loop until pass. Do not use --allow-failed without asking me.
- Report totals, cross-application duplicates and the output file paths.
