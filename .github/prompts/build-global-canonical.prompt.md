---
description: Merge all released regional canonical models into one global canonical model and OpenAPI spec with region/API filters
agent: canonical-model
---
Merge the released canonical models of all regions into the global canonical model (`merge_global.py --catalog api-catalog`),
validate it (`validate_global.py`), loop until it passes, and report regions/versions included, ACORD vs custom entity
counts, endpoints, conflicts and the path of `canonical/GLOBAL/global-canonical.html`.
