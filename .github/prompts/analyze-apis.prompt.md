---
description: Map the discovered OpenAPI spec to business domains and capabilities, extract entities and relations, resolve duplicates
agent: api-analysis
---
Run the api-analysis skill for region ${input:region:EU}, application ${input:application}.

- Domain catalogue: `${input:domainsXlsx:api-catalog/domains.xlsx}` (convert with load_domains.py if newer than domains.json).
- Produce the four artifacts (enriched OpenAPI, domains & capabilities, entities & attributes, duplicates report).
- Loop on `validation.json` until pass; put every judgement in `decisions.yaml` with a note.
- End with the proposed changes to the domain Excel (new keywords / capabilities / domains) as a list.
