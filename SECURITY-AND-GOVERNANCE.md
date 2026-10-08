# Security and governance

How the API Catalogue keeps secrets, personal data and client data out of the LLM, the artifacts and chat, and how
changes and approvals are controlled. Rules for the agents are in
`.github/instructions/api-catalog-security.instructions.md` (applies to every file and every agent).

Related: [HOW-TO-RUN.md](HOW-TO-RUN.md) · [HOW-IT-WORKS.md](HOW-IT-WORKS.md)

---

## 1. Principles

1. **Scripts read the code, the LLM reads results.** Deterministic Python parses C#; the agent sees summaries,
   validation findings and only the `file:line` locations those findings point to.
2. **Sensitive data never travels.** Credentials, e-mail addresses, URLs, hosts, personal data and client names are
   not written, quoted or sent - by the agent, the scripts, the HTML/Excel views or CI.
3. **Defence in depth.** Each rule is enforced in several places (scanner, redaction, validators, hooks, CI,
   instructions), so one missing layer does not open a hole.
4. **Humans decide.** Approvals and releases come only from named people; the agent prepares, never decides.
5. **Everything is a file in git.** Corrections, decisions, approvals and releases are reviewed in pull requests.

---

## 2. What counts as sensitive data

| Category | Detected | Examples | Allowed instead |
|---|---|---|---|
| Credentials | key/password assignments, DB / storage / service-bus connection strings, JWTs, bearer/basic auth values, private keys, cloud and source-control tokens, keys in query strings, `user:pass@` in URLs | `AccountKey=…`, `eyJ…`, `ghp_…` | nothing - never needed |
| E-mail addresses | every address, no exceptions | `team@company.com` | team or role name |
| URLs | every URL except a template-variable host (`https://{host}`), reserved example hosts (`*.example`, `*.test`, `*.invalid`, `example.com`) and technical namespaces (w3.org, json-schema.org, spec.openapis.org …) | `https://claims.prod.company.com/api` | `https://{host}` |
| Hosts | internal host names (`*.internal`, `*.corp`, `*.local`, `*.lan`, `*.intranet` …) and IPv4 addresses | `sql01.corp`, `10.20.30.40` | server variables |
| Personal data (PII) | phone numbers (+country code), payment card numbers (Luhn-checked), IBANs (checksum), US SSN, UK NINO, India PAN / Aadhaar | `+44 20 …`, `4111 …` | obviously fake values (`CLM-2026-000123`) |
| Client data | names and terms you list in `sensitive-data.yaml` (clear text or SHA-256 hashes), plus your own regex patterns (e.g. real policy-number formats) | client, partner, broker names | "a client", "policy number" |

Not machine-detectable (covered by instructions and PR review): personal names of customers/claimants, postal
addresses, dates of birth, free-text descriptions of real cases.

### Configuring client names - `api-catalog/reference/sensitive-data.yaml`

Owned by the catalogue owners, not by the agent (the hooks block the agent from reading it).

```bash
python .github/skills/api-discovery/scripts/sensitive_scan.py --hash "Acme Insurance"
# -> 64-char hash; add it under blockedTermHashes
```

```yaml
blockedTermHashes: [<hash>, <hash>]   # preferred: the file does not reveal the names
blockedTerms: []                       # clear text, only if the repo is restricted enough
allowedTerms: []                       # false positives to ignore
allowedUrlHosts: []                    # extra hosts allowed in URLs (e.g. an ACORD namespace)
extraPatterns:                         # your own formats of real data
  - {regex: "\\bPOL-\\d{8}\\b", label: "real policy number", category: pii}
```

---

## 3. Layers of protection

| # | Layer | Where | What it does | Enforced by code? |
|---|---|---|---|---|
| 1 | Scanner skip list | `api-discovery/scripts/cs_parser.py` | never opens config/secret files; reads `*.cs`, `*.csproj`, `host.json` route prefix only | Yes |
| 2 | Redaction before writing | `sensitive_scan.py` used by `scan_dotnet`, `build_openapi`, `analyze`, `build_regional_view`, `spec_viewer`, `align`, `load_reference`, `import_review`, `build_canonical`, `merge_global` | replaces values with `[REDACTED-EMAIL]`, `[REDACTED-URL]`, `[REDACTED-CREDENTIAL]`, `[REDACTED-HOST]`, `[REDACTED-PII]`, `[REDACTED-CLIENT]` in every artifact, including `inventory.json` the agent reads | Yes |
| 3 | Validators | every stage | sensitive data in outputs **or in agent-written files** is an error: D09, A10, R08, AL09, C09, G06; D14 warns that source code contained some | Yes |
| 4 | `preToolUse` hook | `.github/hooks/scripts/guard_tools.py` | denies secret files and `sensitive-data.yaml`; during catalogue work denies web/fetch/browser tools, `curl`/`wget`/`ssh`/`scp`/mail/HTTP-client commands, and any write containing sensitive data; denies hand edits of generated files and approvals | Yes - Copilot CLI and cloud agent |
| 5 | `agentStop` hook | `.github/hooks/scripts/stop_gate.py` | the agent cannot finish while validation fails; after the limit it must report failure | Yes - Copilot CLI and cloud agent |
| 6 | CI | `.github/workflows/api-catalog.yml` | re-runs every stage and validator, re-scans all committed catalogue files, read-only token, artifact upload excludes `sensitive-data.yaml` and ACORD files, 14-day retention | Yes - on every PR |
| 7 | Instructions | `copilot-instructions.md`, `instructions/api-catalog-security.instructions.md`, each `SKILL.md`, each agent | the rules in words; covers what code cannot detect | No - model follows them |
| 8 | Copilot content exclusion | GitHub org/repo settings | stops Copilot from reading secret files in the IDE | Yes - you configure it (section 7) |

Findings never contain the value: validators, hooks and CI report only category, label, length, file and line.

---

## 4. What the LLM sees

| Sees | Does not see |
|---|---|
| `inventory.json`, specs, analysis/alignment JSON - all already redacted | config/secret files, `sensitive-data.yaml` |
| validation findings (code, `file:line`, fix hint) | raw values of anything redacted |
| the C# files a finding points to, and the types they use | the rest of the repository (agents are told to read narrowly) |
| domain Excel (as JSON), ACORD model (redacted JSON) | the web - no web tools |

Remaining risk: when the agent opens a C# file at `file:line`, comments or constants in it reach the model's context.
The instructions forbid repeating them, and every write is checked by the hook (CLI/cloud agent) and validators (all
surfaces). Keep real data out of source comments and test data - D14 tells you where it was found.

---

## 5. Governance of changes

| Rule | How |
|---|---|
| Generated files are never hand-edited | hook denies it; outputs change only through the correction files below and a re-run |
| Every correction carries evidence | `overrides.yaml` (discovery), `decisions.yaml` (analysis), `alignment-overrides.yaml` (alignment) - each entry has a `note` with `file:line`, operationId or schema |
| Style examples are a reference only | D13 fails when paths, schemas or long texts are copied |
| Domain catalogue changes go through the Excel | `load_domains.py`, then re-run analysis; the agent only proposes changes |
| Every stage is validated | loop until `validation.json` = pass or `maxIterations`; a failing stage is reported as failed |

## 6. Governance of approvals and releases

| Rule | How |
|---|---|
| Only named reviewers approve | decisions are made in `acord-alignment.html` / `.xlsx`; `import_review.py` is the only writer of `approvals.yaml` |
| Audit trail per decision | reviewer, timestamp, source file and a **basis fingerprint** of the row the reviewer saw |
| Changed data is re-reviewed | if a row's basis changes, its approval becomes "changed" (AL11) |
| Reviewer fields are clean | `import_review.py` strips e-mails and other sensitive values from reviewer and comment fields - use names, not e-mail addresses |
| Agent never approves | instructions + hook; "approve all" is a reviewer's button and is recorded under their name |
| Releases are immutable | `canonical/<REGION>/releases/<v>/` frozen; C13 fails if a release differs; hook blocks edits |
| Releasing and switching baselines need you | the orchestrator asks; it never releases on its own |
| Breaking changes are visible | C11 fails a breaking change against a release; `CHANGELOG.md` per version |
| Only approved, released regions enter the global model | G01; type conflicts between regions fail (G02) |

Who owns what (suggested):

| Role | Owns |
|---|---|
| Application team | `api-catalog.config.yaml`, PR review of discovery/analysis corrections |
| Catalogue owner | `domains.xlsx`, `regions/*.yaml`, `sensitive-data.yaml`, release decisions |
| Reviewers (domain / architecture) | decisions in the alignment HTML/Excel |
| Platform / security | hooks, CI, Copilot content exclusion, branch protection |

---

## 7. Settings to apply outside the kit

1. **Copilot content exclusion** (organisation or repository settings → Copilot). Add the secret-file patterns,
   for example:
   ```yaml
   - "**/appsettings*.json"
   - "**/local.settings.json"
   - "**/secrets.json"
   - "**/.env*"
   - "**/*.pfx"
   - "**/*.pem"
   - "**/*.key"
   - "**/*.pubxml"
   - "**/launchSettings.json"
   - "**/web.config"
   - "/api-catalog/reference/sensitive-data.yaml"
   ```
   Check GitHub's documentation for which Copilot features honour content exclusion in your plan.
2. **Branch protection** on the default branch: required PR review, the `api-catalog` workflow as a required check,
   CODEOWNERS for `api-catalog/alignment/**/approvals.yaml`, `api-catalog/canonical/**/releases/**`,
   `api-catalog/reference/**` and `.github/**`.
3. **Secret scanning and push protection** enabled for the repository (GitHub Advanced Security), as a backstop for
   anything committed outside the catalogue.
4. **Licensed ACORD files**: keep the repository private; the CI artifact upload already excludes them.

---

## 8. Limits

- Hooks run in Copilot CLI and the Copilot cloud agent. In VS Code / Visual Studio chat the protection is the scanner,
  redaction, validators, instructions, content exclusion and CI.
- Detection is pattern-based: it catches formats, not meaning. Customer names, addresses and dates of birth in free
  text are not detectable - PR review is the final check.
- If a hook script itself crashes it allows the call (so the agent is not locked out); redaction, validators and CI
  still apply.
- The URL rule is strict: every real URL is removed from artifacts. Add a host to `allowedUrlHosts` only after the
  catalogue owner agrees it is not sensitive.

## 9. Checking it

```bash
bash tests/run_security_tests.sh     # redaction, validator errors, hook denials, scanner copies identical
bash tests/run_e2e.sh                # full pipeline still passes
python .github/skills/api-discovery/scripts/sensitive_scan.py --scan api-catalog   # ad-hoc scan, exit 1 on findings
```
