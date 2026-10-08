#!/usr/bin/env python3
"""
Validate the global canonical model. Writes canonical/GLOBAL/validation.json; exit 1 on errors.

  G01  every region input is approved (and released when requireReleased); skipped regions are reported
  G02  conflicts between regions (same entity/attribute with different type / kind) - fix by aligning the later
       region on the earlier region's released canonical as baseline
  G03  global OpenAPI valid, $refs resolve; YAML and JSON forms identical
  G04  completeness: every entity, attribute, code value and endpoint of every region model is in the global model
  G05  operationIds renamed because two regions used the same id for different endpoints (warning)
  G06  sensitive data (credentials, e-mails, URLs, hosts, PII, client names) in outputs
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="api-catalog")
    ap.add_argument("--iteration", type=int, default=0)
    a = ap.parse_args()
    cat = Path(a.catalog).resolve()
    gcfg_p = cat / "global.yaml"
    gcfg = (yaml.safe_load(gcfg_p.read_text(encoding="utf-8")) or {}) if gcfg_p.exists() else {}
    out = (cat / gcfg.get("outputDir", "canonical/GLOBAL")).resolve()
    errors, warnings = [], []
    err = lambda c, m, f: errors.append({"code": c, "message": m, "fix": f})  # noqa: E731
    warn = lambda c, m, f="": warnings.append({"code": c, "message": m, "fix": f})  # noqa: E731
    model = json.loads((out / "global-canonical-model.json").read_text(encoding="utf-8"))
    spec = yaml.safe_load((out / "global-canonical-openapi.yaml").read_text(encoding="utf-8"))
    for r in model["regions"]:
        if r["status"] != "approved":
            err("G01", f"Region {r['region']} v{r['version']} is {r['status']}", "Finish that region's review and canonical build")
        if gcfg.get("requireReleased", True) and not r["released"]:
            err("G01", f"Region {r['region']} v{r['version']} is not a release", "Release it (build_canonical.py --release)")
    for s in model.get("skippedRegions", []):
        warn("G01", f"Region {s['region']} skipped: {s['reason']}", "Release it to include it")
    for c in model["conflicts"]:
        if c["kind"] == "operationId":
            warn("G05", f"operationId {c['item']}: {c['detail']}", "Give the endpoints distinct canonical operationIds in review")
        else:
            err("G02", f"{c['kind']} conflict {c['item']}: {c['detail']}",
                "Regions disagree. Align the later region with the earlier region's release as baseline, re-review, rebuild")
    refs = set(re.findall(r"#/components/schemas/([\w.-]+)", json.dumps(spec)))
    for r in sorted(refs - set(spec["components"]["schemas"])):
        err("G03", f"Unresolved $ref {r}", "Re-run merge_global.py")
    try:
        from openapi_spec_validator import validate as osv  # type: ignore
        try:
            osv(spec)
        except Exception as ex:  # noqa: BLE001
            err("G03", f"global-canonical-openapi.yaml invalid: {str(ex).splitlines()[0][:300]}", "Re-run merge_global.py; check region specs")
    except ImportError:
        warn("G03", "openapi-spec-validator not installed")
    if json.loads((out / "global-canonical-openapi.json").read_text(encoding="utf-8")) != spec:
        err("G03", "global OpenAPI JSON and YAML differ", "Re-run merge_global.py")
    if yaml.safe_load((out / "global-canonical-model.yaml").read_text(encoding="utf-8")) != model:
        err("G03", "global model JSON and YAML differ", "Re-run merge_global.py")
    g_ents = {e["name"]: e for e in model["entities"]}
    g_eps = {(e["method"], e["path"]) for e in model["endpoints"]}
    for r in model["regions"]:
        rm = json.loads((cat / r["file"]).read_text(encoding="utf-8")) if not Path(r["file"]).is_absolute() else json.loads(Path(r["file"]).read_text(encoding="utf-8"))
        for e in rm["entities"]:
            g = g_ents.get(e["name"])
            if not g or r["region"] not in g["availableIn"]:
                err("G04", f"{r['region']}:{e['name']} missing from the global model", "Re-run merge_global.py")
                continue
            names = {a["name"] for a in g["attributes"]}
            for at in e.get("attributes", []):
                if at["name"] not in names:
                    err("G04", f"{r['region']}:{e['name']}.{at['name']} missing", "Re-run merge_global.py")
            for v in e.get("enumValues") or []:
                if v not in g["enumValues"]:
                    err("G04", f"{r['region']}:{e['name']} value {v} missing", "Re-run merge_global.py")
        for ep in rm.get("endpoints", []):
            if (ep["method"], ep["path"]) not in g_eps:
                err("G04", f"{r['region']}: {ep['method']} {ep['path']} missing", "Re-run merge_global.py")
    from sensitive_scan import check_files, find_policy_file, load_policy, report
    report(check_files([out / f for f in ("global-canonical-model.json", "global-canonical-openapi.yaml",
                                           "global-canonical.html", "global-source-mapping.json")],
                       load_policy(find_policy_file(out))), err, "G06", "Remove it at the source (overrides/decisions/config/comments) and rebuild; never write e-mails, URLs, hosts, keys, personal or client data into catalogue files")
    for f in ("global-canonical.html", "global-canonical.xlsx", "global-source-mapping.json"):
        if not (out / f).exists():
            err("G03", f"{f} missing", "Re-run merge_global.py")
    status = "pass" if not errors else "fail"
    (out / "validation.json").write_text(json.dumps({"skill": "canonical-model/global", "status": status, "iteration": a.iteration,
                                                      "summary": model["summary"], "errors": errors, "warnings": warnings}, indent=2), encoding="utf-8")
    print(json.dumps({"status": status, "errors": len(errors), "warnings": len(warnings),
                      "firstErrors": [e["code"] + " " + e["message"] for e in errors[:10]],
                      "warningsList": [w["code"] + " " + w["message"] for w in warnings[:6]]}, indent=2))
    sys.exit(0 if status == "pass" else 1)


if __name__ == "__main__":
    main()
