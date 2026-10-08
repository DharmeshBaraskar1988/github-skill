#!/usr/bin/env python3
"""
api-analysis: discovery openapi.yaml + domains.json + decisions.yaml -> 4 artifacts.

  1-openapi.enriched.yaml          OpenAPI with domain tags, x-domain, x-capability, x-entity
  2-domains-capabilities.json/.md  domain -> capabilities -> operations (+ entities per domain)
  3-entities-attributes.json/.md   canonical entities, attribute tree, relations, usage
  4-duplicates-report.json/.md     duplicate groups, where used, canonical, mapping
  analysis-summary.json            counts used by validation and by the regional view

Usage:
  python analyze.py --spec <discovery>/openapi.yaml --domains api-catalog/domains.json --out <analysis dir>
  python analyze.py --config api-catalog.config.yaml
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis_core import run_analysis  # noqa: E402


class NoAlias(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def md_domains(dc) -> str:
    L = [f"# Domains and capabilities - {dc['application']} ({dc['region']})", ""]
    for d in sorted(dc["domains"], key=lambda x: (x["domain"] == "Unclassified", x["domain"])):
        flag = "" if d["inCatalogue"] or d["domain"] == "Unclassified" else " (NOT IN CATALOGUE)"
        L += [f"## {d['domain']}{flag}", ""]
        if d.get("description"):
            L += [d["description"], ""]
        L += ["| Capability | Status | Operations |", "|---|---|---|"]
        for c in d["capabilities"]:
            ops = "<br>".join(f"`{o['method']} {o['path']}` ({o['operationId']}, {o['confidence']})" for o in c["operations"])
            L.append(f"| {c['name']} | {c['status']} | {ops} |")
        if d.get("catalogueCapabilitiesNotImplemented"):
            L += ["", "Catalogue capabilities with no endpoint here: " + ", ".join(d["catalogueCapabilitiesNotImplemented"])]
        if d.get("entities"):
            L += ["", "Entities: " + ", ".join(d["entities"])]
        L.append("")
    return "\n".join(L)


def md_entities(ea) -> str:
    L = [f"# Entities and attributes - {ea['application']} ({ea['region']})", ""]
    for e in sorted(ea["entities"], key=lambda x: x["name"]):
        L += [f"## {e['name']}", "",
              f"- Kind: {e['kind']}  |  Domain: {e['domain'] or '-'}  |  Roles: {', '.join(e['roles'])}",
              f"- Schemas: {', '.join(e['schemaNames'])}",
              f"- Source: {', '.join(e['sourceFiles'])}"]
        if e["description"]:
            L.append(f"- Description: {e['description']}")
        if e["kind"] == "enum":
            L += [f"- Values: {', '.join(e['enumValues'] or [])}", ""]
            continue
        L += ["", "| Attribute | Type | Required | Description |", "|---|---|---|---|"]
        for a in e["attributes"]:
            t = a["type"] + (f"({a['format']})" if a["format"] and "(" not in a["type"] else "")
            if a["refEntity"]:
                t = f"{'list of ' if a['isCollection'] else ''}{a['refEntity']}"
            L.append(f"| {a['name']} | {t} | {'yes' if a['required'] else ''} | {a['description']} |")
        if e["usedBy"]:
            L += ["", "Used by: " + ", ".join(f"`{u['method']} {u['path']}`" for u in e["usedBy"])]
        L.append("")
    L += ["## Relations", "", "| From | Relation | To | Via | Cardinality |", "|---|---|---|---|---|"]
    for r in ea["relations"]:
        L.append(f"| {r['from']} | {r['type']} | {r['to']} | {r['via']} | {r['cardinality']} |")
    return "\n".join(L) + "\n"


def md_dups(du) -> str:
    L = [f"# Duplicate entities - {du['application']} ({du['region']})", ""]
    if not du["groups"]:
        return "\n".join(L + ["No duplicate entities found.", ""])
    for i, g in enumerate(du["groups"], 1):
        L += [f"## Group {i}: {' / '.join(g['members'])}", "",
              f"- Match: **{g['match']}** (similarity {g['similarity']})",
              f"- Decision: **{g['decision']}**" + (f" -> canonical `{g['canonical']}`" if g.get("canonical") else ""),
              ]
        if g.get("note"):
            L.append(f"- Note: {g['note']}")
        if g.get("onlyIn"):
            for m, attrs in g["onlyIn"].items():
                if attrs:
                    L.append(f"- Only in {m}: {', '.join(attrs)}")
        L += ["", "| Schema | Role | Project | Source | Used by |", "|---|---|---|---|---|"]
        for m in g["memberDetails"]:
            L.append(f"| {m['schema']} | {m['role']} | {m['sourceProject']} | {m['sourceFile']} | {'<br>'.join(m['usedBy'])} |")
        L.append("")
    if du["mapping"]:
        L += ["## Schema -> canonical entity mapping", "", "| Schema | Canonical entity |", "|---|---|"]
        L += [f"| {k} | {v} |" for k, v in sorted(du["mapping"].items())]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--spec")
    ap.add_argument("--domains")
    ap.add_argument("--decisions")
    ap.add_argument("--out")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config, encoding="utf-8")) if a.config else {}
    cfg = cfg or {}
    base = Path(a.config).resolve().parent if a.config else Path.cwd()

    def rp(p):
        p = Path(p)
        return p if p.is_absolute() else (base / p).resolve()

    region, app = cfg.get("region"), cfg.get("application")
    spec_p = rp(a.spec or Path(cfg.get("discovery", {}).get("outputDir", f"api-catalog/discovery/{region}/{app}")) / "openapi.yaml")
    out = rp(a.out or cfg.get("analysis", {}).get("outputDir", f"api-catalog/analysis/{region}/{app}"))
    dom_p = rp(a.domains or cfg.get("analysis", {}).get("domainsJson", "api-catalog/domains.json"))
    out.mkdir(parents=True, exist_ok=True)
    dec_p = rp(a.decisions) if a.decisions else out / "decisions.yaml"

    spec = yaml.safe_load(spec_p.read_text(encoding="utf-8"))
    domains = json.loads(dom_p.read_text(encoding="utf-8"))
    decisions = yaml.safe_load(dec_p.read_text(encoding="utf-8")) if dec_p.exists() else {}

    res = run_analysis(spec, domains, decisions or {}, cfg)
    res["summary"]["inputs"] = {"spec": os.path.relpath(spec_p, out), "domains": os.path.relpath(dom_p, out),
                                "decisions": dec_p.name if dec_p.exists() else None}

    from sensitive_scan import find_policy_file, load_policy, redact_obj, summarise
    res, red = redact_obj(res, load_policy(find_policy_file(out)))
    res["summary"]["redactions"] = {"count": len(red), "summary": summarise(red)}
    with open(out / "1-openapi.enriched.yaml", "w", encoding="utf-8") as f:
        yaml.dump(res["enrichedSpec"], f, Dumper=NoAlias, sort_keys=False, allow_unicode=True, width=120)
    (out / "2-domains-capabilities.json").write_text(json.dumps(res["domainsCapabilities"], indent=2), encoding="utf-8")
    (out / "2-domains-capabilities.md").write_text(md_domains(res["domainsCapabilities"]), encoding="utf-8")
    (out / "3-entities-attributes.json").write_text(json.dumps(res["entitiesAttributes"], indent=2), encoding="utf-8")
    (out / "3-entities-attributes.md").write_text(md_entities(res["entitiesAttributes"]), encoding="utf-8")
    (out / "4-duplicates-report.json").write_text(json.dumps(res["duplicates"], indent=2), encoding="utf-8")
    (out / "4-duplicates-report.md").write_text(md_dups(res["duplicates"]), encoding="utf-8")
    (out / "analysis-summary.json").write_text(json.dumps(res["summary"], indent=2), encoding="utf-8")
    print(json.dumps(dict(res["summary"], output=str(out)), indent=2))


if __name__ == "__main__":
    main()
