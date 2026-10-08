---
name: api-discovery
description: Crawl a .NET solution (minimal APIs, controllers, Azure Functions, shared model libraries) and produce a validated OpenAPI 3.0 spec with full request/response schemas and $ref model graph. Use when asked to discover, inventory, document or generate OpenAPI/Swagger for .NET APIs, endpoints, functions or DTOs.
---

# API discovery (.NET → OpenAPI)

Produces, per application, a reproducible and validated OpenAPI document from source code.
The heavy lifting is done by scripts (deterministic, complete); you (the agent) handle what
static analysis cannot prove, and you loop on the validator until it passes.

## Inputs

| Input | Where | Notes |
|---|---|---|
| Repository | workspace root or `repoRoot` in config | .NET 6–9. Projects found via `*.csproj` |
| Config | `api-catalog.config.yaml` (repo root) | region, application, sourceRoots, outputDir — copy `templates/api-catalog.config.template.yaml` if missing |
| Overrides | `<outputDir>/overrides.yaml` | the ONLY place you record corrections — see `references/overrides-reference.md` |

## Outputs (`api-catalog/discovery/<REGION>/<application>/`)

- `inventory.json` – everything the scanner proved (projects, endpoints, types, non-HTTP functions, needsReview)
- `openapi.yaml` – the spec (generated, never hand-edited)
- `discovery-report.md` – human summary
- `validation.json` – last validator result (the loop reads this)

## Style examples - reference, never copy
Put example OpenAPI specs that show your house style in `api-catalog/style-examples/_global/` (all regions) and/or
`api-catalog/style-examples/<REGION>/` (region-specific; both are read, region adds to global). Every `build_openapi.py`
run learns the **conventions** into `style-profile.json` and applies the safe ones automatically:
operationId case, tag case, security-scheme names, standard error responses (ProblemDetails, only codes most example
operations use; 401/403 only on secured operations, 404 only with path parameters; each marked `x-style-added`), and
`info` fields from YOUR config `info:` block. Listed in `info.x-style-applied`.
What cannot be changed without changing the API (path / property casing, required headers) is reported as **D12**
(warnings; errors with `discovery.style.strict: true`) - fix in code, or with overrides only after checking the code.
**D13 copy guard (error):** a path, schema name or long text that exists in the examples but not in this code means
something was copied - remove it. Use the examples to learn *how* to write summaries/descriptions, then write them
for this API from its code. Override the folders with `discovery.styleExamples: [paths]`; in central mode set
`catalogRoot:` so the default folders resolve.

## Security rules (non-negotiable)

1. Never open `appsettings*.json`, `local.settings.json`, `secrets.json`, `.env*`, `*.pfx`, `*.pem`, `*.key`,
   `*.pubxml`, `launchSettings.json`, `web.config`. The scanner skips them; you must too. Hooks deny them in Copilot CLI / cloud agent.
2. Never copy a host name, connection string, key, token or real customer data into overrides or the spec.
   Servers stay placeholders (`https://{host}`).
3. Never send source files outside the workspace (no web tools, no pasting code into URLs).
4. Read only the source files a `needsReview` item points to (`file:line`) plus the types they reference.

## Workflow

Run commands from the repository root. Python 3.10+ with `pyyaml`, `openpyxl`, `openapi-spec-validator`
(`pip install -r .github/skills/requirements.txt`).

```bash
S=.github/skills/api-discovery/scripts
python $S/scan_dotnet.py      --config api-catalog.config.yaml          # 1. scan -> inventory.json
python $S/build_openapi.py    --config api-catalog.config.yaml          # 2. build -> openapi.yaml
python $S/validate_discovery.py --dir <outputDir> --config api-catalog.config.yaml --iteration 1   # 3. validate
```

(Windows PowerShell: same commands with `python` and `$S=".github/skills/api-discovery/scripts"`.)

### Step 4 – validation loop (mandatory)

```
iteration = 1
while validation.json.status == "fail" and iteration <= maxIterations (config, default 5):
    for each error in validation.json.errors (group by code):
        follow its "fix" text; see references/validation-codes.md
        record the correction in overrides.yaml WITH a `note:` citing file:line you checked
    python build_openapi.py ...   (re-run scan_dotnet.py only if you changed config/excludes)
    iteration += 1
    python validate_discovery.py ... --iteration <iteration>
```

- Never edit `openapi.yaml` or `inventory.json` directly. Never delete an error by excluding an endpoint
  unless the endpoint is genuinely not part of the public contract (health probes, internal callbacks) — and say why in `reason`.
- Never invent a type. If a type comes from a NuGet package / another repo / a DLL, add it to `externalTypes`
  (shape copied from its source) or generate it with `tools/TypeExtractor` and list the JSON under `extraTypeFiles`.
- If the loop hits `maxIterations`, stop, and report the remaining errors to the user. Do not claim success.

### Step 5 – finish

Report: projects found (kind + target framework), endpoint count, schema count, non-HTTP functions,
overrides you added (one line each), remaining warnings. Point to `discovery-report.md`.

## What the scanner understands

See `references/dotnet-patterns.md`. In short: `MapGet/MapPost/...` with `MapGroup` prefixes, `.Produces<T>()`,
`.Accepts<T>()`, `TypedResults`/`Results<...>`, handler methods; `[ApiController]` + `[Route]` + `[HttpX]` +
`ActionResult<T>`/`[ProducesResponseType]`; Azure Functions isolated `[Function]` and in-process `[FunctionName]`
with `[HttpTrigger]`, `host.json` routePrefix, `[OpenApi*]` attributes, `ReadFromJsonAsync<T>`; classes, records,
enums, inheritance, generics, XML `<summary>`, DataAnnotations, `JsonPropertyName`, `JsonIgnore`.

## Typical needsReview items and how to resolve them

| Message | What to do |
|---|---|
| Success response type could not be determined | Open handler at `x-source-file:x-source-line`, find what is returned, `set.responses: {"200": TypeName}` |
| Response body type not statically declared (Functions) | Find the object passed to `WriteAsJsonAsync`/`OkObjectResult`, set responses |
| Request body type not found | Find `ReadFromJsonAsync<T>`/`Deserialize<T>` or the bound model, `set.requestBody: T` |
| HttpTrigger declares no methods | Read the body (branching on `req.Method`) and set the real verbs; exclude the fake ones with reason |
| ExcludeFromDescription() is set | Usually `exclude: true` + reason (infra endpoint) |
| Type not found in scanned source | `externalTypes` or `extraTypeFiles` (DLL) |
| D03 raw count > captured | A route the parser missed (unusual syntax). Add it under `addEndpoints` |
