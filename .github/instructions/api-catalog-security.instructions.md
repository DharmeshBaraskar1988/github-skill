---
applyTo: "**"
description: Security rules for API catalogue work
---
- Treat `appsettings*.json`, `local.settings.json`, `secrets.json`, `.env*`, `*.pfx`, `*.pem`, `*.key`, `*.pubxml`,
  `*.publishsettings`, `launchSettings.json`, `web.config` as off-limits: do not open, search, quote or summarise them.
- Never write host names, IPs, connection strings, keys, tokens, passwords or customer data into
  `overrides.yaml`, `decisions.yaml`, specs, reports or chat.
- Example values in specs are synthetic and obviously fake (e.g. `CLM-2026-000123`).
