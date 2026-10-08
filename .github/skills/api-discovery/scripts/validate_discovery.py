#!/usr/bin/env python3
"""
Step 3 of discovery: validate openapi.yaml against inventory.json and the source.

Writes validation.json next to the spec and exits 1 when anything blocking is
found. The agent MUST loop: fix (overrides.yaml) -> rebuild -> validate, until
status == "pass" or the iteration limit is reached.

Checks
  D01  OpenAPI document is structurally valid (openapi-spec-validator when installed)
  D02  every $ref resolves
  D03  coverage: raw route/attribute counts in source == endpoints in inventory
  D04  coverage: every inventory endpoint is in the spec (or excluded with a reason)
  D05  no unresolved C# types
  D06  no operation still flagged x-needs-review
  D07  every operation has a 2xx response; POST/PUT/PATCH have a request body (warning)
  D08  operationIds unique
  D09  no sensitive data (credentials, e-mails, URLs, hosts, PII, client names) in spec/overrides/inventory
  D14  sensitive values found in source code were redacted - warning
  D10  every schema has x-source-project (traceability)
  D11  description coverage (warning; error if config discovery.requireDescriptions)
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


def resolve_ref(spec, ref):
    if not ref.startswith("#/"):
        return False
    cur = spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="discovery output folder")
    ap.add_argument("--config")
    ap.add_argument("--iteration", type=int, default=0, help="loop counter, recorded in validation.json")
    args = ap.parse_args()
    d = Path(args.dir).resolve()
    cfg = yaml.safe_load(open(args.config, encoding="utf-8")) if args.config else {}
    cfg = cfg or {}
    require_desc = bool(cfg.get("discovery", {}).get("requireDescriptions", False))

    errors, warnings = [], []

    def err(code, msg, fix, **kw):
        errors.append(dict(code=code, message=msg, fix=fix, **kw))

    def warn(code, msg, fix="", **kw):
        warnings.append(dict(code=code, message=msg, fix=fix, **kw))

    inv = json.loads((d / "inventory.json").read_text(encoding="utf-8"))
    spec_text = (d / "openapi.yaml").read_text(encoding="utf-8")
    spec = yaml.safe_load(spec_text)

    # D01
    try:
        from openapi_spec_validator import validate as osv_validate  # type: ignore
        try:
            osv_validate(spec)
        except Exception as e:  # noqa: BLE001
            err("D01", f"OpenAPI structural validation failed: {str(e).splitlines()[0][:400]}",
                "Fix the cause in overrides.yaml (bad type/response) and rebuild")
    except ImportError:
        for k in ("openapi", "info", "paths"):
            if k not in spec:
                err("D01", f"Missing top-level '{k}'", "Rebuild with build_openapi.py")
        warn("D01", "openapi-spec-validator not installed - only basic structure checked",
             "pip install openapi-spec-validator")

    # D02
    refs = []
    walk_refs(spec, refs)
    for r in sorted(set(refs)):
        if not resolve_ref(spec, r):
            err("D02", f"Unresolved $ref {r}", "Add the missing type via overrides.yaml externalTypes / extraTypeFiles")

    # D03 raw vs inventory per file
    inv_by_file = {}
    for ep in inv["endpoints"]:
        key = (ep["file"], ep["style"])
        inv_by_file[key] = inv_by_file.get(key, 0) + 1
    for f, rc in inv.get("rawCounts", {}).items():
        mapping = [("minimalApi", "minimal-api"), ("controllerActions", "controller"), ("httpTriggers", "azure-function")]
        for raw_key, style in mapping:
            raw = rc.get(raw_key, 0)
            found = inv_by_file.get((f, style), 0)
            if style == "azure-function":
                # one trigger may expand to several verbs
                distinct = len({(e["handler"]) for e in inv["endpoints"] if e["file"] == f and e["style"] == style})
                found = distinct
            if raw > found:
                err("D03", f"{f}: source has {raw} {raw_key} declarations but scanner captured {found}",
                    "Open the file, find the missed endpoint(s) and add them under addEndpoints in overrides.yaml",
                    file=f)

    # D04 inventory -> spec
    spec_ops = {(m.upper(), p) for p, item in spec.get("paths", {}).items() for m in item}
    excluded = {(e["method"], e["path"]) for e in spec.get("x-excluded-endpoints", [])}
    for ep in inv["endpoints"]:
        k = (ep["method"], ep["path"])
        if k not in spec_ops and k not in excluded:
            err("D04", f"Endpoint {ep['method']} {ep['path']} ({ep['file']}:{ep['line']}) missing from spec",
                "Rebuild; if two endpoints collide on the same method+path, fix the route in overrides.yaml")
    for e in spec.get("x-excluded-endpoints", []):
        if not e.get("reason") or e["reason"] is True:
            err("D04", f"Excluded endpoint {e['method']} {e['path']} has no reason",
                "Give every exclude in overrides.yaml a 'reason'")

    # D05
    for name, by in (spec.get("x-unresolved-types") or {}).items():
        err("D05", f"Unresolved C# type '{name}' (used by {', '.join(by[:3])})",
            "Locate the type (other repo / NuGet DLL). Add it under externalTypes or extraTypeFiles in overrides.yaml",
            type=name)

    # D06/D07/D08/D11
    op_ids = {}
    missing_desc_ops = 0
    for p, item in spec.get("paths", {}).items():
        for m, op in item.items():
            ref = f"{m.upper()} {p}"
            if op.get("x-needs-review"):
                for issue in op["x-needs-review"]:
                    err("D06", f"{ref}: {issue}",
                        "Read the handler at x-source-file:x-source-line and add an endpoints override with the real types",
                        operationId=op.get("operationId"), file=op.get("x-source-file"), line=op.get("x-source-line"))
            codes = list(op.get("responses", {}).keys())
            if not any(str(c).startswith("2") for c in codes):
                err("D07", f"{ref}: no 2xx response", "Declare the success response in overrides.yaml")
            if m in ("post", "put", "patch") and "requestBody" not in op:
                warn("D07", f"{ref}: {m.upper()} without request body", "Confirm the endpoint really has no body")
            for c, r in op.get("responses", {}).items():
                if str(c).startswith("2") and str(c) != "204" and "content" not in r and m != "delete":
                    warn("D07", f"{ref}: {c} response has no body schema", "Confirm, or set the response type in overrides.yaml")
            oid = op.get("operationId")
            if oid in op_ids:
                err("D08", f"Duplicate operationId '{oid}' ({op_ids[oid]} and {ref})", "Rename via overrides.yaml set.operationId")
            op_ids[oid] = ref
            if not op.get("summary") and not op.get("description"):
                missing_desc_ops += 1

    # D09
    from sensitive_scan import check_files, find_policy_file, load_policy, report
    _pol = load_policy(find_policy_file(d))
    report(check_files([d / "openapi.yaml", d / "overrides.yaml", d / "inventory.json", d / "style-profile.json"], _pol),
           err, "D09", "Remove it at the source (overrides/decisions/config/comments) and rebuild; never write e-mails, URLs, hosts, keys, personal or client data into catalogue files")
    _inv_p = d / "inventory.json"
    _inv_red = (json.loads(_inv_p.read_text(encoding="utf-8")).get("redactions") or {}) if _inv_p.exists() else {}
    _spec_red = spec.get("x-redactions") or {}
    _red = _inv_red.get("count", 0) + _spec_red.get("count", 0)
    if _red:
        _sum = "; ".join(x for x in (_inv_red.get("summary"), _spec_red.get("summary")) if x)
        warn("D14", f"{_red} sensitive values found in the source code were redacted ({_sum})",
             "Nothing to fix in the spec. Tell the code owners: comments, defaults or examples in code contain real data")

    # D10 / D11 schemas
    missing_desc_schemas, missing_desc_props = 0, 0
    for name, s in spec.get("components", {}).get("schemas", {}).items():
        if "x-source-project" not in s:
            err("D10", f"Schema {name} has no x-source-project", "Rebuild; external types must set x-source-project")
        if not s.get("description"):
            missing_desc_schemas += 1
        for pn, ps in (s.get("properties") or {}).items():
            if not ps.get("description"):
                missing_desc_props += 1
    if missing_desc_ops or missing_desc_schemas:
        msg = (f"Descriptions missing: {missing_desc_ops} operations, {missing_desc_schemas} schemas, "
               f"{missing_desc_props} properties")
        fix = "Add summaries/descriptions via overrides.yaml (endpoints[].set.summary, types.<Name>.description)"
        (err if require_desc else warn)("D11", msg, fix)

    # D12 / D13 - style examples
    prof_p = d / "style-profile.json"
    if prof_p.exists():
        prof = json.loads(prof_p.read_text(encoding="utf-8"))
        conv, fp = prof["conventions"], prof["fingerprints"]
        strict = bool(cfg.get("discovery", {}).get("style", {}).get("strict"))
        ops = [(p, m, op) for p, it in spec.get("paths", {}).items() for m, op in it.items()]

        def style(msg, fix):
            (err if strict else warn)("D12", msg, fix)
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from style_profile import case_of
        if conv.get("pathSegmentCase") not in (None, "mixed"):
            bad = sorted({s for p, _, _ in ops for s in p.split("/") if s and not s.startswith("{") and not re.match(r"^v\d+$", s)
                          and case_of(s) not in (conv["pathSegmentCase"], "lowercase")})
            if bad:
                style(f"Path segments not in {conv['pathSegmentCase']} like the style examples: {bad[:8]}",
                      "Routes come from code - change them in code or accept the deviation; do not rename in overrides")
        if conv.get("propertyCase") not in (None, "mixed"):
            badp = sorted({f"{n}.{pn}" for n, s in spec.get("components", {}).get("schemas", {}).items()
                           for pn in (s.get("properties") or {}) if case_of(pn) not in (conv["propertyCase"], "lowercase")})
            if badp:
                style(f"Property names not in {conv['propertyCase']}: {badp[:8]}", "Wire names come from the serializer settings in code")
        miss_info = [k for k in conv.get("requiredInfoFields", []) if k not in spec.get("info", {})]
        if miss_info:
            style(f"info fields used by all style examples are missing: {miss_info}",
                  "Add them under `info:` in api-catalog.config.yaml with YOUR values (never copy the examples' values)")
        hdrs = conv.get("commonHeaderParameters") or []
        if hdrs:
            lacking = [f"{m.upper()} {p}" for p, m, op in ops
                       if not all(any(x.get("name", "").lower() == h.lower() for x in op.get("parameters", [])) for h in hdrs)]
            if lacking:
                style(f"{len(lacking)} operations lack header parameters {hdrs} that the style examples always declare",
                      "Check the code/middleware; if the API really accepts them add via overrides addParams, otherwise accept")
        sh = conv.get("summaryShare")
        if sh and sh >= 0.9:
            nos = [op.get("operationId") for _, _, op in ops if not op.get("summary")]
            if nos:
                style(f"Style examples give every operation a summary; {len(nos)} here have none: {nos[:8]}",
                      "Write summaries from the code's meaning in overrides (set.summary)")
        # D13 copy guard
        inv_paths = {e["path"] for e in inv["endpoints"]}
        inv_types = {t.get("schemaKey", t["name"]) for t in inv["types"]}
        ov_p = d / "overrides.yaml"
        ov = (yaml.safe_load(ov_p.read_text(encoding="utf-8")) or {}) if ov_p.exists() else {}
        allowed_types = inv_types | set((ov.get("externalTypes") or {}).keys())
        for p in sorted(set(spec.get("paths", {})) & set(fp["paths"])):
            if p not in inv_paths:
                err("D13", f"Path {p} exists only in the style examples - examples are a reference, not a source",
                    "Remove it from overrides addEndpoints unless the code really has it (then cite file:line)")
        for n in sorted(set(spec.get("components", {}).get("schemas", {})) & set(fp["schemas"])):
            if n not in allowed_types and not n.startswith(tuple(allowed_types)):
                err("D13", f"Schema {n} comes from the style examples, not from the code", "Remove it; describe real types only")
        from style_profile import long_texts as _lt
        src_hashes = set()
        for t in inv["types"]:
            _lt({"description": t.get("description", "")}, src_hashes)
            for pr in t.get("properties", []):
                _lt({"description": pr.get("description", "")}, src_hashes)
        for e in inv["endpoints"]:
            _lt({"summary": e.get("summary", ""), "description": e.get("description", "")}, src_hashes)
        mine = set()
        _lt(spec, mine)
        copied = (mine & set(fp["textHashes"])) - src_hashes
        if copied:
            err("D13", f"{len(copied)} description/summary texts are identical to texts in the style examples",
                "Write descriptions for THIS API from its code; the examples only show the style")

    status = "pass" if not errors else "fail"
    report = {
        "skill": "api-discovery",
        "status": status,
        "iteration": args.iteration,
        "region": inv["region"],
        "application": inv["application"],
        "counts": {
            "projects": len(inv["projects"]),
            "inventoryEndpoints": len(inv["endpoints"]),
            "specOperations": len(spec_ops),
            "excludedEndpoints": len(excluded),
            "schemas": len(spec.get("components", {}).get("schemas", {})),
            "nonHttpFunctions": len(inv.get("nonHttpFunctions", [])),
        },
        "errors": errors,
        "warnings": warnings,
    }
    (d / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_report_md(d, inv, spec, report)
    print(json.dumps({"status": status, "errors": len(errors), "warnings": len(warnings),
                      "firstErrors": [e["code"] + " " + e["message"] for e in errors[:10]]}, indent=2))
    sys.exit(0 if status == "pass" else 1)


def write_report_md(d: Path, inv, spec, report):
    L = [f"# Discovery report - {inv['application']} ({inv['region']})", "",
         f"Status: **{report['status'].upper()}** (iteration {report['iteration']})", "",
         "## Projects", "", "| Project | Kind | Target framework | Path |", "|---|---|---|---|"]
    for p in inv["projects"]:
        L.append(f"| {p['name']} | {p['kind']} | {', '.join(p['targetFrameworks'])} | {p['path']} |")
    L += ["", "## Counts", ""] + [f"- {k}: {v}" for k, v in report["counts"].items()]
    L += ["", "## Endpoints", "", "| Method | Path | operationId | Style | Source |", "|---|---|---|---|---|"]
    for p, item in spec.get("paths", {}).items():
        for m, op in item.items():
            L.append(f"| {m.upper()} | `{p}` | {op.get('operationId')} | {op.get('x-endpoint-style')} | "
                     f"{op.get('x-source-file')}:{op.get('x-source-line')} |")
    if inv.get("nonHttpFunctions"):
        L += ["", "## Non-HTTP functions (not in paths)", "", "| Function | Trigger | Source |", "|---|---|---|"]
        for f in inv["nonHttpFunctions"]:
            L.append(f"| {f['function']} | {f['trigger']} | {f['file']}:{f['line']} |")
    if report["errors"]:
        L += ["", "## Errors (must fix)", ""] + [f"- **{e['code']}** {e['message']}  \n  _Fix:_ {e['fix']}" for e in report["errors"]]
    if report["warnings"]:
        L += ["", "## Warnings", ""] + [f"- {w['code']} {w['message']}" for w in report["warnings"]]
    (d / "discovery-report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
