---
description: Run the full API catalogue pipeline (discovery -> analysis -> regional view -> ACORD alignment -> review -> canonical)
agent: api-catalog
---
Run the API catalogue pipeline for: ${input:configs:api-catalog.config.yaml} (application configs, comma separated)
and region(s) ${input:regions:EU}.

Stage gates: discovery -> analysis -> regional view -> ACORD alignment -> human review (stop and tell me what to review)
-> canonical model. Finish with the stage status table, output paths, open warnings and pending review items.
