---
name: api-analysis
description: Analyse a discovered OpenAPI spec against the business domain catalogue (Excel) and produce four artifacts - enriched OpenAPI, domains and capabilities, entities with attribute trees and relations, and a duplicate-entity report with canonical mapping. Use after api-discovery, or on any OpenAPI file, when asked to map APIs to domains/capabilities, extract entities/attributes/relations, or find duplicate models.
---

# API analysis (OpenAPI + domain Excel → 4 artifacts)

## Inputs
| Input | Default location |
|---|---|
| Discovery spec | `api-catalog/discovery/<REGION>/<app>/openapi.yaml` (must have passed discovery validation) |
| Domain catalogue (Excel) | `analysis.domainsXlsx` in config, e.g. `api-catalog/domains.xlsx` - layout in `references/domain-catalogue.md` |
| Decisions | `api-catalog/analysis/<REGION>/<app>/decisions.yaml` - agent-maintained, see `references/decisions-reference.md` |

## Outputs (`api-catalog/analysis/<REGION>/<app>/`)
| # | File | Content |
|---|---|---|
| 1 | `1-openapi.enriched.yaml` | Spec with domain as tag, `x-domain`, `x-capability`, `x-entity`, `x-duplicate-of`, filled descriptions |
| 2 | `2-domains-capabilities.json` / `.md` | Domain → capabilities (catalogue or proposed) → endpoints; entities per domain; catalogue capabilities not implemented |
| 3 | `3-entities-attributes.json` / `.md` | Canonical entities, attributes (type, required, description, enum values, present-in), attribute tree, relations (has-one, has-many, references, uses-enum), used-by endpoints |
| 4 | `4-duplicates-report.json` / `.md` | Exact and near duplicate groups, where each variant is defined and used, decision, canonical entity, schema → entity mapping |
| – | `analysis-summary.json`, `validation.json` | Counts and last validation result |

## Sensitive data (non-negotiable - full rules: `.github/instructions/api-catalog-security.instructions.md`)
- **Never write, quote or send**: credentials (keys, tokens, passwords, connection strings), **e-mail addresses**,
  **URLs**, internal host names / IP addresses, **personal data** (names of people who are customers or claimants,
  phone numbers, addresses, card numbers, IBANs, national/tax ids) or **client / customer / partner names** - not in
  correction files, outputs, commit or PR text, or chat. Use `https://{host}`, team/role names and obviously fake values.
- Seen such data in code? Do not copy or mention its value; refer to `file:line` only ("real e-mail in `X.cs:12`").
- Never open config/secret files or `api-catalog/reference/sensitive-data.yaml`. No web, fetch or browser tools,
  no `curl`/`wget`/`ssh`/mail - nothing leaves the workspace.
- The scripts redact (`[REDACTED-EMAIL]`, `[REDACTED-URL]`, ...) and the validator fails on any sensitive value
  (A10, also on `decisions.yaml`); fix at the source, never by editing outputs. Report findings by category and location only.
- Work from the spec, the Excel and `decisions.yaml`; open C# source only to confirm a duplicate or a description.

## Workflow (from the repository root)
```bash
S=.github/skills/api-analysis/scripts
python $S/load_domains.py --xlsx api-catalog/domains.xlsx --out api-catalog/domains.json   # when the Excel changed
python $S/analyze.py --config api-catalog.config.yaml
python $S/validate_analysis.py --dir api-catalog/analysis/<REGION>/<app> \
       --spec api-catalog/discovery/<REGION>/<app>/openapi.yaml --domains api-catalog/domains.json \
       --config api-catalog.config.yaml --iteration 1
```
No Excel yet? `python $S/load_domains.py --template api-catalog/domains.xlsx` writes an example to fill in — tell the user it is an example.

Before starting, check `api-catalog/discovery/<REGION>/<app>/validation.json` is `pass`. If it is not, stop and run api-discovery first.

### Validation loop (mandatory)
Repeat until `validation.json.status == "pass"` or `maxIterations` (config, default 5):
1. Read `validation.json` errors. Each has `code`, `message`, `fix` (`references/validation-codes.md`).
2. Resolve by editing **only** `decisions.yaml` (or asking the user to change the Excel when a domain/keyword is missing):
   - **A02 unclassified / A04 low confidence** - look at path, operationId, schemas and the domain list; add
     `domainAssignments.<operationId>: {domain, capability, note}`. If it truly has no business domain (health, admin),
     add it to `acceptedUnclassified` with a reason. If many endpoints miss for the same reason, propose new Excel keywords to the user.
   - **A05 proposed capability** - map to an existing catalogue capability when the meaning matches; otherwise keep it
     proposed and list it for the user to add to the Excel.
   - **A07 near duplicate** - open both source classes (`sourceFile` in the report). Same business concept → `merge` with a
     `canonical` business name. Different meaning or lifecycle (e.g. request vs. reporter vs. party) → `keep-separate`. Always add a note.
   - **A11 descriptions** - write short business descriptions in `descriptions` from XML docs, names and usage.
   - **A12 stale decision** - an operationId/schema no longer exists; remove or fix the entry.
3. Re-run `analyze.py`, then `validate_analysis.py --iteration <n+1>`.

Never edit the generated artifacts by hand. Exact duplicates are merged automatically; override with `keep-separate` if wrong.
If the loop limit is reached, stop and report remaining errors. Do not claim success.

### Finish
Report per artifact: domains used, capabilities (catalogue vs proposed), entities, relations, duplicate groups and
decisions, schemas merged, any proposed Excel changes (new domains, keywords, capabilities) as a short list the user can paste into the Excel.
