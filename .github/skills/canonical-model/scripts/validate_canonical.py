#!/usr/bin/env python3
"""
Validate a canonical model build. Writes validation.json; exit 1 on errors.

  C01  review incomplete: pending / changed items (error; warning when canonical.allowPending)
  C02  unresolved references (attribute or endpoint points to an entity that is not approved)
  C03  canonical OpenAPI invalid or a $ref does not resolve
  C04  conflicting attribute types merged into one canonical attribute; duplicate operationIds / paths
  C05  endpoint uses a rejected entity and was not excluded
  C06  baseline not preserved (baseline entity/attribute removed or retyped)
  C07  lineage incomplete (a source attribute of an approved entity has no mapping row; canonical attribute with no source)
  C08  approvals file missing, hand-edited (no import history) or refers to rows that no longer exist
  C09  sensitive data (credentials, e-mails, URLs, hosts, PII, client names) in outputs
  C10  descriptions missing (warning)
  C11  breaking change against the previous build without a version bump
  C12  model is stale (alignment.json regenerated after this build)
  C13  status is 'draft' but a release exists for this version / outputs missing
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml



def walk_refs(node, acc):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str):
                acc.append(v)
            else:
                walk_refs(v, acc)
    elif isinstance(node, list):
        for v in node:
            walk_refs(v, acc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--iteration", type=int, default=0)
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config, encoding="utf-8")) or {}
    base = Path(a.config).resolve().parent
    ccfg = cfg.get("canonical", {}) or {}
    out = (base / (ccfg.get("outputDir") or f"../canonical/{cfg['region']}")).resolve()
    errors, warnings = [], []

    def err(code, msg, fix, **kw):
        errors.append(dict(code=code, message=msg, fix=fix, **kw))

    def warn(code, msg, fix="", **kw):
        warnings.append(dict(code=code, message=msg, fix=fix, **kw))

    for f in ("canonical-model.json", "canonical-model.yaml", "canonical-openapi.yaml", "canonical-openapi.json",
              "source-to-canonical-mapping.json", "canonical-model.xlsx", "canonical-model.md", "CHANGELOG.md", "canonical-viewer.html"):
        if not (out / f).exists():
            err("C13", f"{f} missing", "Run build_canonical.py")
    if errors:
        return finish(out, a, errors, warnings, {})
    model = json.loads((out / "canonical-model.json").read_text(encoding="utf-8"))
    spec = yaml.safe_load((out / "canonical-openapi.yaml").read_text(encoding="utf-8"))
    al_p = (out / model["inputs"]["alignment"]).resolve()
    al = json.loads(al_p.read_text(encoding="utf-8"))

    # C01
    if model["pending"]:
        items = ", ".join(f"{p.get('entity') or p.get('endpoint')} ({p['state']})" for p in model["pending"][:12])
        (warn if ccfg.get("allowPending") else err)(
            "C01", f"{len(model['pending'])} items not approved: {items}",
            "Reviewers decide them in acord-alignment.html / .xlsx, then import_review.py, align.py, build_canonical.py. "
            "Agents must not approve on their behalf.")
    # C02 / C04 / C05 from build problems
    for p in model.get("problems", []):
        err(p["code"], p["message"], p["fix"])
    ids, paths = {}, {}
    for ep in model["endpoints"]:
        if ep["operationId"] in ids:
            err("C04", f"Duplicate operationId {ep['operationId']}", "Set Canonical operationId in review")
        ids[ep["operationId"]] = 1
        k = (ep["method"], ep["path"])
        if k in paths:
            err("C04", f"Duplicate endpoint {k}", "Set different canonical paths in review")
        paths[k] = 1
        if ep.get("variants"):
            warn("C04", f"{ep['method']} {ep['path']} merges {len(ep['sources'])} source operations with different contracts "
                        f"({', '.join(v['source'] for v in ep['variants'])}) - the first one is used", "Confirm in review or give them separate canonical paths")
    # C03
    refs = []
    walk_refs(spec, refs)
    for r in sorted(set(refs)):
        name = r.split("/")[-1]
        if name not in spec.get("components", {}).get("schemas", {}):
            err("C03", f"Unresolved $ref {r}", "An approved entity references a missing one - see C02")
    try:
        from openapi_spec_validator import validate as osv  # type: ignore
        try:
            osv(spec)
        except Exception as ex:  # noqa: BLE001
            err("C03", f"canonical-openapi.yaml invalid: {str(ex).splitlines()[0][:300]}", "Fix the cause (review decisions) and rebuild")
    except ImportError:
        warn("C03", "openapi-spec-validator not installed", "pip install openapi-spec-validator")
    # C06
    cb = model.get("changesVsBaseline")
    if cb and cb.get("breaking"):
        err("C06", f"Baseline not preserved: removed {cb['removedEntities'] + cb['removedAttributes']}, changed {cb['changedAttributes']}",
            "A region extends its baseline; it never removes or retypes baseline items. Change the baseline region instead.")
    # C07
    for e in al["entities"]:
        if any(x["entity"] == e["name"] for x in model["rejected"]) or any(p.get("entity") == e["name"] for p in model["pending"]):
            continue
        for at in e["attributes"]:
            for s in at["sources"]:
                if not any(r["regionalEntity"] == e["name"] and r["regionalAttribute"] == at["name"] and r["appId"] == s["appId"]
                           for r in model["lineage"]):
                    err("C07", f"No mapping row for {s['appId']}:{e['name']}.{at['name']}", "Rebuild; report a bug if it persists")
    for e in model["entities"]:
        if e["status"].startswith("baseline") or e["kind"] == "enum":
            continue
        for at in e["attributes"]:
            if not at.get("sources") and not at.get("referenceOnly") and at.get("introducedIn") == model["region"]:
                warn("C07", f"{e['name']}.{at['name']} has no source attribute", "Expected only for reference-only attributes")
    # C08
    ap_p = al_p.parent / "approvals.yaml"
    if not ap_p.exists():
        err("C08", "approvals.yaml missing - nothing has been reviewed", "Reviewers decide in the HTML/Excel; run import_review.py")
    else:
        apv = yaml.safe_load(ap_p.read_text(encoding="utf-8")) or {}
        if not apv.get("history"):
            err("C08", "approvals.yaml has no import history - it was not written by import_review.py",
                "Delete it and re-import the reviewed Excel/JSON with import_review.py")
        if al["review"].get("staleKeys"):
            warn("C08", f"Approvals for rows that no longer exist: {al['review']['staleKeys'][:6]}", "Re-review the renamed/merged entities")
    # C13b - YAML and JSON forms must carry the same content
    if yaml.safe_load((out / "canonical-model.yaml").read_text(encoding="utf-8")) != model:
        err("C13", "canonical-model.yaml differs from canonical-model.json", "Re-run build_canonical.py (never edit either by hand)")
    if json.loads((out / "canonical-openapi.json").read_text(encoding="utf-8")) != spec:
        err("C13", "canonical-openapi.json differs from canonical-openapi.yaml", "Re-run build_canonical.py")
    # C09
    from sensitive_scan import check_files, find_policy_file, load_policy, report
    report(check_files([out / f for f in ("canonical-model.json", "canonical-openapi.yaml", "canonical-model.md",
                                           "CHANGELOG.md", "source-to-canonical-mapping.json", "canonical-viewer.html")],
                       load_policy(find_policy_file(out))), err, "C09", "Remove it at the source (overrides/decisions/config/comments) and rebuild; never write e-mails, URLs, hosts, keys, personal or client data into catalogue files")
    # C10
    nd_e = [e["name"] for e in model["entities"] if not e.get("description")]
    nd_a = sum(1 for e in model["entities"] for x in e["attributes"] if not x.get("description"))
    if nd_e or nd_a:
        warn("C10", f"{len(nd_e)} entities and {nd_a} attributes without description" + (f": {', '.join(nd_e[:10])}" if nd_e else ""),
             "Add descriptions at source (analysis decisions.yaml descriptions) or in the reference model")
    # C11
    ch = model.get("changes") or {}
    rel = out / "releases"
    if ch.get("breaking"):
        if (rel / model["version"]).exists():
            err("C11", f"Breaking change vs previous build but version {model['version']} is already released", "Bump canonical.version")
        else:
            warn("C11", f"Breaking change vs previous build: removed {ch['removedEntities'] + ch['removedAttributes']}, "
                        f"changed {ch['changedAttributes']}", "Bump the major version before releasing")
    # C12
    if al["meta"]["generatedAt"] != model["inputs"]["alignmentGeneratedAt"]:
        err("C12", "alignment.json was regenerated after this canonical build", "Re-run build_canonical.py")
    # C13
    if (rel / model["version"]).exists():
        r_model = json.loads((rel / model["version"] / "canonical-model.json").read_text(encoding="utf-8"))
        if json.dumps(r_model["entities"], sort_keys=True) != json.dumps(model["entities"], sort_keys=True):
            err("C13", f"Version {model['version']} is released but the current build differs from the release",
                "Bump canonical.version (a release is immutable)")
    finish(out, a, errors, warnings, model)


def finish(out, a, errors, warnings, model):
    status = "pass" if not errors else "fail"
    rep = {"skill": "canonical-model", "status": status, "iteration": a.iteration,
           "modelStatus": model.get("status"), "version": model.get("version"), "summary": model.get("summary"),
           "errors": errors, "warnings": warnings}
    (out / "validation.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(json.dumps({"status": status, "modelStatus": model.get("status"), "errors": len(errors), "warnings": len(warnings),
                      "firstErrors": [e["code"] + " " + e["message"] for e in errors[:10]],
                      "warningsList": [w["code"] + " " + w["message"][:140] for w in warnings[:8]]}, indent=2))
    sys.exit(0 if status == "pass" else 1)


if __name__ == "__main__":
    main()
