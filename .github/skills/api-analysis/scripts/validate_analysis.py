#!/usr/bin/env python3
"""
Validate the four analysis artifacts. Writes validation.json; exit 1 on errors.
The agent loops: fix decisions.yaml (or the domain Excel) -> analyze.py -> validate.

  A01  every operation of the discovery spec appears in 2-domains-capabilities (none lost)
  A02  no operation left 'unclassified' without an acceptedUnclassified decision
  A03  every domain used exists in the domain catalogue
  A04  low-confidence keyword assignments (warning; error when analysis.strictDomains)
  A05  proposed capabilities not in the catalogue (warning; list to add to the Excel)
  A06  every schema is an entity, merged into one, or excluded with a reason
  A07  no undecided near-duplicate groups
  A08  relations point to existing entities; canonical names unique
  A09  enriched spec is valid OpenAPI, refs resolve, same operation count as discovery
  A10  no sensitive data (credentials, e-mails, URLs, hosts, PII, client names) in any artifact or decisions.yaml
  A11  description coverage (warning; error when analysis.requireDescriptions)
  A12  decisions.yaml has no stale references
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
    ap.add_argument("--dir", required=True, help="analysis output folder")
    ap.add_argument("--spec", required=True, help="discovery openapi.yaml")
    ap.add_argument("--domains", required=True, help="domains.json")
    ap.add_argument("--config")
    ap.add_argument("--iteration", type=int, default=0)
    a = ap.parse_args()
    d = Path(a.dir)
    cfg = (yaml.safe_load(open(a.config, encoding="utf-8")) or {}) if a.config else {}
    acfg = cfg.get("analysis", {}) or {}
    errors, warnings = [], []

    def err(code, msg, fix, **kw):
        errors.append(dict(code=code, message=msg, fix=fix, **kw))

    def warn(code, msg, fix="", **kw):
        warnings.append(dict(code=code, message=msg, fix=fix, **kw))

    spec = yaml.safe_load(Path(a.spec).read_text(encoding="utf-8"))
    domains = json.loads(Path(a.domains).read_text(encoding="utf-8"))
    cat = {x["name"] for x in domains["domains"]}
    enr_text = (d / "1-openapi.enriched.yaml").read_text(encoding="utf-8")
    enr = yaml.safe_load(enr_text)
    dc = json.loads((d / "2-domains-capabilities.json").read_text(encoding="utf-8"))
    ea = json.loads((d / "3-entities-attributes.json").read_text(encoding="utf-8"))
    du = json.loads((d / "4-duplicates-report.json").read_text(encoding="utf-8"))
    summ = json.loads((d / "analysis-summary.json").read_text(encoding="utf-8"))

    spec_ops = {op.get("operationId") for p, it in spec.get("paths", {}).items() for m, op in it.items()}
    enr_ops = {op.get("operationId") for p, it in enr.get("paths", {}).items() for m, op in it.items()}
    dc_ops = {o["operationId"] for o in dc["operations"]}
    dc_ops_in_caps = {op["operationId"] for dd in dc["domains"] for c in dd["capabilities"] for op in c["operations"]}

    # A01
    for oid in sorted(spec_ops - (dc_ops_in_caps & dc_ops)):
        err("A01", f"Operation {oid} missing from 2-domains-capabilities", "Re-run analyze.py; report a bug if it persists")
    # A02 / A04
    for o in dc["operations"]:
        if o["assignment"] == "unclassified":
            err("A02", f"{o['method']} {o['path']} ({o['operationId']}) is unclassified (scores: {o.get('scores') or 'none'})",
                "Add the right keywords to the domain Excel, or set decisions.yaml domainAssignments / acceptedUnclassified",
                operationId=o["operationId"])
        if o.get("confidence") == "low":
            (err if acfg.get("strictDomains") else warn)(
                "A04", f"{o['operationId']} -> {o['domain']} has low confidence (scores {o.get('scores')})",
                "Confirm in decisions.yaml domainAssignments (with a note) or improve Excel keywords",
                operationId=o["operationId"])
    # A03
    for dd in dc["domains"]:
        if dd["domain"] != "Unclassified" and dd["domain"] not in cat:
            err("A03", f"Domain '{dd['domain']}' is not in the domain catalogue",
                "Use a catalogue domain in decisions.yaml or add the domain to the Excel")
    # A05
    proposed = [(dd["domain"], c["name"]) for dd in dc["domains"] for c in dd["capabilities"] if c["status"] == "proposed"]
    if proposed:
        (err if acfg.get("strictCapabilities") else warn)(
            "A05", f"{len(proposed)} capabilities are not in the catalogue: " +
            "; ".join(f"{dn}: {cn}" for dn, cn in proposed[:25]),
            "Map to an existing capability via decisions.yaml domainAssignments.capability, or add them to the Excel")

    # A06
    schemas = set(spec.get("components", {}).get("schemas", {}))
    covered = set()
    for e in ea["entities"]:
        covered |= set(e["schemaNames"])
    covered |= {x["schema"] for x in ea.get("excludedSchemas", [])}
    for s in sorted(schemas - covered):
        err("A06", f"Schema {s} is not represented in entities or excludedSchemas", "Re-run analyze.py; report a bug")

    # A07
    for g in du["groups"]:
        if g["decision"] == "undecided":
            err("A07", f"Possible duplicate {' / '.join(g['members'])} (similarity {g['similarity']}, shared: "
                       f"{', '.join(g.get('sharedAttributes', [])[:8])}) needs a decision",
                "Compare the source classes, then add to decisions.yaml duplicates: members, decision: merge|keep-separate, canonical, note",
                members=g["members"])

    # A08
    names = [e["name"] for e in ea["entities"]]
    for n in {x for x in names if names.count(x) > 1}:
        err("A08", f"Entity name '{n}' is not unique", "Set decisions.yaml entityNames or a different canonical")
    for r in ea["relations"]:
        if r["to"] not in names or r["from"] not in names:
            err("A08", f"Relation {r['from']} -> {r['to']} points to a missing entity", "Re-run analyze.py")

    # A09
    try:
        from openapi_spec_validator import validate as osv  # type: ignore
        try:
            osv(enr)
        except Exception as ex:  # noqa: BLE001
            err("A09", f"Enriched spec invalid: {str(ex).splitlines()[0][:300]}", "Check decisions.yaml descriptions/types")
    except ImportError:
        warn("A09", "openapi-spec-validator not installed; structural check skipped", "pip install openapi-spec-validator")
    if spec_ops != enr_ops:
        err("A09", f"Enriched spec operations differ from discovery ({len(enr_ops)} vs {len(spec_ops)})", "Re-run analyze.py")

    # A10
    from sensitive_scan import check_files, find_policy_file, load_policy, report
    _pol = load_policy(find_policy_file(d))
    report(check_files(sorted(p for p in d.iterdir() if p.suffix in (".json", ".yaml", ".md") and p.name != "validation.json"), _pol),
           err, "A10", "Remove it at the source (overrides/decisions/config/comments) and rebuild; never write e-mails, URLs, hosts, keys, personal or client data into catalogue files")

    # A11
    no_desc_e = [e["name"] for e in ea["entities"] if not e["description"]]
    no_desc_a = sum(1 for e in ea["entities"] for x in e["attributes"] if not x["description"])
    if no_desc_e or no_desc_a:
        (err if acfg.get("requireDescriptions") else warn)(
            "A11", f"{len(no_desc_e)} entities and {no_desc_a} attributes lack descriptions"
                   + (f" (entities: {', '.join(no_desc_e[:15])})" if no_desc_e else ""),
            "Write business descriptions in decisions.yaml descriptions: {Entity: ..., Entity.attribute: ...}")

    # A12
    for s in summ.get("staleDecisions", []):
        err("A12", s, "Remove or correct the entry in decisions.yaml")

    status = "pass" if not errors else "fail"
    report = {"skill": "api-analysis", "status": status, "iteration": a.iteration,
              "region": summ["region"], "application": summ["application"],
              "counts": {k: v for k, v in summ.items() if isinstance(v, (int, float))},
              "errors": errors, "warnings": warnings}
    (d / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": status, "errors": len(errors), "warnings": len(warnings),
                      "firstErrors": [e["code"] + " " + e["message"] for e in errors[:12]]}, indent=2))
    sys.exit(0 if status == "pass" else 1)


if __name__ == "__main__":
    main()
