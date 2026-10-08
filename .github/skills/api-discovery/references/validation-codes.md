# Discovery validation codes

| Code | Severity | Meaning | Typical fix |
|---|---|---|---|
| D01 | error | OpenAPI document invalid | Usually a bad override (wrong status key, malformed schema in externalTypes). Fix overrides, rebuild |
| D02 | error | A `$ref` points nowhere | Add the missing type (externalTypes / extraTypeFiles) |
| D03 | error | Source has more route declarations than the scanner captured | Open the file, find the missed route, add under `addEndpoints` |
| D04 | error | Inventory endpoint missing in spec, or exclude without reason | Two endpoints on same method+path, or add a `reason` |
| D05 | error | Unresolved C# type | Locate it (NuGet, other repo, generated code). externalTypes / extraTypeFiles. Or add the project folder to `sourceRoots` |
| D06 | error | Operation still flagged `x-needs-review` | Read the handler, set the real request/response in overrides |
| D07 | error/warn | No 2xx response (error); POST without body or 2xx without schema (warning) | Confirm in code; declare in overrides |
| D08 | error | Duplicate operationId | `set.operationId` |
| D09 | error | Sensitive data (credentials, e-mails, URLs, hosts/IPs, PII, client names) in spec, overrides, inventory or style profile | Remove it from overrides/config at the source; the message gives category + file:line only |
| D14 | warning | Source code contained sensitive values that were redacted from inventory/spec | Nothing to fix in the catalogue; tell the code owners (comments, defaults or examples hold real data) |
| D10 | error | Schema without `x-source-project` | externalTypes entries must declare `x-source-project` |
| D11 | warn (error if `discovery.requireDescriptions`) | Missing summaries/descriptions | Add via `endpoints[].set.summary` / `types.<T>.description` from XML docs or code meaning |
| D12 | warn (error if `discovery.style.strict`) | Deviates from the style examples (path/property case, info fields, common headers, summaries) | Code change, config `info:`, or overrides after checking code |
| D13 | error | Content copied from the style examples (path, schema, long text) | Remove it; examples are a reference only |

The loop ends when `status == pass`. Warnings do not block, but list them in your final report.
