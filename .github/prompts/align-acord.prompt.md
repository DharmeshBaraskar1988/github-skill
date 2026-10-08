---
description: Align a region (or one application) with ACORD and prepare the HTML/Excel review
agent: acord-alignment
---
Run the ACORD alignment for region ${input:region:EU}${input:apps: (applications: all)}.

- Region config: `api-catalog/regions/${input:region:EU}.yaml`; ACORD export: ${input:acordExport:api-catalog/reference/acord-export.xlsx}.
- Loop on validation until it passes; resolve ambiguous matches with notes in alignment-overrides.yaml.
- Do not approve anything. Finish with alignment % per domain and application and how to review the HTML/Excel.
