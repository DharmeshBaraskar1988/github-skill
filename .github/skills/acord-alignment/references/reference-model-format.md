# Reference model formats (load_reference.py)

The ACORD data standards are licensed by ACORD. Export the part of the model you are licensed to use; the kit only
normalises it. Three sources are accepted:

Where to keep it: `api-catalog/reference/acord/` (one standard for all regions). Region-specific additions, if
ever needed, go to `api-catalog/reference/<REGION>/` with their own `reference.json` named in that region's config.

## 1. Excel (recommended - easiest to export from a modelling tool)
Any sheet(s). Header row detected in the first 25 rows; names matched loosely. Only **Entity** is mandatory.

| Entity | Attribute | Type | Required | Collection | Reference To | Code List | Subject Area | Description | Parent | Synonyms | ID |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Claim | | | | | | | Claim | A demand for payment ... | | | |
| Claim | claimNumber | string | Y | | | | | Business claim number | | | |
| Claim | lossLocation | | | | Address | | | | | | |
| Claim | claimParties | | | Y | ClaimParty | | | | | | |
| ClaimStatusCode | | | | | | Open, Closed, ... | Claim | | | | |

- Row with no Attribute = the entity itself (description, subject area, parent, code list, synonyms).
- Type: string, boolean, integer/int/long, decimal/number/amount, date, datetime/timestamp, time, uuid, uri, code,
  identifier ... Unknown names are treated as references to other entities.
- Collection: Y / list / * / 0..* / unbounded / a number > 1.
- Parent: inheritance - parent attributes are matched as well (marked "inherited").
- Code List on an entity row makes it a code list (enum); on an attribute row it lists allowed values.

## 2. XSD
Named `complexType`s become entities (`_Type` suffix removed), their `element`s / `attribute`s become attributes
(`minOccurs`, `maxOccurs` honoured), `extension base` is inheritance, named `simpleType` enumerations become code lists.
Very large ACORD XSD sets: point `--source` at the main file; included files must sit next to it (or merge them first).

## 3. YAML or JSON
- **OpenAPI** (`openapi:` / `swagger:`) - `components.schemas` (or `definitions`) become entities: properties →
  attributes, `$ref` → reference, arrays → collections, `enum` schemas → code lists, `allOf: [$ref]` → parent,
  `required` honoured, `x-subject-area` / `x-acord-subject-area` read when present.
- **JSON Schema** (`$schema`, `$defs` / `definitions`) - same mapping.
- A `reference.json` (or its YAML form) produced earlier, or a **canonical-model.json** (used as a baseline region).

## 4. A folder
`--source api-catalog/reference/acord/` loads every `.yaml/.yml/.json/.xsd/.xlsx` inside (e.g. one file per ACORD
subject area) and merges them; the first definition of an entity name wins.

## Normalised shape (reference.json)
```json
{"kind": "reference", "source": "acord", "name": "ACORD", "version": "...",
 "entities": [{"name": "Claim", "kind": "object|enum", "subjectArea": "Claim", "description": "...", "parent": null,
               "codeValues": [], "synonyms": [],
               "attributes": [{"name": "claimNumber", "type": "string", "format": "", "refEntity": null,
                               "isCollection": false, "required": true, "description": "", "codeValues": []}]}]}
```
