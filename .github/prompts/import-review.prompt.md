---
description: Import reviewers' decisions (HTML export or Excel) into approvals.yaml
agent: acord-alignment
---
Import the review decisions in ${input:files:review-decisions.json} for region ${input:region:EU}
with `import_review.py`, then re-run `align.py` and report applied decisions, conflicts, problems and what is still pending.
Do not change any decision.
