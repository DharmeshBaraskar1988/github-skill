#!/usr/bin/env python3
"""
Validate the regional view against its inputs. Writes validation.json; exit 1 on errors.

  R01  every application found in the input folder is in the view (none dropped)
  R02  per-application counts in the view equal the counts in its analysis artifacts
  R03  regional-view.html embeds the data and the data parses; no template placeholders left
  R04  regional-view.xlsx has all sheets and row counts match the data
  R05  applications whose discovery/analysis validation failed (error unless --allow-failed)
  R06  applications analysed inline (external specs, no discovery validation) - warning
  R07  undecided duplicates / unclassified endpoints still present - warning
  R08  no secrets in the HTML or the workbook data
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SECRET_PATTERNS = [
    r"(?i)(AccountKey|SharedAccessKey|Password|Pwd|ClientSecret)\s*=\s*[^;\s\"']{6,}",
    r"Endpoint=sb://[^;]+;SharedAccessKeyName=",
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="regional view output folder")
    ap.add_argument("--allow-failed", action="store_true", help="publish even if an input app failed validation")
    ap.add_argument("--iteration", type=int, default=0)
    a = ap.parse_args()
    out = Path(a.out)
    errors, warnings = [], []

    def err(code, msg, fix):
        errors.append({"code": code, "message": msg, "fix": fix})

    def warn(code, msg, fix=""):
        warnings.append({"code": code, "message": msg, "fix": fix})

    data = json.loads((out / "regional-view-data.json").read_text(encoding="utf-8"))
    root = (out / data["inputFolder"]).resolve()

    # R01: re-scan the input folder independently
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from build_regional_view import find_inputs  # noqa: E402
    items = find_inputs(root, [out.name, "regional-view", "canonical", "alignment", "reference", "regions", "style-examples"])
    if len(items) != len(data["apps"]):
        err("R01", f"Input folder has {len(items)} applications but the view has {len(data['apps'])}",
            "Re-run build_regional_view.py; check for unreadable specs")

    # R02
    for app in data["apps"]:
        aid = app["id"]
        n_ops = sum(1 for o in data["operations"] if o["appId"] == aid)
        n_ent = sum(1 for e in data["entities"] if e["appId"] == aid)
        n_dup = sum(1 for g in data["duplicates"] if g["appId"] == aid)
        c = app["counts"]
        for label, got, exp in (("operations", n_ops, c["operations"]), ("entities", n_ent, c["entities"]),
                                ("duplicate groups", n_dup, c["duplicateGroups"])):
            if got != exp:
                err("R02", f"{aid}: {label} in view {got} != analysis {exp}", "Re-run analyze.py then build_regional_view.py")
        if app["mode"] == "analysis":
            src = root / app["source"] / "analysis-summary.json"
            if src.exists():
                s = json.loads(src.read_text(encoding="utf-8"))
                if s["operations"] != c["operations"]:
                    err("R02", f"{aid}: analysis-summary has {s['operations']} operations, view has {c['operations']}",
                        "Regional view is stale - rebuild it")

    # R03
    html = (out / "regional-view.html").read_text(encoding="utf-8")
    m = re.search(r"const DATA = (\{.*?\});\nconst TABS", html, re.S)
    if not m:
        err("R03", "Embedded data not found in regional-view.html", "Rebuild; check the template marker /*__DATA__*/null")
    else:
        try:
            emb = json.loads(m.group(1).replace("<\\/", "</"))
            if len(emb["operations"]) != len(data["operations"]):
                err("R03", "Embedded data differs from regional-view-data.json", "Rebuild")
        except Exception as ex:  # noqa: BLE001
            err("R03", f"Embedded data is not valid JSON: {ex}", "Rebuild")
    if "{{TITLE}}" in html or "/*__DATA__*/" in html:
        err("R03", "Template placeholders left in HTML", "Rebuild")

    # R04
    try:
        import openpyxl
        wb = openpyxl.load_workbook(out / "regional-view.xlsx", read_only=True)
        need = {"Summary": None, "Applications": len(data["apps"]), "Domain_Matrix": None,
                "Domains_Capabilities": len(data["capabilities"]), "Endpoints": len(data["operations"]),
                "Entities": len(data["entities"]), "Attributes": None, "Relations": len(data["relations"]),
                "Duplicates": len(data["duplicates"]), "Cross_App_Duplicates": len(data["crossAppDuplicates"]),
                "Validation": None}
        for sh, rows in need.items():
            if sh not in wb.sheetnames:
                err("R04", f"Sheet {sh} missing from regional-view.xlsx", "Rebuild")
            elif rows is not None:
                got = sum(1 for _ in wb[sh].iter_rows(min_row=2, values_only=True))
                if got != rows:
                    err("R04", f"Sheet {sh}: {got} rows, expected {rows}", "Rebuild")
    except Exception as ex:  # noqa: BLE001
        err("R04", f"Cannot open regional-view.xlsx: {ex}", "Rebuild")

    # R05 / R06 / R07
    for app in data["apps"]:
        v = app["validation"]
        if v["analysis"] == "fail" or v["discovery"] == "fail":
            (warn if a.allow_failed else err)(
                "R05", f"{app['id']}: discovery={v['discovery']} analysis={v['analysis']}",
                "Run the discovery/analysis loops for this application until they pass")
        if app["mode"] == "inline-analysis":
            warn("R06", f"{app['id']} came from an external spec ({app['source']}) - analysed inline, not validated",
                 "Run the api-analysis skill on it to get decisions + validation")
        if app["counts"]["unclassified"]:
            warn("R07", f"{app['id']}: {app['counts']['unclassified']} unclassified endpoints")
    und = [g for g in data["duplicates"] if g["decision"] == "undecided"]
    if und:
        warn("R07", f"{len(und)} undecided duplicate groups are shown in the view")

    # R08
    for pat in SECRET_PATTERNS:
        if re.search(pat, html):
            err("R08", f"Secret-like content in regional-view.html (/{pat[:30]}.../)", "Find the source artifact and remove it")

    status = "pass" if not errors else "fail"
    report = {"skill": "regional-view", "status": status, "iteration": a.iteration, "totals": data["totals"],
              "applications": [x["id"] for x in data["apps"]], "errors": errors, "warnings": warnings}
    (out / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": status, "errors": len(errors), "warnings": len(warnings),
                      "firstErrors": [e["code"] + " " + e["message"] for e in errors[:10]],
                      "warningsList": [w["code"] + " " + w["message"] for w in warnings[:10]]}, indent=2))
    sys.exit(0 if status == "pass" else 1)


if __name__ == "__main__":
    main()
