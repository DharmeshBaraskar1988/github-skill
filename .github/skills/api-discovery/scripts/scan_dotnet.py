#!/usr/bin/env python3
"""
Step 1 of discovery: scan a .NET repository and write inventory.json.

Usage:
  python scan_dotnet.py --config api-catalog.config.yaml
  python scan_dotnet.py --root . --region EU --application claims --out api-catalog/discovery/EU/claims

The inventory is the single source of truth for everything the scanner could
prove statically: projects, endpoints, model types, non-HTTP functions and a
list of `needsReview` items the agent must resolve via overrides.yaml.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cs_parser as P  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


def load_config(path: str | None) -> dict:
    if not path:
        return {}
    if yaml is None:
        sys.exit("PyYAML is required: pip install pyyaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def referenced_names(cs_type: str | None) -> set:
    """All non-primitive type names referenced by a C# type expression."""
    out = set()
    if not cs_type:
        return out
    t = cs_type.strip().rstrip("?").replace(" ", "")
    while t.endswith("[]"):
        t = t[:-2]
    base, args = P.parse_generic(t)
    base = base.split(".")[-1]
    for a in args:
        out |= referenced_names(a)
    if base in P.PRIMITIVES or t in P.PRIMITIVES:
        return out
    if base in P.COLLECTION_GENERICS or base in P.DICT_GENERICS or base in P.WRAPPER_GENERICS:
        return out
    if base in ("ProblemDetails", "HttpValidationProblemDetails", "ValidationProblemDetails"):
        out.add(base)
        return out
    if re.match(r"^[A-Z]\w*$", base) and len(base) > 1:
        out.add(base)
    return out


def shape(td: P.TypeDef) -> tuple:
    return tuple(sorted((p.name, p.csType) for p in td.properties)) + tuple(td.enumValues)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--root")
    ap.add_argument("--region")
    ap.add_argument("--application")
    ap.add_argument("--out")
    args = ap.parse_args()

    cfg = load_config(args.config)
    cfg_dir = Path(args.config).resolve().parent if args.config else Path.cwd()
    root = Path(args.root) if args.root else (cfg_dir / cfg["repoRoot"] if cfg.get("repoRoot") else cfg_dir)
    root = root.resolve()
    region = args.region or cfg.get("region") or "UNSPECIFIED"
    app = args.application or cfg.get("application") or root.name
    out = Path(args.out or cfg.get("discovery", {}).get("outputDir") or f"api-catalog/discovery/{region}/{app}")
    if not out.is_absolute():
        out = (cfg_dir / out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    excludes = P.DEFAULT_EXCLUDES + list(cfg.get("exclude", []))
    source_roots = cfg.get("sourceRoots") or ["."]

    projects = P.find_projects(root, source_roots, excludes)
    if not projects:
        sys.exit(f"No .csproj found under {root} (sourceRoots={source_roots})")
    include_projects = cfg.get("includeProjects")
    if include_projects:
        projects = [p for p in projects if p.name in include_projects]
    proj_paths = [p.path for p in projects]

    # ---- read sources ---------------------------------------------------- #
    file_index: dict = {}
    raw_text: dict = {}
    types: list = []
    skipped_forbidden = []
    for proj in projects:
        file_index[proj.name] = {}
        for f, rel in P.iter_cs_files(root, proj, excludes, proj_paths):
            if P.is_forbidden(str(f)):
                skipped_forbidden.append(rel)
                continue
            text = P.read_text(f)
            raw_text[rel] = (proj, text)
            file_index[proj.name][rel] = P.strip_comments_keep_layout(text)
            types.extend(P.extract_types(text, proj.name, rel))

    known_types = {t.name for t in types}

    # ---- endpoints ------------------------------------------------------- #
    endpoints, non_http = [], []
    raw_counts = {}
    for rel, (proj, text) in raw_text.items():
        clean = file_index[proj.name][rel]
        eps = []
        if re.search(r"\.Map(" + "|".join(P.HTTP_VERBS) + r")\s*\(", clean):
            eps += P.extract_minimal_apis(text, proj.name, rel, known_types, file_index)
        if re.search(r"\[Http(" + "|".join(P.HTTP_VERBS) + r")\b", clean):
            eps += P.extract_controllers(text, proj.name, rel, known_types)
        if re.search(r"\[(Function|FunctionName)\(", clean):
            fe, fo = P.extract_functions(text, proj, rel, known_types)
            eps += fe
            non_http += fo
        endpoints += eps
        # independent raw counts -> used by the validator as a coverage cross-check
        rc = {
            "minimalApi": len(re.findall(r"\.\s*Map(?:" + "|".join(P.HTTP_VERBS) + r")\s*\(\s*\"", clean)),
            "controllerActions": len(re.findall(r"\[Http(?:" + "|".join(P.HTTP_VERBS) + r")\b", clean)),
            "httpTriggers": len(re.findall(r"\[HttpTrigger\b", clean)),
        }
        if any(rc.values()):
            raw_counts[rel] = rc

    # ---- resolve referenced types (transitive) ---------------------------- #
    by_name: dict = {}
    for t in types:
        by_name.setdefault(t.name, []).append(t)

    proj_refs = {p.name: set(p.projectReferences) for p in projects}

    def resolve(name: str, from_project: str):
        cands = by_name.get(name, [])
        if not cands:
            return None
        if len(cands) == 1:
            return cands[0]
        for c in cands:
            if c.project == from_project:
                return c
        for c in cands:
            if c.project in proj_refs.get(from_project, set()):
                return c
        return cands[0]

    reachable: dict = {}           # key -> TypeDef
    unresolved: dict = {}          # name -> set(referencedBy)
    queue = []
    for ep in endpoints:
        refs = set()
        refs |= referenced_names(ep.requestBody)
        for p in ep.params:
            refs |= referenced_names(p.csType)
        for v in ep.responses.values():
            refs |= referenced_names(v)
        for r in refs:
            queue.append((r, ep.project, f"{ep.method} {ep.path}"))

    seen = set()
    while queue:
        name, proj, ref_by = queue.pop()
        key = (name, proj)
        if key in seen:
            continue
        seen.add(key)
        td = resolve(name, proj)
        if td is None:
            if name in ("ProblemDetails", "HttpValidationProblemDetails", "ValidationProblemDetails"):
                continue
            unresolved.setdefault(name, set()).add(ref_by)
            continue
        reachable[(td.name, td.project, td.file)] = td
        nxt = []
        if td.baseType:
            nxt += list(referenced_names(td.baseType))
        for p in td.properties:
            nxt += list(referenced_names(p.csType))
        for n in nxt:
            if n in td.genericParams:
                continue
            queue.append((n, td.project, td.name))

    # schema keys (handle same-name types with different shapes)
    schema_keys = {}
    groups: dict = {}
    for td in reachable.values():
        groups.setdefault(td.name, []).append(td)
    collisions = []
    for name, tds in groups.items():
        shapes = {shape(t) for t in tds}
        if len(shapes) == 1:
            for t in tds:
                schema_keys[(t.name, t.project, t.file)] = name
        else:
            collisions.append({"name": name, "definitions": [f"{t.project}:{t.file}:{t.line}" for t in tds]})
            for t in tds:
                schema_keys[(t.name, t.project, t.file)] = f"{name}_{t.project.split('.')[-1]}"

    # ---- operationId uniqueness / defaults -------------------------------- #
    used = {}
    for ep in endpoints:
        if not ep.operationId:
            segs = [s for s in ep.path.split("/") if s and not s.startswith("{") and s.lower() not in ("api", "v1", "v2", "v3")]
            ep.operationId = P.to_pascal_words(ep.method.lower()) + "".join(P.to_pascal_words(s) for s in segs[-2:])
            if ep.path.rstrip("/").endswith("}"):
                ep.operationId += "ById"
        base = ep.operationId
        n = used.get(base, 0)
        if n:
            ep.operationId = f"{base}_{n + 1}"
        used[base] = n + 1

    review = []
    for ep in endpoints:
        for r in ep.needsReview:
            review.append({"operationId": ep.operationId, "method": ep.method, "path": ep.path,
                           "file": ep.file, "line": ep.line, "issue": r})
    for name, refs in sorted(unresolved.items()):
        review.append({"type": name, "issue": "Type not found in scanned source (NuGet/DLL/excluded project?)",
                       "referencedBy": sorted(refs)})
    for c in collisions:
        review.append({"type": c["name"], "issue": "Same type name with different shapes in several projects - suffixed with project",
                       "definitions": c["definitions"]})

    inventory = {
        "schemaVersion": 1,
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "region": region,
        "application": app,
        "repoRoot": os.path.relpath(root, out),
        "projects": P.to_dict(projects),
        "endpoints": P.to_dict(endpoints),
        "types": [dict(P.to_dict(td), schemaKey=schema_keys[k]) for k, td in sorted(reachable.items())],
        "allTypeCount": len(types),
        "unresolvedTypes": {k: sorted(v) for k, v in sorted(unresolved.items())},
        "typeNameCollisions": collisions,
        "nonHttpFunctions": non_http,
        "rawCounts": raw_counts,
        "needsReview": review,
        "skippedForbiddenFiles": skipped_forbidden,
    }
    # Sensitive data (credentials, e-mails, URLs, hosts, PII, client names) never reaches the inventory the agent reads
    from sensitive_scan import find_policy_file, load_policy, redact_obj, summarise
    inventory, red = redact_obj(inventory, load_policy(find_policy_file(out)))
    inventory["redactions"] = {"count": len(red), "summary": summarise(red),
                               "paths": sorted({r["path"] for r in red})[:100]}
    (out / "inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")

    print(json.dumps({
        "output": str(out / "inventory.json"),
        "projects": [(p.name, p.kind, ",".join(p.targetFrameworks)) for p in projects],
        "endpoints": len(endpoints),
        "reachableTypes": len(reachable),
        "unresolvedTypes": len(unresolved),
        "nonHttpFunctions": len(non_http),
        "needsReview": len(review),
    }, indent=2))


if __name__ == "__main__":
    main()
