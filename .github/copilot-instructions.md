# Repository instructions - API catalogue

This repository carries the **API catalogue** tooling for our .NET insurance applications (claims, policy, quote, ...).
It turns source code into validated OpenAPI specs, maps them to the business domain catalogue, and publishes a
regional view.

## Pipeline
| Stage | Agent | Skill | Output |
|---|---|---|---|
| 1 Discovery | `api-discovery` | `.github/skills/api-discovery` | `api-catalog/discovery/<REGION>/<app>/openapi.yaml` |
| 2 Analysis | `api-analysis` | `.github/skills/api-analysis` | `api-catalog/analysis/<REGION>/<app>/1..4-*` |
| 3 Regional view | `regional-view` | `.github/skills/regional-view` | `api-catalog/regional-view/regional-view.html/.xlsx` |
| 4 ACORD alignment | `acord-alignment` | `.github/skills/acord-alignment` | `api-catalog/alignment/<REGION>/acord-alignment.html/.xlsx` |
| 5 Human review | people | HTML / Excel → `import_review.py` | `api-catalog/alignment/<REGION>/approvals.yaml` |
| 6 Canonical model | `canonical-model` | `.github/skills/canonical-model` | `api-catalog/canonical/<REGION>/canonical-openapi.yaml`, `canonical-model.json` |
| 7 Global canonical | `canonical-model` | `merge_global.py` | `api-catalog/canonical/GLOBAL/global-canonical.html`, `global-canonical-openapi.yaml` |
| all | `api-catalog` (orchestrator) | – | runs 1→7 with gates; UK etc. use the released EU canonical as baseline |

Prompts: `/discover-apis`, `/analyze-apis`, `/build-regional-view`, `/align-acord`, `/import-review`, `/build-canonical`, `/build-global-canonical`, `/run-api-catalog`.
Style examples (`api-catalog/style-examples/`) are a reference for conventions only - never copy their paths, schemas or texts.

## Always
- Scripts produce artifacts; agents fix gaps via `overrides.yaml` (discovery) and `decisions.yaml` (analysis) only.
  Never hand-edit generated files (`openapi.yaml`, `inventory.json`, `1-openapi.enriched.yaml`, `2-/3-/4-*`, `regional-view*`).
- Every stage ends with its validator and loops until `validation.json` is `pass` (limit `maxIterations` in config).
  A failing stage is reported as failing - never as done.
- **Approvals are human-only.** Agents never write `approvals.yaml`, never fill review decision columns, never create
  review exports, never bulk-approve. They may run `import_review.py` on files reviewers provide.
- ACORD material is licensed: keep it inside the repository, never send it to web tools or other services.
- Python 3.10+, dependencies in `.github/skills/requirements.txt`. Commands run from the repository root.

## Security
- Do not open or quote `appsettings*.json`, `local.settings.json`, `secrets.json`, `.env*`, certificates/keys,
  publish profiles, `launchSettings.json`, `web.config`. They are not needed for API discovery.
- No real host names, connection strings, keys, tokens or personal data in any artifact. Servers are placeholders.
- No web tools on source code or artifacts.
