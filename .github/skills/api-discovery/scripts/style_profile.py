#!/usr/bin/env python3
"""
Learn house-style CONVENTIONS from example OpenAPI specs - never their content.

Example folders (first existing ones are used, region overrides global):
  api-catalog/style-examples/_global/**.yaml|yml|json
  api-catalog/style-examples/<REGION>/**.yaml|yml|json
(or `discovery.styleExamples: [paths]` in api-catalog.config.yaml)

What is learned (style-profile.json, next to the discovery output):
  * operationId case (PascalCase / camelCase / snake_case / kebab-case), tag case, path segment case,
    property name case, plural collection segments
  * info fields always present (names only: contact, license, x-audience ...)
  * standard error responses used on most operations (status codes + whether a shared error schema is used)
  * security scheme naming (key name per scheme type)
  * header parameters that most operations declare (names only - reported, never added automatically)
  * vendor extensions in use (names only)
  * share of operations with summary / description
What is stored to PREVENT copying ("fingerprints"): example paths, schema names and hashes of every long text.
The discovery validator (D13) fails if any of them shows up in a generated spec without coming from the source code.

Usage:
  python style_profile.py --config api-catalog.config.yaml          # writes <discovery outputDir>/style-profile.json
  python style_profile.py --examples api-catalog/style-examples/_global --out style-profile.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import yaml

METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
STANDARD_SCHEMAS = {"ProblemDetails", "HttpValidationProblemDetails", "ValidationProblemDetails", "Error", "ErrorResponse"}


def case_of(s: str) -> str:
    if not s:
        return "unknown"
    if "-" in s and s == s.lower():
        return "kebab-case"
    if "_" in s and s == s.lower():
        return "snake_case"
    if re.match(r"^[A-Z][A-Za-z0-9]*$", s):
        return "PascalCase"
    if re.match(r"^[a-z][A-Za-z0-9]*$", s):
        return "camelCase" if re.search(r"[A-Z]", s) else "lowercase"
    if s.istitle() or re.match(r"^([A-Z][a-z0-9]*)( [A-Z][a-z0-9]*)*$", s):
        return "Title Case"
    return "mixed"


def majority(counter: Counter, ignore=("lowercase", "unknown")):
    """lowercase single words fit camelCase/kebab/snake alike - do not let them vote."""
    c = Counter({k: v for k, v in counter.items() if k not in ignore})
    if not c:
        return counter.most_common(1)[0][0] if counter else None
    k, v = c.most_common(1)[0]
    return k if v / max(sum(c.values()), 1) >= 0.6 else "mixed"


def text_hash(t: str) -> str:
    return hashlib.sha1(re.sub(r"\s+", " ", t.strip().lower()).encode()).hexdigest()[:16]


def long_texts(node, acc):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("description", "summary", "title") and isinstance(v, str) and len(v.strip()) >= 40:
                acc.add(text_hash(v))
            else:
                long_texts(v, acc)
    elif isinstance(node, list):
        for v in node:
            long_texts(v, acc)


def collect(folders: list) -> list:
    docs = []
    for f in folders:
        f = Path(f)
        if not f.exists():
            continue
        for p in sorted(list(f.rglob("*.yaml")) + list(f.rglob("*.yml")) + list(f.rglob("*.json"))):
            try:
                t = p.read_text(encoding="utf-8")
                d = json.loads(t) if p.suffix == ".json" else yaml.safe_load(t)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(d, dict) and str(d.get("openapi", "")).startswith("3"):
                docs.append((p, d))
    return docs


def build_profile(docs: list) -> dict:
    op_case, tag_case, seg_case, prop_case = Counter(), Counter(), Counter(), Counter()
    plural, single = 0, 0
    info_fields, ext_names, header_params = Counter(), Counter(), Counter()
    err_codes, err_schema = Counter(), Counter()
    sec_names = {}
    n_ops = n_summary = n_desc = 0
    fp_paths, fp_schemas, fp_texts = set(), set(), set()
    for _, d in docs:
        for k in (d.get("info") or {}):
            info_fields[k] += 1
        for t in d.get("tags") or []:
            tag_case[case_of(t.get("name", ""))] += 1
        for name, sch in ((d.get("components") or {}).get("securitySchemes") or {}).items():
            key = (sch.get("type"), sch.get("scheme") or sch.get("in"))
            sec_names.setdefault(f"{key[0]}:{key[1]}", Counter())[name] += 1
        for name, s in ((d.get("components") or {}).get("schemas") or {}).items():
            fp_schemas.add(name)
            for pn in (s.get("properties") or {}):
                prop_case[case_of(pn)] += 1
        for path, item in (d.get("paths") or {}).items():
            fp_paths.add(path)
            parts = [s for s in path.split("/") if s]
            for i, s in enumerate(parts):
                if s.startswith("{") or re.match(r"^v\d+$", s):
                    continue
                seg_case[case_of(s)] += 1
                if i + 1 < len(parts) and parts[i + 1].startswith("{"):
                    if s.endswith("s"):
                        plural += 1
                    else:
                        single += 1
            for m, op in item.items():
                if m not in METHODS:
                    if m == "parameters":
                        for p in op:
                            if isinstance(p, dict) and p.get("in") == "header":
                                header_params[p.get("name")] += 1
                    continue
                n_ops += 1
                op_case[case_of(op.get("operationId", ""))] += 1
                n_summary += bool(op.get("summary"))
                n_desc += bool(op.get("description"))
                for k in op:
                    if k.startswith("x-"):
                        ext_names[k] += 1
                for p in op.get("parameters") or []:
                    if isinstance(p, dict) and p.get("in") == "header":
                        header_params[p.get("name")] += 1
                    if isinstance(p, dict) and "$ref" in p:
                        ref = p["$ref"].split("/")[-1]
                        cp = ((d.get("components") or {}).get("parameters") or {}).get(ref, {})
                        if cp.get("in") == "header":
                            header_params[cp.get("name")] += 1
                for code, r in (op.get("responses") or {}).items():
                    code = str(code)
                    if code[0] in "45" or code == "default":
                        err_codes[code] += 1
                        if isinstance(r, dict) and "$ref" in r:
                            r = ((d.get("components") or {}).get("responses") or {}).get(r["$ref"].split("/")[-1], {})
                        for c in ((r or {}).get("content") or {}).values():
                            ref = ((c.get("schema") or {}).get("$ref") or "").split("/")[-1]
                            if ref:
                                err_schema[ref] += 1
        long_texts(d, fp_texts)
    nd = max(len(docs), 1)
    return {
        "examples": [str(p) for p, _ in docs],
        "operations": n_ops,
        "conventions": {
            "operationIdCase": majority(op_case),
            "tagCase": majority(tag_case),
            "pathSegmentCase": majority(seg_case),
            "propertyCase": majority(prop_case),
            "pluralCollections": (plural >= single) if (plural + single) else None,
            "requiredInfoFields": sorted(k for k, v in info_fields.items() if v / nd >= 0.8 and k not in ("title", "version")),
            "standardErrorResponses": sorted(c for c, v in err_codes.items() if n_ops and v / n_ops >= 0.7),
            "errorSchemaUsed": err_schema.most_common(1)[0][0] if err_schema else None,
            "securitySchemeNames": {k: v.most_common(1)[0][0] for k, v in sec_names.items()},
            "commonHeaderParameters": sorted(k for k, v in header_params.items() if k and n_ops and v / n_ops >= 0.7),
            "vendorExtensions": sorted(ext_names),
            "summaryShare": round(n_summary / n_ops, 2) if n_ops else None,
            "descriptionShare": round(n_desc / n_ops, 2) if n_ops else None,
        },
        "fingerprints": {"paths": sorted(fp_paths), "schemas": sorted(fp_schemas - STANDARD_SCHEMAS), "textHashes": sorted(fp_texts)},
    }


def example_folders(cfg: dict, base: Path) -> list:
    if cfg.get("discovery", {}).get("styleExamples"):
        return [(base / p).resolve() for p in cfg["discovery"]["styleExamples"]]
    root = (base / cfg.get("catalogRoot", "api-catalog")).resolve()
    return [root / "style-examples" / "_global", root / "style-examples" / str(cfg.get("region", ""))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--examples", action="append", default=[])
    ap.add_argument("--out")
    a = ap.parse_args()
    cfg, base = {}, Path.cwd()
    if a.config:
        cfg = yaml.safe_load(open(a.config, encoding="utf-8")) or {}
        base = Path(a.config).resolve().parent
    folders = [Path(x) for x in a.examples] or example_folders(cfg, base)
    out = Path(a.out) if a.out else (base / cfg.get("discovery", {}).get("outputDir", "api-catalog/discovery") / "style-profile.json")
    docs = collect(folders)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not docs:
        if out.exists():
            out.unlink()
        print(json.dumps({"styleExamples": [str(f) for f in folders], "examples": 0,
                          "note": "no example specs found - no style profile, conventions not enforced"}, indent=2))
        return
    prof = build_profile(docs)
    prof["folders"] = [str(f) for f in folders if f.exists()]
    out.write_text(json.dumps(prof, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(out), "examples": len(docs), "conventions": prof["conventions"]}, indent=2))


if __name__ == "__main__":
    main()
