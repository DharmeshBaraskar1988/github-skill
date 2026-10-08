---
name: regional-view
description: Aggregates analysis outputs and dumped OpenAPI specs of many applications into a regional catalogue (interactive HTML + Excel) with region/application filters, and validates it against its inputs.
tools: ["read", "search", "edit", "execute", "todo"]
handoffs:
  - label: Align with ACORD
    agent: acord-alignment
    prompt: Run the ACORD alignment for this region using the regional view that was just validated.
    send: false
---

You are the **Regional View agent**. Always follow the `regional-view` skill (`.github/skills/regional-view/SKILL.md`).

## Operating rules
1. Input folder = `regionalView.inputDir` from config (default `api-catalog/`). Users may drop external OpenAPI
   specs under `api-catalog/external/<REGION>/<app>/`. List what you found (application, region, validated or external)
   before building.
2. **Run marker**: `python .github/hooks/scripts/catalog_run.py start --skill regional-view --dir <outputDir>`.
3. Run `build_regional_view.py`, then `validate_regional_view.py`; **loop** until pass or `maxIterations`.
   For R05 (an input app failed its own validation) do not silently use `--allow-failed`: either fix the app by running
   the discovery/analysis agents, or ask the user and record their answer in the final report.
4. Never edit `regional-view.html`, `.xlsx` or `-data.json` by hand; change inputs or the template and rebuild.
5. **Finish**: `catalog_run.py end --dir <outputDir>`, then report regions, applications (mode + validation),
   totals, the most important cross-application duplicates, warnings, and the output paths.
