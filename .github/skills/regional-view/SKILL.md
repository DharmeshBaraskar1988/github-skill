---
name: regional-view
description: Build a regional API catalogue view (one interactive HTML page plus an Excel workbook) from many applications' analysis outputs or dumped OpenAPI specs, with filters by region and application and tabs for domains, capabilities, entities, attributes, endpoints and duplicates. Use when asked for a regional view, catalogue, landscape, cross-application comparison, or HTML/Excel overview of APIs.
---

# Regional view (many apps → HTML + Excel)

## Input
One folder (config `regionalView.inputDir`, default `api-catalog/`). Any depth. Per application it accepts:

| Found | Treated as |
|---|---|
| a folder with `analysis-summary.json` (+ 2-/3-/4- artifacts) | validated analysis output, used as is |
| a bare OpenAPI 3.x file (`.yaml`, `.yml`, `.json`) | external spec, analysed inline with the domain catalogue (and a `decisions.yaml` beside it, if any) |

Discovery specs that already have an analysis folder are skipped. Region/application come from `info.x-region` /
`info.x-application`, else from the layout `<input>/<REGION>/<application>/<file>`, else the file name.
So teams can simply drop specs into `api-catalog/external/<REGION>/<app>/openapi.json`.

## Output (`regionalView.outputDir`, default `api-catalog/regional-view/`)
- `regional-view.html` - single self-contained file (no CDN, works offline / on a file share). Region selector,
  application chips (multi-select), domain filter, search; tabs Overview (KPIs, domain × application matrix, app cards
  with validation status), Domains & capabilities, Entities & attributes (attribute tree, relations, used-by, same entity
  in other apps), Endpoints, Duplicates (within app + across apps/regions), Validation. CSV export of the current table, light/dark.
- `regional-view.xlsx` - sheets Summary, Applications, Domain_Matrix, Domains_Capabilities, Endpoints, Entities,
  Attributes, Relations, Duplicates, Cross_App_Duplicates, Validation (filters and frozen headers).
- `regional-view-data.json` - the aggregated data (also embedded in the HTML).
- `spec-viewer.html` - every OpenAPI spec of the catalogue (discovery, enriched, external, canonical) and the canonical
  models, each viewable as **YAML or JSON** with outline, `$ref` navigation, search, copy and download. Rebuild the
  regional view after a canonical build to include the canonical specs.

## Sensitive data (non-negotiable - full rules: `.github/instructions/api-catalog-security.instructions.md`)
- **Never write, quote or send**: credentials (keys, tokens, passwords, connection strings), **e-mail addresses**,
  **URLs**, internal host names / IP addresses, **personal data** (names of people who are customers or claimants,
  phone numbers, addresses, card numbers, IBANs, national/tax ids) or **client / customer / partner names** - not in
  correction files, outputs, commit or PR text, or chat. Use `https://{host}`, team/role names and obviously fake values.
- Seen such data in code? Do not copy or mention its value; refer to `file:line` only ("real e-mail in `X.cs:12`").
- Never open config/secret files or `api-catalog/reference/sensitive-data.yaml`. No web, fetch or browser tools,
  no `curl`/`wget`/`ssh`/mail - nothing leaves the workspace.
- The scripts redact (`[REDACTED-EMAIL]`, `[REDACTED-URL]`, ...) and the validator fails on any sensitive value
  (R08 on the HTML, data and spec viewer; external specs are redacted when loaded); fix at the source, never by editing outputs. Report findings by category and location only.

## Workflow
```bash
S=.github/skills/regional-view/scripts
python $S/build_regional_view.py --config api-catalog.config.yaml
#   or: --input api-catalog --domains api-catalog/domains.json --out api-catalog/regional-view
python $S/validate_regional_view.py --out api-catalog/regional-view --iteration 1
```

### Validation loop (mandatory)
Repeat until `validation.json.status == "pass"` or `maxIterations`:
- **R05** an input application failed discovery/analysis validation → run those skills' loops for that application
  (or, only if the user explicitly accepts it, rebuild with `--allow-failed` and say so in the report).
- **R01/R02/R03/R04** → rebuild; if it persists, an input artifact is stale or corrupt - re-run analyze.py for that app.
- **R08** sensitive data in output → find which input contains it (category + file are in the message), fix at the source (overrides/decisions, or ask the team that dumped the external spec), rebuild everything downstream.
- Warnings R06 (external specs not validated) and R07 (unclassified / undecided) go into the final report.

### Finish
Report: regions, applications (with mode and validation status), totals, top cross-application duplicates
(they are candidates for a shared canonical model), and the paths of the HTML and Excel files.

## Customising
- Title: `regionalView.title`. Look and feel: `assets/regional-view.template.html` (CSS variables at the top).
- Cross-application duplicate sensitivity: `regionalView.crossAppThreshold`.
