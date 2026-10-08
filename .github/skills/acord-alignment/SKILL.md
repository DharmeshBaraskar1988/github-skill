---
name: acord-alignment
description: Align a region's de-duplicated entities, attributes, domains and endpoints with the ACORD reference model (and with an approved baseline canonical model of another region), score each match as full / partial / none with percentages, and produce an interactive HTML review page and an Excel review workbook where humans approve, extend, rename or reject. Use for ACORD alignment, ACORD mapping, gap analysis against ACORD, or checking how well one application (e.g. claims) aligns.
---

# ACORD alignment (regional view → scored matches → human review)

## Inputs
| Input | Where |
|---|---|
| Region config | `api-catalog/regions/<REGION>.yaml` (copy `templates/region.config.template.yaml`) |
| Regional data | `api-catalog/regional-view/regional-view-data.json` (regional-view skill must have passed) |
| ACORD reference | Your **licensed** ACORD model as Excel, XSD, YAML / JSON (OpenAPI or JSON Schema) or a folder of them, normalised with `load_reference.py` (format: `references/reference-model-format.md`). The kit contains no ACORD content. |
| Baseline (optional) | `canonical/<OTHER REGION>/releases/<v>/canonical-model.json`, e.g. EU when aligning UK. Baseline candidates are preferred over ACORD ones. |
| Synonyms (optional) | `api-catalog/reference/synonyms.yaml` (organisation vocabulary) |

## Outputs (`api-catalog/alignment/<REGION>/` or a slice such as `/claims`)
- `acord-alignment.html` - review page: filters by application / domain / match / review state, alignment % per
  domain, application, entity and endpoint, side-by-side attribute matching, candidates, decision controls,
  **Approve all** (recommendations or full matches only, for everything in the current filters, optionally with their
  endpoints, with undo), **Export decisions** (`review-decisions.json`).
- `acord-alignment.xlsx` - review workbook: Domains, Applications, Entities, Attributes, Endpoints, Candidates; yellow
  decision columns with drop-downs.
- `alignment.json`, `alignment-report.md`, `validation.json`.
- `approvals.yaml` - human decisions, written ONLY by `import_review.py`.
- `alignment-overrides.yaml` - your (agent) corrections to the matching, each with a note.

## How matching works (short; details in `references/alignment-method.md`)
1. Same entity in several applications of the region is grouped into one **regional entity** (cross-app exact /
   same-name duplicates). Source schemas stay listed, so lineage is kept: schema → app entity → regional entity.
2. Each regional entity is scored against every reference entity: 30 % name similarity (with synonyms) + 70 % share of
   our attributes matched × match quality (name + type compatibility). Code lists compare values.
3. **full** (all our attributes matched, no type conflict, score ≥ 80 %) → *Use reference as-is*;
   **partial** (≥ 45 %) → *Extend reference*; **none** → *Custom canonical entity*. With a baseline: *Reuse / Extend baseline*.
4. Entities that map to the same reference entity (e.g. `ClaimDto`, `CreateClaimRequest`, `UpdateClaimRequest` → Claim)
   are flagged "merges with" - they become one canonical entity.
5. Endpoint alignment = average of the entities in its request/response; a canonical path is proposed
   (`/api/v1/claims/{id}/claimants` → `/claims/{id}/claim-parties`).

## Sensitive data (non-negotiable - full rules: `.github/instructions/api-catalog-security.instructions.md`)
- **Never write, quote or send**: credentials (keys, tokens, passwords, connection strings), **e-mail addresses**,
  **URLs**, internal host names / IP addresses, **personal data** (names of people who are customers or claimants,
  phone numbers, addresses, card numbers, IBANs, national/tax ids) or **client / customer / partner names** - not in
  correction files, outputs, commit or PR text, or chat. Use `https://{host}`, team/role names and obviously fake values.
- Seen such data in code? Do not copy or mention its value; refer to `file:line` only ("real e-mail in `X.cs:12`").
- Never open config/secret files or `api-catalog/reference/sensitive-data.yaml`. No web, fetch or browser tools,
  no `curl`/`wget`/`ssh`/mail - nothing leaves the workspace.
- The scripts redact (`[REDACTED-EMAIL]`, `[REDACTED-URL]`, ...) and the validator fails on any sensitive value
  (AL09, also on `alignment-overrides.yaml` and `approvals.yaml`; `import_review.py` strips e-mails and other sensitive values from reviewer and comment fields); fix at the source, never by editing outputs. Report findings by category and location only.

## Workflow
```bash
S=.github/skills/acord-alignment/scripts
python $S/load_reference.py --source api-catalog/reference/acord-export.xlsx --name ACORD --version "<licence version>" \
       --out api-catalog/reference/acord.reference.json                     # once per ACORD export
python $S/align.py --config api-catalog/regions/EU.yaml                     # whole region (needed for the canonical model)
python $S/align.py --config api-catalog/regions/EU.yaml --apps claims       # only claims (report / check)
python $S/validate_alignment.py --dir api-catalog/alignment/EU --iteration 1
```
No ACORD export yet? `load_reference.py --sample <file.xlsx>` writes an **invented, non-ACORD** sample so you can try
the pipeline. Say clearly that results based on it are not ACORD alignment.

### Validation loop (matching quality - mandatory)
Repeat until `validation.json.status == "pass"` or `maxIterations`:
- **AL03 ambiguous** - compare the candidates' attributes and meaning (open the source classes listed in the row) and
  write `entityMatches.<Entity>: {reference, source, note}` (or `reference: null` for no match).
- **AL05/AL06** - fix or annotate overrides.
- **AL07 stale** - re-run `align.py` (and the regional view first if sources changed).
- Wrong attribute pairing you can prove → `attributeMatches.<Entity.attr>: {reference: <refAttr>|null, note}`.
- Same entity wrongly grouped / not grouped across apps → `clusters: [{members, decision: merge|separate, note}]`.
Then re-run `align.py` + `validate_alignment.py --iteration n+1`.

Warnings AL04 (type conflicts with ACORD) and AL08 (type differs between apps) are for reviewers - list them.

### Human review (not the agent's job)
Tell the user: open `acord-alignment.html` (or the `.xlsx`), decide each entity (approve / use-as-is / extend / custom /
reject with comment), optionally attributes and endpoints, enter the reviewer name, export / save. Then:
```bash
python $S/import_review.py --dir api-catalog/alignment/EU --json review-decisions.json      # and/or --xlsx reviewed.xlsx
python $S/align.py --config api-catalog/regions/EU.yaml                                      # refresh review state
```
**Never write or edit `approvals.yaml`, never fill decision columns, never "approve" on the user's behalf** - even if asked to
speed things up, the decision must come from a named human reviewer via the HTML/Excel. If the user explicitly says
"approve all recommendations" in chat, tell them to use the page's bulk button (it records them as reviewer).

### Finish
Report overall %, per domain and per application, full/partial/none counts, ambiguous resolved (with notes), type
conflicts, review progress (pending / changed), and the HTML + Excel paths.
