"""
Core of the api-analysis skill. Pure functions, no I/O, so both analyze.py and
the regional-view skill can call run_analysis().

Input : a discovery OpenAPI document, the domain catalogue (domains.json) and the
        agent-maintained decisions.yaml.
Output: dict with the four artifacts
          enrichedSpec, domainsCapabilities, entitiesAttributes, duplicates
        plus a summary.
"""
from __future__ import annotations

import copy
import re
from collections import Counter, defaultdict

STOP = {"api", "v1", "v2", "v3", "v4", "by", "id", "ids", "the", "of", "and", "for", "a", "an", "to",
        "dto", "request", "response", "model", "result", "info", "details", "data", "item", "items", "fn"}
VERB_SYNONYMS = {
    "get": "get", "read": "get", "view": "get", "retrieve": "get", "fetch": "get", "show": "get",
    "list": "list", "search": "list", "find": "list", "query": "list", "browse": "list",
    "create": "create", "add": "create", "register": "create", "submit": "create", "new": "create",
    "post": "create", "issue": "create", "open": "create",
    "update": "update", "modify": "update", "edit": "update", "change": "update", "put": "update",
    "patch": "update", "maintain": "update", "manage": "update",
    "delete": "delete", "remove": "delete", "withdraw": "delete", "cancel": "delete", "close": "delete",
    "upload": "upload", "attach": "upload",
}
ACTION_VERBS = {
    "approve", "reject", "close", "reopen", "submit", "cancel", "search", "assign", "settle",
    "validate", "calculate", "renew", "export", "import", "quote", "bind", "issue", "endorse",
    "lapse", "reinstate", "transfer", "pay", "refund", "suspend", "activate", "deactivate",
    "archive", "restore", "publish", "notify", "verify", "complete", "escalate",
}
SUFFIXES = ["ViewModel", "Response", "Request", "Command", "Query", "Resource", "Details", "Detail",
            "Summary", "Entity", "Model", "Input", "Output", "Info", "Data", "Dto", "DTO", "Vm", "VM", "Payload"]
PREFIXES = ["Create", "Update", "Add", "Patch", "Upsert", "Get", "New", "Edit"]
ENVELOPE_HINT = re.compile(r"^(Paged|Paginated|Page|List|Collection|Envelope|ApiResponse|Result|Response)(Of|Result)?", re.I)
PROBLEM_SCHEMAS = {"ProblemDetails", "HttpValidationProblemDetails", "ValidationProblemDetails"}


# --------------------------------------------------------------------------- text
def split_words(s: str) -> list:
    s = re.sub(r"\{[^}]*\}", " ", s or "")
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)
    return [w.lower() for w in re.split(r"[^A-Za-z0-9]+", s) if w]


def singular(w: str) -> str:
    if len(w) <= 3:
        return w
    if w.endswith("ies"):
        return w[:-3] + "y"
    if w.endswith(("sses", "xes", "ches", "shes")):
        return w[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def tokens(s: str) -> set:
    return {singular(w) for w in split_words(s) if w not in STOP and not w.isdigit()}


def title(words) -> str:
    return " ".join(w[:1].upper() + w[1:] for w in words)


def plural(w: str) -> str:
    if w.endswith("y") and not w.endswith(("ay", "ey", "oy", "uy")):
        return w[:-1] + "ies"
    if w.endswith(("s", "x", "ch", "sh")):
        return w + "es"
    return w + "s"


def business_name(schema_name: str) -> str:
    n = re.sub(r"_[A-Za-z0-9]+$", "", schema_name)        # collision suffix from discovery
    n = re.sub(r"Of[A-Z].*$", "", n) if ENVELOPE_HINT.match(n) else n
    for _ in range(2):
        for s in SUFFIXES:
            if n.endswith(s) and len(n) > len(s) + 2:
                n = n[: -len(s)]
                break
    for p in PREFIXES:
        if n.startswith(p) and len(n) > len(p) + 2 and n[len(p)].isupper():
            n = n[len(p):]
            break
    return n


# --------------------------------------------------------------------------- spec helpers
def ref_name(s: dict):
    if not isinstance(s, dict):
        return None
    if "$ref" in s:
        return s["$ref"].split("/")[-1]
    for k in ("allOf", "oneOf", "anyOf"):
        if k in s and s[k]:
            for x in s[k]:
                r = ref_name(x)
                if r:
                    return r
    return None


def describe_type(s: dict) -> tuple:
    """-> (typeLabel, refName|None, isArray)"""
    if not isinstance(s, dict):
        return "any", None, False
    r = ref_name(s)
    if r:
        return r, r, False
    t = s.get("type")
    if t == "array":
        inner, ir, _ = describe_type(s.get("items", {}))
        return f"{inner}[]", ir, True
    if t == "object" and "additionalProperties" in s:
        inner, ir, _ = describe_type(s["additionalProperties"] if isinstance(s["additionalProperties"], dict) else {})
        return f"map<string,{inner}>", ir, True
    if s.get("format"):
        return f"{t}({s['format']})", None, False
    return t or "object", None, False


def schema_refs_deep(spec, name, seen=None) -> set:
    seen = seen if seen is not None else set()
    if name in seen:
        return seen
    seen.add(name)
    s = spec.get("components", {}).get("schemas", {}).get(name, {})
    for ps in (s.get("properties") or {}).values():
        _, r, _ = describe_type(ps)
        if r:
            schema_refs_deep(spec, r, seen)
    return seen


def iter_ops(spec):
    for path, item in (spec.get("paths") or {}).items():
        for m, op in item.items():
            if m.lower() in ("get", "post", "put", "patch", "delete", "head", "options"):
                yield path, m.upper(), op


def op_schema_usage(op) -> list:
    """[(schemaName, role)] directly referenced by an operation"""
    out = []
    for p in op.get("parameters", []) or []:
        _, r, _ = describe_type(p.get("schema", {}))
        if r:
            out.append((r, "parameter"))
    for ct in ((op.get("requestBody") or {}).get("content") or {}).values():
        _, r, _ = describe_type(ct.get("schema", {}))
        if r:
            out.append((r, "request"))
    for code, resp in (op.get("responses") or {}).items():
        for ct in (resp.get("content") or {}).values():
            _, r, _ = describe_type(ct.get("schema", {}))
            if r:
                out.append((r, "response" if str(code).startswith("2") else "error"))
    return out


def op_contract(op) -> dict:
    """Request / response / parameter contract of an operation (schema names), for lineage downstream."""
    req = None
    for ct, c in ((op.get("requestBody") or {}).get("content") or {}).items():
        t, r, arr = describe_type(c.get("schema", {}))
        req = {"contentType": ct, "schema": r, "type": t, "isArray": arr}
        if not r and isinstance(c.get("schema"), dict) and c["schema"].get("properties"):
            req["inline"] = c["schema"]
        break
    resps = {}
    for code, resp in (op.get("responses") or {}).items():
        content = resp.get("content") or {}
        if not content:
            resps[str(code)] = None
            continue
        for ct, c in content.items():
            t, r, arr = describe_type(c.get("schema", {}))
            resps[str(code)] = {"contentType": ct, "schema": r, "type": t, "isArray": arr}
            break
    params = []
    for p in op.get("parameters", []) or []:
        t, r, arr = describe_type(p.get("schema", {}))
        params.append({"name": p.get("name"), "in": p.get("in"), "required": bool(p.get("required")),
                       "type": t, "format": (p.get("schema") or {}).get("format", ""), "schema": r, "isArray": arr})
    return {"request": req, "responses": resps, "parameters": params,
            "security": [list(x.keys())[0] for x in (op.get("security") or []) if x]}


# --------------------------------------------------------------------------- domains
def filter_domains(domains_doc: dict, region: str, app: str) -> list:
    out = []
    for d in domains_doc.get("domains", []):
        if d.get("regions") and region not in d["regions"]:
            continue
        if d.get("applications") and app not in d["applications"]:
            continue
        d2 = copy.deepcopy(d)
        d2["capabilities"] = [c for c in d["capabilities"]
                              if (not c.get("regions") or region in c["regions"])
                              and (not c.get("applications") or app in c["applications"])]
        out.append(d2)
    return out


def domain_index(domains: list) -> dict:
    idx = {}
    for d in domains:
        strong = tokens(d["name"])
        for k in d.get("keywords", []):
            strong |= tokens(k)
        weak = set()
        for c in d.get("capabilities", []):
            weak |= tokens(c["name"])
            for k in c.get("keywords", []):
                weak |= tokens(k)
        weak -= strong
        weak = {w for w in weak if w not in VERB_SYNONYMS}
        idx[d["name"]] = {"strong": strong, "weak": weak}
    return idx


def op_tokens(path, method, op, spec) -> Counter:
    c = Counter()
    statics = [s for s in path.split("/") if s and not s.startswith("{")]
    for s in statics:
        for t in tokens(s):
            c[t] += 2
    for t in tokens(op.get("operationId", "")):
        c[t] += 1
    for tag in op.get("tags", []) or []:
        for t in tokens(tag):
            c[t] += 2
    for sname, role in op_schema_usage(op):
        for t in tokens(business_name(sname)):
            c[t] += 1
    for t in tokens(op.get("summary", "")):
        c[t] += 0.5
    return c


def score_domains(otoks: Counter, idx: dict) -> list:
    scores = []
    for name, kw in idx.items():
        s = sum(w for t, w in otoks.items() if t in kw["strong"]) + \
            0.5 * sum(w for t, w in otoks.items() if t in kw["weak"])
        scores.append((s, name))
    scores.sort(reverse=True)
    return scores


def derive_capability(path: str, method: str, op: dict) -> dict:
    segs = [s for s in path.split("/") if s]
    statics = [(i, s) for i, s in enumerate(segs) if not s.startswith("{") and s.lower() not in ("api", "fn") and not re.match(r"^v\d+$", s)]
    ends_with_param = bool(segs) and segs[-1].startswith("{")
    is_multipart = "multipart/form-data" in ((op.get("requestBody") or {}).get("content") or {})
    if not statics:
        return {"verb": method.lower(), "resource": "resource", "name": f"{title([method.lower()])} Resource"}
    last_i, last = statics[-1]
    last_words = split_words(last)
    if last.lower() in ACTION_VERBS and len(statics) > 1:
        res = singular(" ".join(split_words(statics[-2][1])))
        verb = last.lower()
        name = title([verb] + res.split())
        return {"verb": VERB_SYNONYMS.get(verb, verb), "resource": res, "name": name, "action": verb}
    res_words = [singular(w) for w in last_words]
    res = " ".join(res_words)
    if method == "GET":
        if ends_with_param:
            verb, name = "get", title(["get"] + res_words)
        else:
            verb, name = "list", title(["list"] + res_words[:-1] + [plural(res_words[-1])])
    elif method == "POST":
        verb = "upload" if is_multipart else "create"
        name = title([verb] + res_words)
    elif method in ("PUT", "PATCH"):
        verb, name = "update", title(["update"] + res_words)
    elif method == "DELETE":
        verb, name = "delete", title(["delete"] + res_words)
    else:
        verb, name = method.lower(), title([method.lower()] + res_words)
    return {"verb": verb, "resource": res, "name": name}


def cap_tokens(text_parts) -> set:
    out = set()
    for p in text_parts:
        for w in split_words(p):
            w = VERB_SYNONYMS.get(w, singular(w))
            if w not in STOP:
                out.add(w)
    return out


def match_capability(derived: dict, op: dict, domain: dict):
    d_toks = cap_tokens([derived["name"]])
    best, best_s = None, 0.0
    for c in domain.get("capabilities", []):
        c_name = cap_tokens([c["name"]])
        c_all = c_name | cap_tokens(c.get("keywords", []))
        inter = d_toks & c_all
        if not inter:
            continue
        verb_ok = derived["verb"] in c_all or derived.get("action", "") in c_all
        noun_ok = bool((d_toks - set(VERB_SYNONYMS.values())) & c_all)
        s = len(inter) / max(len(d_toks | c_name), 1) + (0.5 if verb_ok and noun_ok else 0)
        if s > best_s:
            best, best_s = c, s
    if best and best_s >= 0.75:
        return best, round(best_s, 2)
    return None, round(best_s, 2)


# --------------------------------------------------------------------------- main analysis
def run_analysis(spec: dict, domains_doc: dict, decisions: dict, cfg: dict | None = None) -> dict:
    cfg = cfg or {}
    acfg = cfg.get("analysis", {}) or {}
    decisions = decisions or {}
    region = spec.get("info", {}).get("x-region", cfg.get("region", "UNSPECIFIED"))
    app = spec.get("info", {}).get("x-application", cfg.get("application", "unknown"))
    domains = filter_domains(domains_doc, region, app)
    dom_by_name = {d["name"]: d for d in domains}
    idx = domain_index(domains)
    min_score = float(acfg.get("minDomainScore", 2))
    min_margin = float(acfg.get("minDomainMargin", 1))
    schemas = spec.get("components", {}).get("schemas", {}) or {}

    # decisions may use the operationId before house-style renaming (x-original-operation-id) - accept both
    alias = {}
    for _p, _m, _op in iter_ops(spec):
        if _op.get("x-original-operation-id"):
            alias[_op["x-original-operation-id"]] = _op.get("operationId")
    dec_assign = {alias.get(k, k): v for k, v in (decisions.get("domainAssignments", {}) or {}).items()}
    dec_unclass = {alias.get(x["operationId"], x["operationId"]): x for x in (decisions.get("acceptedUnclassified") or [])}
    dec_desc = decisions.get("descriptions", {}) or {}
    dec_names = decisions.get("entityNames", {}) or {}
    stale = []

    # ---------------- 1. operations -> domain / capability
    ops = []
    op_ids = set()
    for path, method, op in iter_ops(spec):
        oid = op.get("operationId") or f"{method} {path}"
        op_ids.add(oid)
        otoks = op_tokens(path, method, op, spec)
        scores = score_domains(otoks, idx)
        best_s, best_d = scores[0] if scores else (0, None)
        second_s = scores[1][0] if len(scores) > 1 else 0
        derived = derive_capability(path, method, op)
        rec = {"operationId": oid, "method": method, "path": path, "summary": op.get("summary", ""),
               "sourceProject": op.get("x-source-project", ""), "sourceFile": op.get("x-source-file", ""),
               "derivedCapability": derived["name"],
               "scores": {n: round(s, 2) for s, n in scores if s > 0}}
        rec.update(op_contract(op))
        if oid in dec_assign:
            da = dec_assign[oid] or {}
            rec.update(domain=da.get("domain"), assignment="decision", confidence="confirmed",
                       decisionNote=da.get("note", ""))
            if da.get("capability"):
                rec["capability"], rec["capabilityStatus"] = da["capability"], (
                    "catalogue" if da.get("domain") in dom_by_name and any(
                        c["name"] == da["capability"] for c in dom_by_name[da["domain"]]["capabilities"]) else "proposed")
        elif oid in dec_unclass:
            rec.update(domain=None, assignment="accepted-unclassified", confidence="confirmed",
                       decisionNote=dec_unclass[oid].get("reason", ""))
        elif best_s <= 0 or best_d is None:
            rec.update(domain=None, assignment="unclassified", confidence="none")
        else:
            conf = "high" if best_s >= min_score and best_s - second_s >= min_margin else "low"
            rec.update(domain=best_d, assignment="keyword", confidence=conf)
        if rec.get("domain") and "capability" not in rec:
            cap, cs = match_capability(derived, op, dom_by_name.get(rec["domain"], {}))
            if cap:
                rec["capability"], rec["capabilityStatus"], rec["capabilityScore"] = cap["name"], "catalogue", cs
            else:
                rec["capability"], rec["capabilityStatus"], rec["capabilityScore"] = derived["name"], "proposed", cs
        ops.append(rec)
    for oid in list(dec_assign) + list(dec_unclass):
        if oid not in op_ids:
            stale.append(f"decision references unknown operationId '{oid}'")

    op_by_id = {o["operationId"]: o for o in ops}

    # ---------------- 2. schema usage / roles
    usage = defaultdict(list)       # schema -> [(opId, role, direct)]
    for path, method, op in iter_ops(spec):
        oid = op.get("operationId") or f"{method} {path}"
        for sname, role in op_schema_usage(op):
            for s2 in schema_refs_deep(spec, sname):
                usage[s2].append((oid, role, s2 == sname))

    def schema_role(name, s):
        if name in PROBLEM_SCHEMAS or s.get("x-source-project") == "Microsoft.AspNetCore.Http":
            return "problem"
        if s.get("enum"):
            return "enum"
        props = s.get("properties") or {}
        arr_props = [p for p, ps in props.items() if (ps.get("type") == "array")]
        if ENVELOPE_HINT.match(name) and arr_props and len(props) <= 6 and any(
                k.lower() in ("page", "pagesize", "totalcount", "total", "count", "pagenumber", "nextpagetoken", "continuationtoken")
                for k in props):
            return "envelope"
        roles = {r for _, r, _ in usage.get(name, [])}
        if roles <= {"request", "parameter"} and roles:
            return "request"
        if roles <= {"response"} and roles:
            return "response"
        if roles <= {"error"} and roles:
            return "error"
        return "shared" if roles else "unused"

    roles = {n: schema_role(n, s) for n, s in schemas.items()}

    # ---------------- 3. duplicates
    def fp_props(s):
        out = set()
        for pn, ps in (s.get("properties") or {}).items():
            tl, r, arr = describe_type(ps)
            if r:
                tl = ("[]" if arr else "") + "ref:" + business_name(r).lower()
            out.add((pn.lower(), tl))
        return out

    cand_names = [n for n in schemas if roles[n] not in ("problem", "envelope")]
    fps = {n: (frozenset(fp_props(schemas[n])) if roles[n] != "enum" else frozenset(("enum", v) for v in schemas[n]["enum"]))
           for n in cand_names}
    exact_groups = defaultdict(list)
    for n in cand_names:
        if len(fps[n]) >= 2:
            exact_groups[(roles[n] == "enum", fps[n])].append(n)
    groups = []
    grouped = set()
    for (_, _fp), members in exact_groups.items():
        if len(members) > 1:
            groups.append({"members": sorted(members), "match": "exact", "similarity": 1.0})
            grouped |= set(members)
    near_thr = float(acfg.get("nearDuplicateThreshold", 0.8))
    names_sorted = sorted(n for n in cand_names if roles[n] != "enum")
    for i, a in enumerate(names_sorted):
        for b in names_sorted[i + 1:]:
            if {a, b} <= grouped and any({a, b} <= set(g["members"]) for g in groups):
                continue
            pa = {p for p, _ in fps[a]}
            pb = {p for p, _ in fps[b]}
            if len(pa) < 3 or len(pb) < 3:
                continue
            inter = pa & pb
            jac = len(inter) / len(pa | pb)
            cont = len(inter) / min(len(pa), len(pb))
            same_biz = business_name(a).lower() == business_name(b).lower()
            if (cont >= near_thr and len(inter) >= 3) or jac >= 0.75 or (same_biz and jac >= 0.4):
                groups.append({"members": [a, b], "match": "near", "similarity": round(max(jac, cont), 2),
                               "jaccard": round(jac, 2), "containment": round(cont, 2),
                               "sharedAttributes": sorted(inter), "onlyIn": {a: sorted(pa - pb), b: sorted(pb - pa)}})

    # apply decisions
    dec_dups = decisions.get("duplicates", []) or []
    for g in groups:
        g["decision"] = "merge" if g["match"] == "exact" else "undecided"
        g["decisionSource"] = "auto-exact" if g["match"] == "exact" else None
        for dd in dec_dups:
            dm = set(dd.get("members", []))
            if set(g["members"]) <= dm or dm <= set(g["members"]) and len(dm) >= 2:
                g["decision"] = dd.get("decision", "merge")
                g["decisionSource"] = "decision"
                g["note"] = dd.get("note", "")
                if dd.get("canonical"):
                    g["canonical"] = dd["canonical"]
    for dd in dec_dups:
        for m in dd.get("members", []):
            if m not in schemas:
                stale.append(f"duplicate decision references unknown schema '{m}'")

    # union-find merges
    parent = {n: n for n in schemas}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for g in groups:
        if g["decision"] == "merge":
            ms = g["members"]
            for m in ms[1:]:
                parent[find(m)] = find(ms[0])
    clusters = defaultdict(list)
    for n in schemas:
        clusters[find(n)].append(n)

    # canonical names
    canon_of = {}
    used_names = Counter()
    cluster_canon = {}
    for root, members in clusters.items():
        members.sort()
        explicit = None
        for g in groups:
            if g.get("canonical") and set(g["members"]) & set(members) and g["decision"] == "merge":
                explicit = g["canonical"]
        if explicit:
            cname = explicit
        elif len(members) == 1:
            cname = dec_names.get(members[0]) or members[0]
        else:
            bn = Counter(business_name(m) for m in members).most_common(1)[0][0]
            cname = dec_names.get(members[0]) or bn
        cluster_canon[root] = cname
        used_names[cname] += 1
    # business-name renaming for singletons when unique
    if acfg.get("useBusinessNames", True):
        all_bn = Counter(business_name(m[0]) for r, m in clusters.items() if len(m) == 1)
        for root, members in clusters.items():
            if len(members) == 1 and members[0] not in dec_names and roles[members[0]] not in ("request",):
                bn = business_name(members[0])
                if bn != members[0] and all_bn[bn] == 1 and used_names[bn] == 0 and bn not in schemas:
                    used_names[cluster_canon[root]] -= 1
                    cluster_canon[root] = bn
                    used_names[bn] += 1
    for root, members in clusters.items():
        for m in members:
            canon_of[m] = cluster_canon[root]

    # ---------------- 4. entities
    def op_domains(oids):
        c = Counter(op_by_id[o]["domain"] for o in oids if o in op_by_id and op_by_id[o].get("domain"))
        return c

    entities = {}
    for root, members in clusters.items():
        cname = cluster_canon[root]
        mem_roles = {roles[m] for m in members}
        if mem_roles <= {"problem", "envelope"}:
            continue
        attrs = {}
        for m in members:
            s = schemas[m]
            req = set(s.get("required", []) or [])
            for pn, ps in (s.get("properties") or {}).items():
                tl, r, arr = describe_type(ps)
                desc = dec_desc.get(f"{m}.{pn}") or dec_desc.get(f"{cname}.{pn}") or ps.get("description", "")
                if pn not in attrs:
                    attrs[pn] = {"name": pn, "type": tl if not r else ("array" if arr else "object"),
                                 "format": ps.get("format", ""), "refEntity": canon_of.get(r) if r else None,
                                 "isCollection": arr, "required": pn in req,
                                 "nullable": bool(ps.get("nullable")), "description": desc,
                                 "enum": schemas.get(r, {}).get("enum") if r and roles.get(r) == "enum" else None,
                                 "constraints": {k: ps[k] for k in ("maxLength", "minLength", "pattern", "minimum", "maximum") if k in ps},
                                 "presentIn": [m]}
                else:
                    attrs[pn]["presentIn"].append(m)
                    attrs[pn]["required"] = attrs[pn]["required"] or pn in req
                    if not attrs[pn]["description"] and desc:
                        attrs[pn]["description"] = desc
        if len(members) > 1:
            for a in attrs.values():
                a["inAllVariants"] = len(a["presentIn"]) == len(members)
        used = [u for m in members for u in usage.get(m, [])]
        oids = sorted({u[0] for u in used})
        dc = op_domains(oids)
        desc = dec_desc.get(cname) or next((dec_desc.get(m) for m in members if dec_desc.get(m)), None) or \
            next((schemas[m].get("description") for m in members if schemas[m].get("description")), "")
        entities[cname] = {
            "name": cname,
            "kind": "enum" if mem_roles == {"enum"} else "object",
            "roles": sorted(mem_roles),
            "description": desc or "",
            "domain": dc.most_common(1)[0][0] if dc else None,
            "sharedWithDomains": sorted(d for d in dc if dc and d != dc.most_common(1)[0][0]),
            "schemaNames": members,
            "sourceProjects": sorted({schemas[m].get("x-source-project", "") for m in members}),
            "sourceFiles": sorted({f"{schemas[m].get('x-source-file', '')}:{schemas[m].get('x-source-line', '')}" for m in members}),
            "enumValues": schemas[members[0]].get("enum") if mem_roles == {"enum"} else None,
            "attributes": list(attrs.values()),
            "usedBy": [{"operationId": o, "method": op_by_id[o]["method"], "path": op_by_id[o]["path"],
                        "roles": sorted({u[1] for u in used if u[0] == o}),
                        "direct": any(u[2] for u in used if u[0] == o)} for o in oids if o in op_by_id],
        }

    # relations
    relations = []
    ent_bn = {business_name(n).lower(): n for n in entities}
    ent_lower = {n.lower(): n for n in entities}
    for en, e in entities.items():
        for a in e["attributes"]:
            if a["refEntity"] and a["refEntity"] in entities and entities[a["refEntity"]]["kind"] != "enum":
                relations.append({"from": en, "to": a["refEntity"], "type": "has-many" if a["isCollection"] else "has-one",
                                  "via": a["name"], "cardinality": "0..*" if a["isCollection"] else ("1" if a["required"] else "0..1")})
            elif a["refEntity"] and a["refEntity"] in entities:
                relations.append({"from": en, "to": a["refEntity"], "type": "uses-enum", "via": a["name"],
                                  "cardinality": "1" if a["required"] and not a["nullable"] else "0..1"})
            else:
                m = re.match(r"^(.+?)(Id|ID|Number|Code|Ref|Reference)$", a["name"])
                if m and m.group(1).lower() not in ("", en.lower(), business_name(en).lower()):
                    target = ent_lower.get(m.group(1).lower()) or ent_bn.get(m.group(1).lower())
                    if target and target != en:
                        relations.append({"from": en, "to": target, "type": "references", "via": a["name"],
                                          "cardinality": "0..1"})

    # trees
    def tree(name, depth, path):
        e = entities.get(name)
        if not e:
            return None
        node = {"entity": name, "kind": e["kind"], "attributes": []}
        if e["kind"] == "enum":
            node["values"] = e["enumValues"]
            return node
        for a in e["attributes"]:
            an = {"name": a["name"], "type": a["type"], "required": a["required"], "description": a["description"]}
            if a["format"]:
                an["format"] = a["format"]
            if a["refEntity"]:
                an["refEntity"] = a["refEntity"]
                if a["isCollection"]:
                    an["collection"] = True
                if a["refEntity"] in path:
                    an["cycle"] = True
                elif depth < int(acfg.get("treeDepth", 4)):
                    child = tree(a["refEntity"], depth + 1, path | {a["refEntity"]})
                    if child:
                        an["children"] = child
            node["attributes"].append(an)
        return node

    for en, e in entities.items():
        e["tree"] = tree(en, 1, {en}) if e["kind"] == "object" else None

    # ---------------- 5. enriched spec
    enr = copy.deepcopy(spec)
    dom_tags = {}
    for path, method, op in iter_ops(enr):
        oid = op.get("operationId") or f"{method} {path}"
        rec = op_by_id[oid]
        orig = op.get("tags", [])
        if rec.get("domain"):
            op["x-original-tags"] = orig
            op["tags"] = [rec["domain"]]
            op["x-domain"] = rec["domain"]
            op["x-capability"] = rec.get("capability")
            op["x-capability-status"] = rec.get("capabilityStatus")
            op["x-domain-confidence"] = rec["confidence"]
            dom_tags[rec["domain"]] = dom_by_name.get(rec["domain"], {}).get("description", "")
        else:
            op["x-domain"] = None
            op["x-original-tags"] = orig
            op["tags"] = ["Unclassified"]
            dom_tags["Unclassified"] = "Operations not mapped to a business domain"
        if not op.get("summary") and rec.get("capability"):
            op["summary"] = rec["capability"]
    for n, s in enr.get("components", {}).get("schemas", {}).items():
        cname = canon_of.get(n)
        if cname and cname in entities:
            s["x-entity"] = cname
            if entities[cname]["domain"]:
                s["x-domain"] = entities[cname]["domain"]
            if len(entities[cname]["schemaNames"]) > 1:
                s["x-duplicate-of"] = cname
        if dec_desc.get(n) and not s.get("description"):
            s["description"] = dec_desc[n]
        for pn, ps in (s.get("properties") or {}).items():
            d = dec_desc.get(f"{n}.{pn}") or (dec_desc.get(f"{cname}.{pn}") if cname else None)
            if d and not ps.get("description"):
                ps["description"] = d
    enr["tags"] = [{"name": n, "description": d} for n, d in sorted(dom_tags.items())]
    enr["info"]["x-domains"] = sorted(n for n in dom_tags if n != "Unclassified")
    enr["info"]["x-enriched-by"] = "api-analysis skill"

    def envelope_info(n):
        if roles.get(n) != "envelope":
            return {}
        props = schemas[n].get("properties") or {}
        info = {"itemsProperty": None, "itemsSchema": None, "otherProperties": {}}
        for pn, ps in props.items():
            t, r, arr = describe_type(ps)
            if arr and r and not info["itemsSchema"]:
                info["itemsProperty"], info["itemsSchema"] = pn, r
            else:
                info["otherProperties"][pn] = {"type": t, "format": ps.get("format", "")}
        return info

    # ---------------- 6. assemble artifacts
    dc_out = {}
    for o in ops:
        dname = o.get("domain") or "Unclassified"
        d = dc_out.setdefault(dname, {"domain": dname, "description": dom_by_name.get(dname, {}).get("description", ""),
                                      "inCatalogue": dname in dom_by_name, "capabilities": {}})
        cname = o.get("capability") or o["derivedCapability"]
        c = d["capabilities"].setdefault(cname, {
            "name": cname, "status": o.get("capabilityStatus", "n/a"),
            "description": next((c["description"] for c in dom_by_name.get(dname, {}).get("capabilities", []) if c["name"] == cname), ""),
            "operations": []})
        c["operations"].append({k: o[k] for k in ("operationId", "method", "path", "summary", "assignment", "confidence", "sourceProject")})
    for dname, d in dc_out.items():
        d["catalogueCapabilitiesNotImplemented"] = [c["name"] for c in dom_by_name.get(dname, {}).get("capabilities", [])
                                                    if c["name"] not in d["capabilities"]]
        d["capabilities"] = list(d["capabilities"].values())
        ents = sorted(n for n, e in entities.items() if e["domain"] == dname)
        d["entities"] = ents

    dup_groups_out = []
    for g in groups:
        rec = dict(g)
        rec["canonical"] = canon_of.get(g["members"][0]) if g["decision"] == "merge" else None
        rec["memberDetails"] = [{
            "schema": m, "role": roles[m], "sourceProject": schemas[m].get("x-source-project", ""),
            "sourceFile": f"{schemas[m].get('x-source-file', '')}:{schemas[m].get('x-source-line', '')}",
            "usedBy": sorted({f"{op_by_id[u[0]]['method']} {op_by_id[u[0]]['path']}" for u in usage.get(m, []) if u[0] in op_by_id}),
        } for m in g["members"]]
        dup_groups_out.append(rec)
    merged_roots = {r for r, ms in clusters.items() if len(ms) > 1}
    mapping = {m: canon_of[m] for m in schemas if find(m) in merged_roots and canon_of.get(m) in entities}
    renames = {m: canon_of[m] for m in schemas if canon_of.get(m) in entities and canon_of[m] != m and m not in mapping}

    summary = {
        "region": region, "application": app,
        "operations": len(ops),
        "domainsUsed": sorted({o["domain"] for o in ops if o.get("domain")}),
        "unclassifiedOperations": sum(1 for o in ops if o["assignment"] == "unclassified"),
        "lowConfidenceOperations": sum(1 for o in ops if o.get("confidence") == "low"),
        "capabilities": sum(len(d["capabilities"]) for d in dc_out.values()),
        "proposedCapabilities": sum(1 for d in dc_out.values() for c in d["capabilities"] if c["status"] == "proposed"),
        "schemas": len(schemas),
        "entities": len(entities),
        "relations": len(relations),
        "duplicateGroups": len(groups),
        "undecidedDuplicateGroups": sum(1 for g in groups if g["decision"] == "undecided"),
        "schemasMerged": len(mapping), "schemasRenamed": len(renames),
        "staleDecisions": stale,
    }
    return {
        "enrichedSpec": enr,
        "domainsCapabilities": {"region": region, "application": app, "domains": list(dc_out.values()), "operations": ops},
        "entitiesAttributes": {"region": region, "application": app, "entities": list(entities.values()),
                               "relations": relations, "schemaToEntity": {m: canon_of[m] for m in schemas if canon_of.get(m) in entities},
                               "excludedSchemas": [{"schema": n, "reason": roles[n], **envelope_info(n)} for n in schemas
                                                   if roles[n] in ("problem", "envelope") and canon_of.get(n) not in entities]},
        "duplicates": {"region": region, "application": app, "groups": dup_groups_out, "mapping": mapping},
        "summary": summary,
    }
