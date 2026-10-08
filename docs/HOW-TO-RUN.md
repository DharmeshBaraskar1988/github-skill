# How to run the API Catalogue

Everything runs inside **GitHub Copilot** (agent mode in VS Code / Visual Studio, Copilot CLI, or the Copilot cloud
agent). You start a stage with a slash command or by picking an agent and describing the task. The agent runs the
skill's Python scripts, loops on validation until it passes, and stops at the human review.

Related: [HOW-IT-WORKS.md](HOW-IT-WORKS.md) (artifacts and waits) · [SECURITY-AND-GOVERNANCE.md](SECURITY-AND-GOVERNANCE.md)
· [flow-diagram.html](flow-diagram.html)

---

## 1. One-time setup

| Step | What to do |
|---|---|
| 1 | Copy `.github/` from the kit into the repository (see [section 6](#6-which-files-a-repository-needs)). |
| 2 | Install Python 3.10+ and the packages: `pip install -r .github/skills/requirements.txt` |
| 3 | Per application: copy `.github/skills/api-discovery/templates/api-catalog.config.template.yaml` to `api-catalog.config.yaml` and set `region`, `application`, `sourceRoots`. |
| 4 | Domain catalogue: `api-catalog/domains.xlsx` (your capability map, with Domain Keywords / SubCapability Keywords columns). Keep it up to date; see its "How to maintain" sheet. |
| 5 | Per region: create `api-catalog/regions/<REGION>.yaml` (template: `.github/skills/acord-alignment/templates/region.config.template.yaml`). |
| 6 | Put your licensed ACORD files in `api-catalog/reference/acord/`. |
| 7 | Catalogue owners: fill `api-catalog/reference/sensitive-data.yaml` with client names (as hashes). See the security guide. |
| 8 | Optional: your own example specs in `api-catalog/style-examples/_global/` (replace the invented one). |
| 9 | Organisation admins: add the secret-file patterns to **Copilot content exclusion** (security guide, section 7). |

---

## 2. Run everything

In Copilot Chat, agent mode:

```
/run-api-catalog
```

It asks for:

| Input | Example | Meaning |
|---|---|---|
| `configs` | `api-catalog.config.yaml` or `api-catalog/configs/claims.yaml,api-catalog/configs/policy.yaml` | applications to process |
| `regions` | `EU,UK` | regions to align and build |
| `startAt` | `1 discovery` / `3 regional view` / `6 canonical` | first stage to run (earlier outputs are reused) |

Or pick the **api-catalog** agent and write it in words:

> Run the API catalogue for EU and UK, starting at the regional view.

The orchestrator runs the stages in order, each with its validation loop, and **stops at stage 5 (human review)**
with the list of what to review. After reviewers have exported their decisions, ask it to continue:

> Reviews for EU are in `review-decisions.json`. Import them and continue from the canonical model.

It never approves, never releases and never switches a baseline without your explicit "release" / "yes".

---

## 3. Run one stage

| # | Stage | Slash command | Agent | Plain-language example |
|---|---|---|---|---|
| 1 | Discovery | `/discover-apis` | api-discovery | "Discover the APIs of this repository for EU claims" |
| 2 | Analysis | `/analyze-apis` | api-analysis | "Analyse EU claims against the domain Excel" |
| 3 | Regional view | `/build-regional-view` | regional-view | "Build the regional view from api-catalog" |
| 4 | ACORD alignment | `/align-acord` | acord-alignment | "Align region UK, only the claims app" |
| 5 | Import review | `/import-review` | acord-alignment | "Import `reviewed-claims.xlsx` for EU" |
| 6 | Canonical model | `/build-canonical` | canonical-model | "Build the canonical model for EU and release 1.0.0" |
| 7 | Next region | `/align-acord` then `/build-canonical` | acord-alignment, canonical-model | "Align UK on the EU 1.0.0 baseline" |
| 8 | Global canonical | `/build-global-canonical` | canonical-model | "Merge all released regions into the global model" |

**Copilot CLI:** choose the agent with `/agent`, then type the same prompt.

**Without Copilot (CI or a terminal):** every stage is plain Python, for example:

```bash
S=.github/skills/api-discovery/scripts
python $S/scan_dotnet.py --config api-catalog.config.yaml
python $S/build_openapi.py --config api-catalog.config.yaml
python $S/validate_discovery.py --dir api-catalog/discovery/EU/claims --config api-catalog.config.yaml
```

The exact commands per stage are in each `.github/skills/<skill>/SKILL.md`. Without the agent, nobody fixes
validation errors for you - that is the agent's part.

---

## 4. Order, gates and waits

| After | Wait for | Then |
|---|---|---|
| 1 Discovery | `discovery/<REGION>/<app>/validation.json` = pass | 2 Analysis |
| 2 Analysis | `analysis/<REGION>/<app>/validation.json` = pass (all apps of the region) | 3 Regional view |
| 3 Regional view | `regional-view/validation.json` = pass | 4 Alignment per region |
| 4 Alignment | `alignment/<REGION>/validation.json` = pass | **5 Human review** |
| 5 Review | reviewers decide in `acord-alignment.html` / `.xlsx`, then `import_review.py`; no pending / changed rows | 6 Canonical |
| 6 Canonical | `canonical/<REGION>/validation.json` = pass, then your "release" | 7 next region (baseline = this release) |
| 7 All regions released | | 8 Global canonical |

Baseline regions first: build and release EU before UK when UK uses EU as its baseline.

---

## 5. Starting from existing analysis outputs (no source code)

Stages 3-8 need only the analysis outputs, not the .NET code. Place each application's **whole analysis folder**
under its region:

```
api-catalog/
  domains.xlsx
  analysis/
    EU/claims/   analysis-summary.json, 1-openapi.enriched.yaml, 2-domains-capabilities.json,
                 3-entities-attributes.json, 4-duplicates-report.json, validation.json, decisions.yaml
    EU/policy/   (same files)
    UK/claims/   (same files)
  external/UK/quote/openapi.json     optional: bare OpenAPI specs from other teams
  regions/EU.yaml, regions/UK.yaml
  reference/acord/                    licensed ACORD files
```

- Region and application are read from `analysis-summary.json`; keep the folder names matching anyway.
- `validation.json` is optional (missing = "not validated", the run continues; `fail` stops that app).
- Bare specs in `external/<REGION>/<app>/` are analysed on the fly and sensitive values in them are redacted.
- Then: `/run-api-catalog` with `startAt: 3 regional view`.

Source code is still needed to fix a failed analysis, or when the agent must read a C# class to settle an ambiguous
ACORD match (without it, it decides on attributes and says so).

---

## 6. Which files a repository needs

| Setup | Skills (`.github/skills/`) | Agents (`.github/agents/`) |
|---|---|---|
| Application repo (stages 1-2) | api-discovery, api-analysis | api-discovery, api-analysis |
| Central catalogue repo (stages 3-8, plus 1-2 for checked-out apps) | all 5 | all 6 |

Always with them: `.github/skills/requirements.txt`, `.github/copilot-instructions.md`,
`.github/instructions/*.instructions.md`. Strongly recommended: `.github/hooks/`, `.github/prompts/`,
`.github/workflows/api-catalog.yml`. Not needed in a repo: `examples/`, `tests/`.

Skills that must ship together: `regional-view` uses `api-analysis` and `canonical-model` scripts;
`canonical-model` uses `acord-alignment` scripts.

---

## 7. Where the outputs are

| Stage | Folder | Open this |
|---|---|---|
| 1 | `api-catalog/discovery/<REGION>/<app>/` | `openapi.yaml`, `discovery-report.md` |
| 2 | `api-catalog/analysis/<REGION>/<app>/` | `1-openapi.enriched.yaml`, `2-…md`, `3-…md`, `4-…md` |
| 3 | `api-catalog/regional-view/` | `regional-view.html`, `regional-view.xlsx`, `spec-viewer.html` |
| 4 | `api-catalog/alignment/<REGION>/` | `acord-alignment.html`, `acord-alignment.xlsx` |
| 6 | `api-catalog/canonical/<REGION>/` (+ `releases/<v>/`) | `canonical-viewer.html`, `canonical-openapi.yaml` |
| 8 | `api-catalog/canonical/GLOBAL/` | `global-canonical.html`, `global-canonical-openapi.yaml` |

---

## 8. Troubleshooting

| Symptom | What to do |
|---|---|
| A stage keeps failing after `maxIterations` | Read `validation.json` (errors have code, file:line and a fix). The agent reports it as failed, never as done. |
| `D09 / A10 / R08 / AL09 / C09 / G06` sensitive data | Remove it at the source (overrides, decisions, config, external spec). Never edit outputs. See the security guide. |
| `D14` warning | Source code contains real e-mails/URLs/keys in comments or defaults; outputs are already redacted. Tell the code owners. |
| Hook says "Blocked by API-catalogue policy" | Expected - the action is not allowed. Follow the reason text (use overrides, placeholders, generic wording). |
| Canonical says reviews pending | Reviewers must finish in the HTML/Excel; then `/import-review`. |
| Wrong baseline for UK | Fix `baseline:` in `api-catalog/regions/UK.yaml` (must point to a `releases/<v>/` folder). |
