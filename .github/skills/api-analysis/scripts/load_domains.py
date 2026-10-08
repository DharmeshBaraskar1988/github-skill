#!/usr/bin/env python3
"""
Convert the business domain catalogue (Excel) into domains.json.

Expected sheet layout (first sheet, or --sheet). Header names are matched
case-insensitively and loosely; only "Domain" is mandatory.

  | Domain | Capability | Description | Keywords | Region | Application |
  |--------|------------|-------------|----------|--------|-------------|
  | Claims |            | Claims mgmt | claim, fnol, loss, settlement | | |
  | Claims | Register Claim | ...     | create claim, fnol           | | |

* A row with a Domain and no Capability describes the domain itself.
* A row with a Capability adds that capability to the domain.
* Keywords: comma / semicolon / newline separated. They drive the mapping
  of endpoints to domains, so list the nouns your APIs actually use.
* Region / Application (optional): restrict a row to some regions/apps
  (comma separated, empty = everywhere).

Usage:
  python load_domains.py --xlsx domains.xlsx --out api-catalog/domains.json
  python load_domains.py --template domains-template.xlsx      # write an example workbook
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import openpyxl
except ImportError:  # pragma: no cover
    sys.exit("openpyxl is required: pip install openpyxl")

HEADER_ALIASES = {
    "domain": ["domain", "business domain", "domain name", "bounded context"],
    "subdomain": ["sub domain", "subdomain", "sub-domain"],
    "capability": ["capability", "business capability", "capability name", "function"],
    "description": ["description", "definition", "details"],
    "keywords": ["keywords", "keyword", "synonyms", "terms", "aliases"],
    "region": ["region", "regions"],
    "application": ["application", "applications", "app", "project", "projects", "system"],
}


def norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def split_list(s) -> list:
    return [x.strip() for x in re.split(r"[,;\n|]", str(s or "")) if x.strip()]


def map_headers(row) -> dict:
    idx = {}
    for i, cell in enumerate(row):
        h = norm(cell).lower()
        for key, aliases in HEADER_ALIASES.items():
            if h in aliases and key not in idx:
                idx[key] = i
    return idx


def load(xlsx: Path, sheet: str | None) -> dict:
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    header_row, idx = None, {}
    for r_i, row in enumerate(rows[:20]):
        idx = map_headers(row)
        if "domain" in idx:
            header_row = r_i
            break
    if header_row is None:
        sys.exit(f"No 'Domain' header found in the first 20 rows of sheet '{ws.title}'")

    domains: dict = {}
    issues = []
    for n, row in enumerate(rows[header_row + 1:], start=header_row + 2):
        get = lambda k: row[idx[k]] if k in idx and idx[k] < len(row) else None  # noqa: E731
        dname = norm(get("domain"))
        if not dname:
            if any(norm(c) for c in row):
                issues.append(f"row {n}: no Domain value - skipped")
            continue
        d = domains.setdefault(dname, {"name": dname, "description": "", "keywords": [], "subdomains": [],
                                       "regions": [], "applications": [], "capabilities": []})
        cap = norm(get("capability"))
        desc = norm(get("description"))
        kws = split_list(get("keywords"))
        regions = split_list(get("region"))
        apps = split_list(get("application"))
        sub = norm(get("subdomain"))
        if sub and sub not in d["subdomains"]:
            d["subdomains"].append(sub)
        if not cap:
            d["description"] = d["description"] or desc
            d["keywords"] += [k for k in kws if k not in d["keywords"]]
            d["regions"] += [r for r in regions if r not in d["regions"]]
            d["applications"] += [a for a in apps if a not in d["applications"]]
        else:
            if any(c["name"].lower() == cap.lower() for c in d["capabilities"]):
                issues.append(f"row {n}: duplicate capability '{cap}' in domain '{dname}'")
                continue
            d["capabilities"].append({"name": cap, "description": desc, "keywords": kws,
                                      "subdomain": sub, "regions": regions, "applications": apps, "row": n})
    return {"source": str(xlsx), "sheet": ws.title, "domains": list(domains.values()), "issues": issues}


def write_template(path: Path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Domains"
    ws.append(["Domain", "Capability", "Description", "Keywords", "Region", "Application"])
    data = [
        ("Claims", "", "Claims handling from first notice of loss to settlement", "claim, claims, fnol, loss, claimant, settlement, reserve", "", ""),
        ("Claims", "Register Claim", "Create a claim / first notice of loss", "create claim, register, fnol, submit", "", ""),
        ("Claims", "View Claim", "Retrieve claim details", "get claim, view, details", "", ""),
        ("Claims", "Search Claims", "List and search claims", "list claims, search, find", "", ""),
        ("Claims", "Update Claim", "Change claim data", "update claim, modify", "", ""),
        ("Claims", "Approve Claim", "Approve and settle a claim", "approve, settlement, settle", "", ""),
        ("Claims", "Close Claim", "Close or withdraw a claim", "delete claim, close, withdraw", "", ""),
        ("Claims", "Manage Claimants", "Parties claiming under a policy", "claimant, claimants", "", ""),
        ("Document Management", "", "Documents attached to business objects", "document, documents, upload, attachment, file", "", ""),
        ("Document Management", "Upload Document", "", "upload document, attach", "", ""),
        ("Document Management", "List Documents", "", "list documents", "", ""),
        ("Document Management", "Delete Document", "", "delete document, remove", "", ""),
        ("Policy", "", "Policy administration", "policy, policies, coverage, premium, endorsement, renewal, policyholder", "", ""),
        ("Policy", "Issue Policy", "", "create policy, issue, bind", "", ""),
        ("Policy", "View Policy", "", "get policy, view policy", "", ""),
        ("Policy", "Search Policies", "", "list policies, search", "", ""),
        ("Policy", "Renew Policy", "", "renew, renewal", "", ""),
        ("Policy", "Manage Policyholder", "", "policyholder, holder, insured", "", ""),
        ("Quote", "", "Quotation and pricing", "quote, quotes, quotation, price, pricing, rating", "", ""),
        ("Quote", "Create Quote", "", "create quote, quotation", "", ""),
        ("Quote", "Get Quote", "", "get quote", "", ""),
    ]
    for r in data:
        ws.append(list(r))
    for col, w in zip("ABCDEF", (24, 26, 50, 60, 12, 16)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    readme = wb.create_sheet("README")
    for line in (__doc__ or "").splitlines():
        readme.append([line])
    readme.column_dimensions["A"].width = 110
    wb.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx")
    ap.add_argument("--sheet")
    ap.add_argument("--out")
    ap.add_argument("--template", help="write an example domain workbook to this path and exit")
    a = ap.parse_args()
    if a.template:
        write_template(Path(a.template))
        print(f"Template written: {a.template}")
        return
    if not a.xlsx or not a.out:
        ap.error("--xlsx and --out are required")
    res = load(Path(a.xlsx), a.sheet)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps({"output": a.out, "domains": len(res["domains"]),
                      "capabilities": sum(len(d["capabilities"]) for d in res["domains"]),
                      "issues": res["issues"]}, indent=2))


if __name__ == "__main__":
    main()
