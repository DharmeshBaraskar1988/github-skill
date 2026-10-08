---
name: canonical-model
description: Build the approved canonical model of a region from reviewed ACORD alignment decisions - canonical entities and attributes, relations, source-to-canonical mapping, and ONE canonical OpenAPI spec - and release it as the baseline for other regions (e.g. EU baseline used by UK). Use when asked for canonical models, canonical API specs, the approved baseline, or source-to-canonical mappings.
---

# Canonical model (approved alignment → canonical models + canonical OpenAPI)

## Inputs
| Input | Where |
|---|---|
| Region config | `api-catalog/regions/<REGION>.yaml` (`canonical:` section; `baseline:` for regions that build on another) |
| Whole-region alignment | `api-catalog/alignment/<REGION>/alignment.json` (not a slice) with validation `pass` |
| Human approvals | `api-catalog/alignment/<REGION>/approvals.yaml` - written by `import_review.py` only |
| Baseline (optional) | released `canonical/<OTHER>/releases/<v>/canonical-model.json` |

## Outputs (`api-catalog/canonical/<REGION>/`)
| File | Content |
|---|---|
| `canonical-model.json` | canonical entities (approach, reference, status baseline/approved, sources), attributes (reference attribute, extension flag, introduced-in region, sources), code lists with value mapping, relations, canonical endpoints with source operations, lineage, pending / rejected / excluded lists. Also the **baseline input** for the next region. |
| `canonical-viewer.html` | YAML / JSON viewer for the canonical OpenAPI spec and the canonical model: toggle format, outline (paths, schemas, entities, endpoints), clickable `$ref`s, search, copy, download |
| `canonical-model.yaml` | the same canonical model as YAML (identical content to the JSON - validated, C13) |
| `canonical-openapi.yaml` / `.json` | ONE OpenAPI 3.0.3 spec: canonical paths (deduplicated across apps) and `components/schemas` = canonical entities (+ `<Entity>Page` envelopes, ProblemDetails). `x-reference`, `x-extension`, `x-sources`, `x-source-operations` keep traceability. |
| `source-to-canonical-mapping.json` | every app schema attribute → regional entity → canonical entity.attribute → reference attribute, with transformation (rename / type change) or why it was excluded / dropped / rejected |
| `canonical-model.xlsx` | Summary, Entities, Attributes, Relations, Endpoints, Source_Mapping, Changes, Excluded |
| `canonical-model.md`, `CHANGELOG.md` | readable model; changes vs previous build and vs baseline |
| `releases/<version>/` | immutable frozen copy (`--release`) - this is what other regions use as baseline |

## Rules the build applies
- Only approved rows are used. `approve` = the alignment recommendation. Several regional entities approved onto the same
  reference become ONE canonical entity (Claim ← ClaimDto + ClaimResponse + CreateClaimRequest + UpdateClaimRequest + FnolSubmission).
- use-as-is: reference names and types; our unmatched attributes are dropped (recorded in lineage).
  extend: reference attributes + our extra attributes flagged `x-extension`. custom: our attributes.
- Baseline regions: every baseline entity and attribute is kept unchanged; the region only adds entities, attributes
  (`x-introduced-in: <REGION>`) and code values. Removing or retyping baseline items fails validation (C06).
- Rejected entities: their endpoints are left out (`dropEndpointsWithRejectedEntities`, default true) and listed.
- Pending / changed approvals → model status **draft** and validation fails (C01) unless `canonical.allowPending: true`.

## Sensitive data (non-negotiable - full rules: `.github/instructions/api-catalog-security.instructions.md`)
- **Never write, quote or send**: credentials (keys, tokens, passwords, connection strings), **e-mail addresses**,
  **URLs**, internal host names / IP addresses, **personal data** (names of people who are customers or claimants,
  phone numbers, addresses, card numbers, IBANs, national/tax ids) or **client / customer / partner names** - not in
  correction files, outputs, commit or PR text, or chat. Use `https://{host}`, team/role names and obviously fake values.
- Seen such data in code? Do not copy or mention its value; refer to `file:line` only ("real e-mail in `X.cs:12`").
- Never open config/secret files or `api-catalog/reference/sensitive-data.yaml`. No web, fetch or browser tools,
  no `curl`/`wget`/`ssh`/mail - nothing leaves the workspace.
- The scripts redact (`[REDACTED-EMAIL]`, `[REDACTED-URL]`, ...) and the validator fails on any sensitive value
  (C09 / G06); fix at the source, never by editing outputs. Report findings by category and location only.

## Workflow
```bash
S=.github/skills/canonical-model/scripts
python $S/build_canonical.py --config api-catalog/regions/EU.yaml
python $S/validate_canonical.py --config api-catalog/regions/EU.yaml --iteration 1
# when validation passes and the owners agree:
python $S/build_canonical.py --config api-catalog/regions/EU.yaml --release     # freezes canonical.version
```
Next region: set `baseline: ../canonical/EU/releases/1.0.0/canonical-model.json` in `regions/UK.yaml`, run the
acord-alignment skill for UK (baseline candidates are preferred), review, then this skill for UK.

### Global canonical model (all regions)
When regions are released, merge them into ONE enterprise model:
```bash
python $S/merge_global.py --catalog api-catalog          # optional api-catalog/global.yaml (version, title, pinned regions)
python $S/validate_global.py --catalog api-catalog
```
Output `api-catalog/canonical/GLOBAL/`: `global-canonical-model.json/.yaml`, `global-canonical-openapi.yaml/.json`,
`global-source-mapping.json`, `global-canonical.xlsx` and `global-canonical.html` - an explorer that filters by region
(used by the region's APIs, or available in its canonical), application, domain, origin (ACORD / custom) and API
search, and shows the **filtered OpenAPI spec live as YAML or JSON** with copy / download.
Only approved regions enter; by default only **released** versions (`requireReleased: false` to include current
approved builds). G02 conflicts (regions typing the same attribute differently) mean a region was not aligned on the
other's baseline - fix by re-aligning that region with `baseline:`; never edit the global files.

### Validation loop (mandatory)
Repeat until `validation.json.status == "pass"` or `maxIterations`:
- **C01 pending / changed** - you cannot fix this yourself. List the items, tell the user which reviewers must decide in
  the alignment HTML/Excel, and stop. After they import, re-run `align.py` then this skill.
- **C02 unresolved reference** - an approved entity points to a pending/rejected one: report both entity names; reviewers
  approve the target or exclude/rename the attribute.
- **C03/C04/C05** - re-run the build; persisting duplicates need canonical paths / operationIds / names from reviewers.
- **C06 baseline broken** - never "fix" by editing the baseline; report it - the change belongs in the baseline region.
- **C11/C13 version** - bump `canonical.version` in the region config (major for breaking changes) and rebuild.
- **C12 stale** - re-run `build_canonical.py`.

Never edit canonical outputs, `approvals.yaml` or releases by hand. Never release a draft.

### Finish
Report status (approved / draft), version, entity / attribute / endpoint counts, how many came from the baseline vs new,
extensions, rejected entities and dropped endpoints, changes vs previous and vs baseline, and the output paths.
