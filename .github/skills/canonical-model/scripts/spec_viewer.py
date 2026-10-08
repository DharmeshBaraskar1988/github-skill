#!/usr/bin/env python3
"""
Spec viewer: one self-contained HTML page that shows OpenAPI specs and canonical models as YAML or JSON
(toggle), with an outline (paths / schemas / entities), search, copy and download.

Two modes
  python spec_viewer.py --doc canonical/EU/canonical-openapi.yaml --doc canonical/EU/canonical-model.json \
                        --out canonical/EU/canonical-viewer.html --title "EU canonical"
  python spec_viewer.py --scan api-catalog --out api-catalog/spec-viewer.html
      collects every discovery openapi.yaml, analysis 1-openapi.enriched.yaml, external spec,
      canonical-openapi.yaml and canonical-model.json under the folder (releases excluded)

Both YAML and JSON texts are produced here from the same document, so the two views are always identical in content.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

import yaml

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "spec-viewer.template.html"


class NoAlias(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def load(p: Path):
    t = p.read_text(encoding="utf-8")
    return json.loads(t) if p.suffix == ".json" else yaml.safe_load(t)


def describe(p: Path, doc: dict, root: Path | None) -> dict:
    rel = str(p.relative_to(root)) if root else p.name
    parts = rel.replace("\\", "/").split("/")
    if doc.get("modelType") == "canonical":
        kind, label = "canonical-model", f"{doc.get('region')} canonical model v{doc.get('version')} ({doc.get('status')})"
    elif "openapi" in doc:
        info = doc.get("info", {}) or {}
        if p.name == "canonical-openapi.yaml":
            kind = "canonical-openapi"
        elif p.name == "1-openapi.enriched.yaml":
            kind = "enriched-openapi"
        elif "discovery" in parts:
            kind = "discovery-openapi"
        else:
            kind = "external-openapi"
        region = info.get("x-region") or ""
        app = info.get("x-application") or ""
        label = f"{info.get('title', p.stem)} {info.get('version', '')}".strip() + (f" · {region}/{app}" if app else (f" · {region}" if region else ""))
    else:
        kind, label = "other", rel
    return {"id": rel, "kind": kind, "label": label, "path": rel, "fileName": p.name,
            "yaml": yaml.dump(doc, Dumper=NoAlias, sort_keys=False, allow_unicode=True, width=120),
            "json": json.dumps(doc, indent=2, ensure_ascii=False),
            "stats": stats(doc)}


def stats(doc):
    if doc.get("modelType") == "canonical":
        return {"entities": len(doc.get("entities", [])), "endpoints": len(doc.get("endpoints", [])),
                "attributes": sum(len(e.get("attributes", [])) for e in doc.get("entities", []))}
    if "openapi" in doc:
        return {"paths": len(doc.get("paths") or {}),
                "operations": sum(len([m for m in v if m in ("get", "post", "put", "patch", "delete", "head", "options")])
                                  for v in (doc.get("paths") or {}).values()),
                "schemas": len(((doc.get("components") or {}).get("schemas")) or {})}
    return {}


def scan(root: Path) -> list:
    files = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or {"releases", "regional-view", "style-examples", "reference"} & set(p.parts):
            continue
        if p.name in ("openapi.yaml", "1-openapi.enriched.yaml", "canonical-openapi.yaml", "canonical-model.json") or \
                ("external" in p.parts and p.suffix in (".yaml", ".yml", ".json")):
            files.append(p)
    return files


def build(docs: list, out: Path, title: str):
    payload = json.dumps({"title": title, "docs": docs}, separators=(",", ":")).replace("</", "<\\/")
    page = TEMPLATE.read_text(encoding="utf-8").replace("{{TITLE}}", html.escape(title)).replace("/*__DATA__*/null", payload)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", action="append", default=[])
    ap.add_argument("--scan")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="API specs")
    a = ap.parse_args()
    root = Path(a.scan).resolve() if a.scan else None
    paths = scan(root) if root else [Path(x).resolve() for x in a.doc]
    docs = []
    for p in paths:
        try:
            d = load(p)
        except Exception as ex:  # noqa: BLE001
            print(f"skip {p}: {ex}")
            continue
        if isinstance(d, dict) and ("openapi" in d or d.get("modelType") == "canonical"):
            docs.append(describe(p, d, root or p.parent))
    order = {"canonical-openapi": 0, "canonical-model": 1, "enriched-openapi": 2, "discovery-openapi": 3, "external-openapi": 4}
    docs.sort(key=lambda x: (order.get(x["kind"], 9), x["path"]))
    build(docs, Path(a.out), a.title)
    print(json.dumps({"output": a.out, "documents": [f"{d['kind']}: {d['path']}" for d in docs]}, indent=2))


if __name__ == "__main__":
    main()
