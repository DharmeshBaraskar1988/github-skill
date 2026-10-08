#!/usr/bin/env python3
"""
Step 2 of discovery: inventory.json + overrides.yaml -> openapi.yaml (OpenAPI 3.0.3).

Usage:
  python build_openapi.py --config api-catalog.config.yaml
  python build_openapi.py --dir api-catalog/discovery/EU/claims [--config ...]

Never hand-edit openapi.yaml. Every correction goes into overrides.yaml in the
same folder, then this script is re-run. That keeps the spec reproducible.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cs_parser as P  # noqa: E402

STATUS_TEXT = {
    "200": "OK", "201": "Created", "202": "Accepted", "204": "No Content",
    "400": "Bad Request", "401": "Unauthorized", "403": "Forbidden", "404": "Not Found",
    "409": "Conflict", "422": "Unprocessable Entity", "500": "Internal Server Error",
    "default": "Unexpected error",
}

PROBLEM_DETAILS = {
    "type": "object",
    "description": "RFC 7807 problem details.",
    "properties": {
        "type": {"type": "string", "nullable": True},
        "title": {"type": "string", "nullable": True},
        "status": {"type": "integer", "format": "int32", "nullable": True},
        "detail": {"type": "string", "nullable": True},
        "instance": {"type": "string", "nullable": True},
    },
    "x-source-project": "Microsoft.AspNetCore.Http",
}


class Builder:
    def __init__(self, inv: dict, overrides: dict):
        self.inv = inv
        self.ov = overrides or {}
        self.schemas: dict = {}
        self.unresolved: dict = {}
        self.types_by_name: dict = {}
        for t in inv["types"]:
            self.types_by_name.setdefault(t["name"], []).append(t)
        for extra in self.ov.get("_extraTypes", []):
            extra.setdefault("schemaKey", extra["name"])
            self.types_by_name.setdefault(extra["name"], []).append(extra)
        self.external = self.ov.get("externalTypes", {}) or {}
        self.type_ov = self.ov.get("types", {}) or {}
        self.proj_refs = {p["name"]: set(p["projectReferences"]) for p in inv["projects"]}
        self.building = set()
        self.route_prefixes = [p.get("routePrefix", "") for p in inv["projects"]]

    # ------------------------------------------------------------------ types
    def find_type(self, name: str, project: str):
        c = self.types_by_name.get(name, [])
        if not c:
            return None
        if len(c) == 1:
            return c[0]
        for t in c:
            if t.get("project") == project:
                return t
        for t in c:
            if t.get("project") in self.proj_refs.get(project, set()):
                return t
        return c[0]

    def schema_for(self, cs_type, project: str, ref_by: str, generic_map=None):
        generic_map = generic_map or {}
        if cs_type is None:
            return None
        t = cs_type.strip().replace(" ", "")
        nullable = t.endswith("?")
        t = t.rstrip("?")
        if t in generic_map:
            return self.schema_for(generic_map[t], project, ref_by)
        if t.endswith("[]") and t != "byte[]":
            s = {"type": "array", "items": self.schema_for(t[:-2], project, ref_by, generic_map) or {}}
            return self._nullable(s, nullable)
        base, args = P.parse_generic(t)
        base = base.split(".")[-1]
        if t in P.PRIMITIVES or base in P.PRIMITIVES:
            typ, fmt = P.PRIMITIVES.get(t) or P.PRIMITIVES[base]
            s = {"type": typ}
            if fmt:
                s["format"] = fmt
            return self._nullable(s, nullable)
        if base in P.COLLECTION_GENERICS and args:
            s = {"type": "array", "items": self.schema_for(args[0], project, ref_by, generic_map) or {}}
            if base in ("HashSet", "ISet"):
                s["uniqueItems"] = True
            return self._nullable(s, nullable)
        if base in P.DICT_GENERICS and len(args) == 2:
            return self._nullable({"type": "object",
                                   "additionalProperties": self.schema_for(args[1], project, ref_by, generic_map) or {}}, nullable)
        if base in ("Nullable",) and args:
            return self._nullable(self.schema_for(args[0], project, ref_by, generic_map), True)
        if base in P.WRAPPER_GENERICS and args:
            return self.schema_for(args[0], project, ref_by, generic_map)
        if base in ("ProblemDetails", "HttpValidationProblemDetails", "ValidationProblemDetails"):
            if base not in self.schemas:
                pd = copy.deepcopy(PROBLEM_DETAILS)
                if base != "ProblemDetails":
                    pd["properties"]["errors"] = {"type": "object", "additionalProperties": {"type": "array", "items": {"type": "string"}}}
                self.schemas[base] = pd
            return self._ref(base, nullable)
        if base in self.external:
            if base not in self.schemas:
                ext = copy.deepcopy(self.external[base])
                ext.setdefault("x-source-project", "external")
                self.schemas[base] = ext
            return self._ref(base, nullable)

        td = self.find_type(base, project)
        if td is None:
            self.unresolved.setdefault(base, set()).add(ref_by)
            return self._nullable({"type": "object", "x-unresolved-type": base,
                                   "description": f"UNRESOLVED C# type '{base}' - add it to overrides.yaml externalTypes"}, nullable)

        key = td.get("schemaKey", td["name"])
        if args:      # closed generic e.g. PagedResult<ClaimDto>
            arg_names = []
            for a in args:
                an_base = P.parse_generic(a)[0].split(".")[-1]
                an = re.sub(r"[^A-Za-z0-9]", "", an_base[:1].upper() + an_base[1:] + "".join(
                    re.sub(r"[^A-Za-z0-9]", "", x) for x in P.parse_generic(a)[1]))
                arg_names.append(an)
            key = f"{key}Of{'And'.join(arg_names)}"
            gmap = dict(zip(td.get("genericParams", []), args))
        else:
            gmap = {}
        if key not in self.schemas and key not in self.building:
            self.building.add(key)
            self.schemas[key] = self.type_schema(td, gmap)
            self.building.discard(key)
        return self._ref(key, nullable)

    @staticmethod
    def _ref(key, nullable):
        s = {"$ref": f"#/components/schemas/{key}"}
        if nullable:
            return {"allOf": [s], "nullable": True}
        return s

    @staticmethod
    def _nullable(s, nullable):
        if s is None:
            return None
        if nullable and "$ref" not in s:
            s["nullable"] = True
        elif nullable:
            return {"allOf": [s], "nullable": True}
        return s

    def collect_props(self, td: dict, depth=0) -> list:
        props = []
        if td.get("baseType") and depth < 10:
            bname, bargs = P.parse_generic(td["baseType"])
            base_td = self.find_type(bname.split(".")[-1], td["project"])
            if base_td:
                inherited = self.collect_props(base_td, depth + 1)
                if bargs and base_td.get("genericParams"):
                    gm = dict(zip(base_td["genericParams"], bargs))
                    for p in inherited:
                        p["csType"] = gm.get(p["csType"].rstrip("?"), p["csType"])
                props += inherited
        names = {p["name"] for p in props}
        for p in td.get("properties", []):
            if p["name"] in names:
                props = [x for x in props if x["name"] != p["name"]]
            props.append(dict(p))
        return props

    def type_schema(self, td: dict, gmap: dict) -> dict:
        tov = self.type_ov.get(td["name"], {}) or {}
        src = {
            "x-source-project": td.get("project", ""),
            "x-source-file": td.get("file", ""),
            "x-source-line": td.get("line", 0),
            "x-namespace": td.get("namespace", ""),
            "x-csharp-kind": td.get("kind", "class"),
        }
        desc = tov.get("description") or td.get("description") or ""
        if td.get("kind") == "enum":
            s = {"type": "string", "enum": td.get("enumValues", [])}
            if desc:
                s["description"] = desc
            s.update(src)
            return s
        s = {"type": "object"}
        if desc:
            s["description"] = desc
        props, required = {}, []
        pov = tov.get("properties", {}) or {}
        for p in self.collect_props(td):
            ps = self.schema_for(p["csType"], td["project"], td["name"], gmap) or {}
            pdesc = (pov.get(p["name"], {}) or {}).get("description") or p.get("description")
            extra = {}
            for k in ("maxLength", "minLength", "pattern", "minimum", "maximum"):
                if p.get(k) is not None:
                    extra[k] = p[k]
            if p.get("format") and "$ref" not in ps:
                extra["format"] = p["format"]
            if "$ref" in ps and (pdesc or extra):
                ps = {"allOf": [ps]}
            if pdesc:
                ps["description"] = pdesc
            ps.update(extra)
            props[p["jsonName"]] = ps
            if p.get("required"):
                required.append(p["jsonName"])
        s["properties"] = props
        if required:
            s["required"] = required
        if td.get("baseType"):
            s["x-base-type"] = td["baseType"]
        if td.get("isAbstract"):
            s["x-abstract"] = True
        s.update(src)
        return s

    # ------------------------------------------------------------- endpoints
    def apply_endpoint_overrides(self, endpoints: list) -> list:
        rules = self.ov.get("endpoints", []) or []
        out = []
        for ep in endpoints:
            ep = copy.deepcopy(ep)
            ep["_overridden"] = []
            for r in rules:
                m = r.get("match", {})
                if m.get("operationId") and m["operationId"] != ep["operationId"]:
                    continue
                if m.get("method") and m["method"].upper() != ep["method"]:
                    continue
                if m.get("path") and m["path"] != ep["path"]:
                    continue
                if not m:
                    continue
                if r.get("exclude"):
                    ep["_excluded"] = r.get("reason") or r.get("exclude")
                s = r.get("set", {}) or {}
                for k in ("summary", "description", "tags", "requestBody", "requestContentType", "operationId", "auth"):
                    if k in s:
                        ep[k] = s[k]
                if "responses" in s:
                    ep["responses"] = {str(k): v for k, v in s["responses"].items()}
                if "params" in s:
                    ep["params"] = [dict({"required": True, "description": ""}, **p) for p in s["params"]]
                if "addParams" in s:
                    ep["params"] += [dict({"required": False, "description": ""}, **p) for p in s["addParams"]]
                if r.get("resolved") or s:
                    ep["needsReview"] = [x for x in ep.get("needsReview", [])
                                         if x not in (r.get("resolves") or ep.get("needsReview", []))]
                ep["_overridden"].append(r.get("note", "override"))
            out.append(ep)
        for add in self.ov.get("addEndpoints", []) or []:
            e = {"method": add["method"].upper(), "path": add["path"], "style": add.get("style", "manual"),
                 "project": add.get("project", "manual"), "file": add.get("file", ""), "line": add.get("line", 0),
                 "handler": add.get("handler", ""), "operationId": add["operationId"],
                 "tags": add.get("tags", []), "summary": add.get("summary", ""), "description": add.get("description", ""),
                 "params": [dict({"required": True, "description": ""}, **p) for p in add.get("params", [])],
                 "requestBody": add.get("requestBody"), "requestContentType": add.get("requestContentType", "application/json"),
                 "responses": {str(k): v for k, v in (add.get("responses") or {"200": None}).items()},
                 "auth": add.get("auth", ""), "needsReview": [], "_overridden": ["addEndpoints"]}
            out.append(e)
        return out

    def build(self, cfg: dict) -> dict:
        inv = self.inv
        app = inv["application"]
        region = inv["region"]
        paths: dict = {}
        sec_schemes = {}
        endpoints = self.apply_endpoint_overrides(inv["endpoints"])
        excluded = []
        tags_seen = {}
        for ep in endpoints:
            if ep.get("_excluded"):
                excluded.append({"operationId": ep["operationId"], "method": ep["method"], "path": ep["path"],
                                 "reason": ep["_excluded"]})
                continue
            ref_by = f"{ep['method']} {ep['path']}"
            op = {"operationId": ep["operationId"]}
            tags = ep.get("tags") or [self.default_tag(ep["path"], self.route_prefixes)]
            op["tags"] = tags
            for t in tags:
                tags_seen.setdefault(t, set()).add(ep["project"])
            if ep.get("summary"):
                op["summary"] = ep["summary"]
            if ep.get("description"):
                op["description"] = ep["description"]
            params = []
            for p in ep.get("params", []):
                if p["source"] == "asparameters":
                    td = self.find_type(P.parse_generic(p["csType"].rstrip("?"))[0], ep["project"])
                    if td:
                        for pp in self.collect_props(td):
                            params.append({"name": pp["jsonName"], "in": "query", "required": bool(pp.get("required")),
                                           "schema": self.schema_for(pp["csType"], ep["project"], ref_by) or {"type": "string"}})
                    else:
                        self.unresolved.setdefault(p["csType"], set()).add(ref_by)
                    continue
                if p["source"] in ("body", "form", "services"):
                    continue
                loc = {"path": "path", "query": "query", "header": "header", "cookie": "cookie"}.get(p["source"], "query")
                prm = {"name": p["name"], "in": loc, "required": True if loc == "path" else bool(p.get("required")),
                       "schema": self.schema_for(p["csType"], ep["project"], ref_by) or {"type": "string"}}
                if p.get("description"):
                    prm["description"] = p["description"]
                params.append(prm)
            # path params declared in route but missing from handler
            for rp in re.findall(r"\{([^}]+)\}", ep["path"]):
                if not any(x["name"] == rp and x["in"] == "path" for x in params):
                    params.append({"name": rp, "in": "path", "required": True, "schema": {"type": "string"}})
            if params:
                op["parameters"] = params
            form = [p for p in ep.get("params", []) if p["source"] == "form"]
            if ep.get("requestBody"):
                rb_schema = self.schema_for(ep["requestBody"], ep["project"], ref_by)
                op["requestBody"] = {"required": True,
                                     "content": {ep.get("requestContentType") or "application/json": {"schema": rb_schema}}}
            elif form:
                op["requestBody"] = {"required": True, "content": {"multipart/form-data": {"schema": {
                    "type": "object",
                    "properties": {p["name"]: self.schema_for(p["csType"], ep["project"], ref_by) for p in form}}}}}
            responses = {}
            for code, typ in sorted(ep.get("responses", {}).items(), key=lambda kv: kv[0]):
                r = {"description": STATUS_TEXT.get(code, "Response")}
                if typ and code != "204":
                    r["content"] = {"application/json": {"schema": self.schema_for(typ, ep["project"], ref_by)}}
                responses[code] = r
            op["responses"] = responses or {"200": {"description": "OK"}}
            auth = ep.get("auth") or ""
            if auth.startswith("function-key") and not auth.endswith("Anonymous"):
                sec_schemes["functionKey"] = {"type": "apiKey", "in": "header", "name": "x-functions-key"}
                op["security"] = [{"functionKey": []}]
            elif auth == "required":
                sec_schemes["bearer"] = {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
                op["security"] = [{"bearer": []}]
            elif auth == "anonymous" or auth.endswith("Anonymous"):
                op["security"] = []
            op["x-source-project"] = ep["project"]
            op["x-source-file"] = ep["file"]
            op["x-source-line"] = ep["line"]
            op["x-endpoint-style"] = ep["style"]
            if ep.get("handler"):
                op["x-handler"] = ep["handler"]
            if ep.get("needsReview"):
                op["x-needs-review"] = ep["needsReview"]
            paths.setdefault(ep["path"], {})[ep["method"].lower()] = op

        dcfg = cfg.get("discovery", {}) if cfg else {}
        servers = cfg.get("servers") if cfg else None
        if not servers:
            servers = [{"url": "https://{host}", "description": f"{app} ({region}) - placeholder, real hosts are injected per environment",
                        "variables": {"host": {"default": f"{app}.{region.lower()}.example.internal"}}}]
        spec = {
            "openapi": "3.0.3",
            "info": {
                "title": cfg.get("title") or f"{P.to_pascal_words(app)} API",
                "version": str(cfg.get("version") or "1.0.0"),
                "description": cfg.get("description") or
                f"Generated by the api-discovery skill from source code of '{app}' ({region}). Do not edit by hand; use overrides.yaml.",
                "x-region": region,
                "x-application": app,
                "x-generated-at": inv["generatedAt"],
                "x-target-frameworks": sorted({tf for p in inv["projects"] for tf in p["targetFrameworks"]}),
            },
            "servers": servers,
            "tags": [{"name": t, "x-source-projects": sorted(p)} for t, p in sorted(tags_seen.items())],
            "paths": dict(sorted(paths.items())),
            "components": {"schemas": dict(sorted(self.schemas.items()))},
        }
        if sec_schemes:
            spec["components"]["securitySchemes"] = sec_schemes
        if inv.get("nonHttpFunctions"):
            spec["x-non-http-functions"] = inv["nonHttpFunctions"]
        if excluded:
            spec["x-excluded-endpoints"] = excluded
        if dcfg.get("includeSourceProjects", True):
            spec["x-source-projects"] = [{"name": p["name"], "path": p["path"], "kind": p["kind"],
                                          "targetFrameworks": p["targetFrameworks"]} for p in inv["projects"]]
        return spec

    @staticmethod
    def default_tag(path: str, prefixes=()) -> str:
        skip = {"api"} | {p.strip("/").lower() for p in prefixes if p}
        segs = [s for s in path.split("/") if s and not s.startswith("{") and s.lower() not in skip and not re.match(r"^v\d+$", s, re.I)]
        return P.to_pascal_words(segs[0]) if segs else "Default"


def convert_case(s: str, case: str) -> str:
    words = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z][a-z]|\b|[0-9]|$)", s.replace("-", " ").replace("_", " "))
    words = [w for w in words if w]
    if not words:
        return s
    if case == "PascalCase":
        return "".join(w[:1].upper() + w[1:].lower() if w.isupper() and len(w) > 1 else w[:1].upper() + w[1:] for w in words)
    if case == "camelCase":
        p = convert_case(s, "PascalCase")
        return p[:1].lower() + p[1:]
    if case == "snake_case":
        return "_".join(w.lower() for w in words)
    if case == "kebab-case":
        return "-".join(w.lower() for w in words)
    if case == "Title Case":
        return " ".join(w[:1].upper() + w[1:] for w in words)
    if case == "lowercase":
        return "".join(w.lower() for w in words)
    return s


def apply_style(spec: dict, prof: dict, cfg: dict) -> dict:
    """Apply house conventions learned from style examples. Only naming/structure conventions are applied;
    nothing (paths, schemas, texts, values) is copied from the examples. Every change is listed in x-style-applied."""
    conv = prof.get("conventions", {})
    scfg = (cfg.get("discovery", {}) or {}).get("style", {}) or {}
    applied = []
    oc = conv.get("operationIdCase")
    if scfg.get("operationIdCase", True) and oc in ("PascalCase", "camelCase", "snake_case", "kebab-case"):
        seen = set()
        for item in spec["paths"].values():
            for op in item.values():
                new = convert_case(op["operationId"], oc)
                while new in seen:
                    new += "2"
                seen.add(new)
                if new != op["operationId"]:
                    op.setdefault("x-original-operation-id", op["operationId"])
                    op["operationId"] = new
        applied.append(f"operationId case -> {oc}")
    tc = conv.get("tagCase")
    if scfg.get("tagCase", True) and tc in ("PascalCase", "camelCase", "kebab-case", "Title Case", "lowercase", "snake_case"):
        mp = {t["name"]: convert_case(t["name"], tc) for t in spec.get("tags", [])}
        for t in spec.get("tags", []):
            t["name"] = mp[t["name"]]
        for item in spec["paths"].values():
            for op in item.values():
                op["tags"] = [mp.get(t, convert_case(t, tc)) for t in op.get("tags", [])]
        applied.append(f"tag case -> {tc}")
    names = conv.get("securitySchemeNames") or {}
    schemes = spec.get("components", {}).get("securitySchemes", {})
    if scfg.get("securitySchemeNames", True) and schemes:
        ren = {}
        for k, s in list(schemes.items()):
            want = names.get(f"{s.get('type')}:{s.get('scheme') or s.get('in')}")
            if want and want != k and want not in schemes:
                schemes[want] = schemes.pop(k)
                ren[k] = want
        for item in spec["paths"].values():
            for op in item.values():
                if op.get("security"):
                    op["security"] = [{ren.get(k, k): v for k, v in x.items()} for x in op["security"]]
        if ren:
            applied.append(f"security scheme names {ren}")
    codes = conv.get("standardErrorResponses") or []
    if scfg.get("addStandardErrors", True) and codes:
        schemas = spec["components"]["schemas"]
        if "ProblemDetails" not in schemas:
            schemas["ProblemDetails"] = {"type": "object", "description": "RFC 7807 problem details.",
                                         "properties": {"type": {"type": "string"}, "title": {"type": "string"},
                                                        "status": {"type": "integer", "format": "int32"},
                                                        "detail": {"type": "string"}, "instance": {"type": "string"}},
                                         "x-source-project": "standard (RFC 7807)"}
        n = 0
        for path, item in spec["paths"].items():
            for op in item.values():
                secured = bool(op.get("security"))
                for c in codes:
                    if c in ("401", "403") and not secured:
                        continue
                    if c not in ("400", "401", "403", "404", "409", "422", "429", "500", "503", "default"):
                        continue
                    if c == "404" and "{" not in path:
                        continue
                    if c not in op["responses"]:
                        op["responses"][c] = {"description": STATUS_TEXT.get(c, "Error"),
                                              "content": {"application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetails"}}},
                                              "x-style-added": True}
                        n += 1
        if n:
            applied.append(f"{n} standard error responses ({', '.join(codes)}) added as ProblemDetails")
    info_cfg = (cfg.get("info") or {})
    for k in conv.get("requiredInfoFields") or []:
        if k in info_cfg and k not in spec["info"]:
            spec["info"][k] = info_cfg[k]
            applied.append(f"info.{k} from config")
    spec["info"]["x-style-applied"] = applied
    spec["info"]["x-style-examples"] = len(prof.get("examples", []))
    return spec


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def dump_yaml(obj, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(obj, f, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=True, width=120)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--dir", help="discovery output folder containing inventory.json")
    args = ap.parse_args()
    cfg = {}
    if args.config:
        cfg = yaml.safe_load(open(args.config, encoding="utf-8")) or {}
    base = Path(args.config).resolve().parent if args.config else Path.cwd()
    d = Path(args.dir) if args.dir else Path(cfg.get("discovery", {}).get("outputDir") or
                                             f"api-catalog/discovery/{cfg.get('region')}/{cfg.get('application')}")
    if not d.is_absolute():
        d = (base / d).resolve()
    inv = json.loads((d / "inventory.json").read_text(encoding="utf-8"))
    ov_path = d / "overrides.yaml"
    overrides = yaml.safe_load(ov_path.read_text(encoding="utf-8")) if ov_path.exists() else {}
    overrides = overrides or {}
    extra = []
    for f in overrides.get("extraTypeFiles", []) or []:
        fp = (d / f) if not Path(f).is_absolute() else Path(f)
        extra += json.loads(fp.read_text(encoding="utf-8")).get("types", [])
    overrides["_extraTypes"] = extra

    b = Builder(inv, overrides)
    spec = b.build(cfg)
    prof_p = d / "style-profile.json"
    if args.config:      # (re)learn conventions from the style example folders on every build
        from style_profile import example_folders, collect, build_profile
        folders = example_folders(cfg, base)
        ex = collect(folders)
        if ex:
            prof = build_profile(ex)
            prof["folders"] = [str(f) for f in folders if f.exists()]
            prof_p.write_text(json.dumps(prof, indent=2), encoding="utf-8")
        elif prof_p.exists():
            prof_p.unlink()
    if prof_p.exists():
        spec = apply_style(spec, json.loads(prof_p.read_text(encoding="utf-8")), cfg)
    if b.unresolved:
        spec["x-unresolved-types"] = {k: sorted(v) for k, v in sorted(b.unresolved.items())}
    dump_yaml(spec, d / "openapi.yaml")
    n_ops = sum(len(v) for v in spec["paths"].values())
    print(json.dumps({"output": str(d / "openapi.yaml"), "paths": len(spec["paths"]), "operations": n_ops,
                      "schemas": len(spec["components"]["schemas"]), "unresolvedTypes": sorted(b.unresolved)}, indent=2))


if __name__ == "__main__":
    main()
