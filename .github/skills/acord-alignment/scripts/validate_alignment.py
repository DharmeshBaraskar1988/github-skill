#!/usr/bin/env python3
"""
Validate an alignment run. Writes validation.json; exit 1 on errors.
This gate checks the MATCHING (agent work). Human review completeness is reported here and enforced by the
canonical-model skill.

  AL01  a reference model is loaded and has entities
  AL02  the scope is not empty and every in-scope regional entity has an alignment row (none lost)
  AL03  ambiguous best match (two candidates within the ambiguity margin) without an override
  AL04  attribute type conflicts with the matched reference attribute (warning - reviewers decide)
  AL05  alignment-overrides.yaml references unknown entities / references / attributes
  AL06  overrides without a note
  AL07  regional input is stale (regional-view-data.json newer than alignment.json)
  AL08  same attribute typed differently across applications (warning)
  AL09  sensitive data (credentials, e-mails, URLs, hosts, PII, client names) in outputs, overrides or approvals
  AL10  outputs present (html, xlsx, report) and the HTML embeds the data
  AL11  review progress (info: pending / changed approvals) and stale approval keys (warning)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--iteration", type=int, default=0)
    a = ap.parse_args()
    d = Path(a.dir)
    errors, warnings, info = [], [], []

    def err(code, msg, fix, **kw):
        errors.append(dict(code=code, message=msg, fix=fix, **kw))

    def warn(code, msg, fix="", **kw):
        warnings.append(dict(code=code, message=msg, fix=fix, **kw))

    al = json.loads((d / "alignment.json").read_text(encoding="utf-8"))
    meta, ov = al["meta"], al.get("overrides") or {}

    # AL01
    if not al["references"] or not any(r["entities"] for r in al["references"]):
        err("AL01", "No reference entities loaded", "Run load_reference.py on the ACORD export and set reference.json in the region config")

    # AL02
    if not meta["scope"]["appIds"]:
        err("AL02", f"Scope selects no application in region {meta['region']}", "Check --apps / region config")
    data_p = (d / meta["regionalViewData"]).resolve()
    if data_p.exists():
        data = json.loads(data_p.read_text(encoding="utf-8"))
        rows = {m["appId"] + ":" + m["entity"] for e in al["entities"] for m in e["members"]}
        scope = meta["scope"]
        for e in data["entities"]:
            if e["appId"] not in scope["appIds"]:
                continue
            if scope.get("domains") and e.get("domain") not in scope["domains"]:
                continue
            if scope.get("entities"):
                continue
            if f"{e['appId']}:{e['name']}" not in rows:
                err("AL02", f"{e['appId']}:{e['name']} has no alignment row", "Re-run align.py; report a bug if it persists")
        # AL07
        if data_p.stat().st_mtime > (d / "alignment.json").stat().st_mtime + 1:
            err("AL07", "regional-view-data.json is newer than this alignment", "Re-run align.py")
    else:
        err("AL07", f"Regional input {data_p} not found", "Build the regional view first")
    if not al["entities"]:
        err("AL02", "No entities in scope", "Check scope filters (apps / domains / entities)")

    # AL03
    for e in al["entities"]:
        if e["ambiguous"] and not e.get("excluded"):
            c = e["candidates"]
            err("AL03", f"{e['name']}: ambiguous between {c[0]['reference']} ({round(c[0]['score']*100)}%) and "
                        f"{c[1]['reference']} ({round(c[1]['score']*100)}%)",
                "Compare attributes/meaning, then add alignment-overrides.yaml entityMatches.<Entity>: {reference, source, note}",
                entity=e["name"])

    # AL04 / AL08
    conflicts = [(e["name"], x["name"], x["match"]) for e in al["entities"] for x in e["attributes"] if x["match"].get("status") == "type-conflict"]
    if conflicts:
        warn("AL04", f"{len(conflicts)} attribute type conflicts with the reference: " +
             "; ".join(f"{en}.{an} vs {m['reference']} ({m.get('referenceType')})" for en, an, m in conflicts[:10]),
             "Reviewers decide (rename/extend). If the match is wrong, override attributeMatches.<Entity.attr>: {reference: null}")
    tc = [(e["name"], x["name"], x["typeConflict"]) for e in al["entities"] for x in e["attributes"] if x.get("typeConflict")]
    if tc:
        warn("AL08", f"{len(tc)} attributes typed differently across applications: " +
             "; ".join(f"{en}.{an}: {t}" for en, an, t in tc[:10]), "Canonical type must be agreed in review")

    # AL05 / AL06
    names = {e["name"] for e in al["entities"]}
    for en, v in (ov.get("entityMatches") or {}).items():
        if en not in names:
            err("AL05", f"entityMatches: unknown entity '{en}'", "Fix or remove the override")
        elif (v or {}).get("reference") not in (None, "", "none"):
            row = next(x for x in al["entities"] if x["name"] == en)
            if row["matchHow"] == "override-unknown":
                err("AL05", f"entityMatches.{en}: reference '{v['reference']}' not found in the reference model(s)",
                    "Use the exact reference entity name (see Candidates) and the right source (acord|baseline)")
        if not (v or {}).get("note"):
            err("AL06", f"entityMatches.{en} has no note", "Every override needs a note with the evidence")
    for k, v in (ov.get("attributeMatches") or {}).items():
        en = k.split(".", 1)[0]
        if en not in names:
            err("AL05", f"attributeMatches: unknown entity in '{k}'", "Fix or remove the override")
        if not (v or {}).get("note"):
            err("AL06", f"attributeMatches.{k} has no note", "Every override needs a note")
    for c in ov.get("clusters") or []:
        if not c.get("note"):
            err("AL06", f"clusters override {c.get('members')} has no note", "Every override needs a note")
    for x in ov.get("excludeEntities") or []:
        if not x.get("reason"):
            err("AL06", f"excludeEntities {x.get('entity')} has no reason", "Give a reason")

    # AL09
    html_p = d / "acord-alignment.html"
    from sensitive_scan import check_files, find_policy_file, load_policy, report
    report(check_files([d / f for f in ("alignment.json", "acord-alignment.html", "alignment-report.md",
                                         "alignment-overrides.yaml", "approvals.yaml")], load_policy(find_policy_file(d.resolve()))),
           err, "AL09", "Remove it at the source (overrides/decisions/config/comments) and rebuild; never write e-mails, URLs, hosts, keys, personal or client data into catalogue files")

    # AL10
    for f in ("acord-alignment.html", "acord-alignment.xlsx", "alignment-report.md"):
        if not (d / f).exists():
            err("AL10", f"{f} missing", "Re-run align.py")
    if html_p.exists():
        h = html_p.read_text(encoding="utf-8")
        if "/*__DATA__*/" in h or "{{TITLE}}" in h or "const DATA={" not in h:
            err("AL10", "acord-alignment.html does not embed the alignment data", "Re-run align.py")

    # AL11
    rc = al["summary"]["review"]
    info.append(f"review: {rc}")
    if al["review"].get("staleKeys"):
        warn("AL11", f"{len(al['review']['staleKeys'])} approvals refer to rows that no longer exist: {al['review']['staleKeys'][:5]}",
             "Entities were renamed/merged since review; reviewers must re-approve the new rows")
    if rc.get("entity_changed"):
        warn("AL11", f"{rc['entity_changed']} approved entities changed since approval - they need re-review")

    status = "pass" if not errors else "fail"
    rep = {"skill": "acord-alignment", "status": status, "iteration": a.iteration, "region": meta["region"],
           "slice": meta["scope"]["slice"], "summary": al["summary"], "errors": errors, "warnings": warnings, "info": info}
    (d / "validation.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(json.dumps({"status": status, "errors": len(errors), "warnings": len(warnings), "review": rc,
                      "firstErrors": [e["code"] + " " + e["message"] for e in errors[:10]]}, indent=2))
    sys.exit(0 if status == "pass" else 1)


if __name__ == "__main__":
    main()
