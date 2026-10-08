---
applyTo: "api-catalog/**"
description: How to change API catalogue artifacts
---
- Files under `api-catalog/` are generated. Change them only through:
  - `api-catalog/discovery/<REGION>/<app>/overrides.yaml` → re-run `build_openapi.py` + `validate_discovery.py`
  - `api-catalog/analysis/<REGION>/<app>/decisions.yaml` → re-run `analyze.py` + `validate_analysis.py`
  - the domain Excel (`api-catalog/domains.xlsx`) → `load_domains.py`, then re-run analysis
  - `api-catalog/alignment/<REGION>/alignment-overrides.yaml` → re-run `align.py` + `validate_alignment.py`
  - human decisions only through `import_review.py` (from the review HTML export or Excel) → `approvals.yaml`
  - `api-catalog/regions/<REGION>.yaml` (thresholds, baseline, canonical version) → re-run the stage
- Never edit `approvals.yaml`, `canonical/**` or `canonical/**/releases/**` by hand. Releases are immutable.
- Every override/decision entry needs a `note` (or `reason`) with the evidence (file:line, operationId, schema).
- After any change, run the stage validator and loop until it passes.
- External specs dropped into `api-catalog/external/<REGION>/<app>/` are inputs for the regional view; do not edit them.
