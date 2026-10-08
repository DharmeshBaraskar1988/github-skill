"""
Alignment engine: regional entities / attributes / endpoints / domains  vs  reference models
(a baseline canonical model, e.g. EU, and/or an ACORD export).

Pure functions; align.py does the I/O. Everything the engine decides is explainable: each match carries
name similarity, type compatibility and the attributes that matched or not, so reviewers can judge it.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
from collections import Counter, defaultdict

# ----------------------------------------------------------------------------- vocabulary
# Generic English / insurance vocabulary. Extend per organisation in synonyms.yaml (words / compounds / entities).
WORD_SYN = {
    "id": "identifier", "ident": "identifier", "ref": "identifier", "no": "number", "num": "number", "nbr": "number",
    "dt": "date", "amt": "amount", "desc": "description", "addr": "address", "post": "postal", "zip": "postal",
    "tel": "phone", "telephone": "phone", "mobile": "phone", "cell": "phone", "qty": "quantity", "pct": "percent",
    "inception": "effective", "start": "effective", "expiry": "expiration", "end": "expiration", "expire": "expiration",
    "valid": "expiration", "until": "", "created": "creation", "modified": "update", "updated": "update",
    "dob": "birthdate", "insured": "party", "cust": "customer", "org": "organisation", "organization": "organisation",
    "doc": "document", "size": "size", "bytes": "", "mime": "mime",
}
COMPOUND_SYN = {
    "emailaddress": "email", "email": "email", "mail": "email",
    "firstname": "givenname", "forename": "givenname", "givenname": "givenname",
    "lastname": "surname", "familyname": "surname", "surname": "surname",
    "dateofbirth": "birthdate", "birthdate": "birthdate",
    "postalcode": "postalcode", "postcode": "postalcode", "zipcode": "postalcode", "postal": "postalcode",
    "line1": "line1", "addressline1": "line1", "street": "line1", "line2": "line2", "addressline2": "line2",
    "country": "country", "countrycode": "country", "currency": "currency", "currencycode": "currency",
    "sizebyte": "filesize", "size": "filesize", "filesize": "filesize", "filelength": "filesize",
    "contenttype": "mimetype", "mimetype": "mimetype", "mediatype": "mimetype",
    "lossdatetime": "lossdate", "lossdate": "lossdate", "occurrencedate": "lossdate",
    "location": "losslocation", "losslocation": "losslocation", "lossaddress": "losslocation",
    "description": "description", "lossdescription": "description", "narrative": "description",
    "holder": "policyholder", "policyholder": "policyholder",
}
ENTITY_SYN = {
    "money": "monetaryamount", "amount": "monetaryamount", "monetaryamount": "monetaryamount",
    "claimant": "claimparty", "claimparty": "claimparty",
    "policyholder": "party", "customer": "party", "person": "party", "insured": "party", "party": "party",
    "attachment": "document", "file": "document",
}
SOFT_TOKENS = {"code", "cd", "value", "info", "data", "text"}
STOP = {"the", "of", "and", "a", "an", "dto", "model", "entity", "request", "response"}


def split_words(s: str) -> list:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s or "")
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)
    s = re.sub(r"([A-Za-z])(\d)", r"\1 \2", s)
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


def plural(w: str) -> str:
    if w.endswith("y") and not w.endswith(("ay", "ey", "oy", "uy")):
        return w[:-1] + "ies"
    if w.endswith(("s", "x", "ch", "sh")):
        return w + "es"
    return w + "s"


class Vocab:
    def __init__(self, extra: dict | None = None):
        extra = extra or {}
        self.words = dict(WORD_SYN, **{k.lower(): v.lower() for k, v in (extra.get("words") or {}).items()})
        self.compounds = dict(COMPOUND_SYN, **{k.lower(): v.lower() for k, v in (extra.get("compounds") or {}).items()})
        self.entities = dict(ENTITY_SYN, **{k.lower(): v.lower() for k, v in (extra.get("entities") or {}).items()})

    def tokens(self, s: str) -> list:
        out = []
        for w in split_words(s):
            w = singular(w)
            w = self.words.get(w, w)
            if w and w not in STOP:
                out.append(w)
        return out

    def ent_key(self, name: str) -> str:
        name = re.sub(r"_?Type$", "", name or "")
        j = "".join(singular(w) for w in split_words(name) if w not in STOP)
        return self.entities.get(j, j)

    def attr_key(self, name: str, entity_names=()) -> tuple:
        """-> (compoundKey, tokenSet) after removing tokens of the owning entity name and soft tokens."""
        toks = self.tokens(name)
        ent_toks = set()
        for en in entity_names:
            ent_toks |= set(self.tokens(en))
        stripped = [t for t in toks if t not in ent_toks] or toks
        soft = [t for t in stripped if t not in SOFT_TOKENS] or stripped
        joined = "".join(soft)
        joined_full = "".join(stripped)
        key = self.compounds.get(joined) or self.compounds.get(joined_full) or self.compounds.get("".join(toks)) or joined
        return key, set(soft)


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def base_type(t: str) -> str:
    return (t or "").split("(")[0].strip().lower()


def basis_hash(*parts) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:10]


# ----------------------------------------------------------------------------- regional clusters
def build_clusters(data: dict, scope: dict, overrides: dict) -> tuple:
    """Group the same entity across applications of the scope into one regional entity.
    Uses cross-app duplicate findings (exact / same-name) + overrides.clusters. -> (clusters, appEntityToCluster)"""
    apps_in = set(scope["appIds"])
    ents = [e for e in data["entities"] if e["appId"] in apps_in]
    key = lambda e: f"{e['appId']}:{e['name']}"  # noqa: E731
    parent = {key(e): key(e) for e in ents}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        if a in parent and b in parent:
            parent[find(a)] = find(b)

    separate = set()
    for c in overrides.get("clusters", []) or []:
        if c.get("decision") == "separate":
            ms = c.get("members", [])
            for i, a in enumerate(ms):
                for b in ms[i + 1:]:
                    separate.add(frozenset((a, b)))
    for x in data.get("crossAppDuplicates", []):
        a, b = f"{x['a']['appId']}:{x['a']['entity']}", f"{x['b']['appId']}:{x['b']['entity']}"
        if x["match"] in ("exact", "same-name") and frozenset((a, b)) not in separate:
            union(a, b)
    by_name = defaultdict(list)
    for e in ents:
        by_name[(e["name"], e["kind"])].append(key(e))
    for (_, _k), ks in by_name.items():
        for k in ks[1:]:
            if frozenset((ks[0], k)) not in separate:
                union(ks[0], k)
    forced_names = {}
    for c in overrides.get("clusters", []) or []:
        if c.get("decision") == "merge":
            ms = [m for m in c.get("members", []) if m in parent]
            for m in ms[1:]:
                union(ms[0], m)
            if c.get("name") and ms:
                forced_names[find(ms[0])] = c["name"]
    groups = defaultdict(list)
    by_key = {key(e): e for e in ents}
    for k in parent:
        groups[find(k)].append(by_key[k])

    clusters, a2c, used = [], {}, Counter()
    for root, members in groups.items():
        cnt = Counter(m["name"] for m in members)
        top = max(cnt.values())
        name = forced_names.get(find(root)) or sorted((n for n, k in cnt.items() if k == top),
                                                      key=lambda n: (len(re.sub(r"(Info|Details|Data|Dto)$", "", n)), n))[0]
        used[name] += 1
        if used[name] > 1:
            name = f"{name}{used[name]}"
        for m in members:
            a2c[key(m)] = name
        clusters.append({"name": name, "members": members})

    out = []
    for c in clusters:
        ms = c["members"]
        attrs = {}
        for m in ms:
            for a in m["attributes"]:
                k = a["name"].lower()
                ref = a2c.get(f"{m['appId']}:{a['refEntity']}") if a.get("refEntity") else None
                if k not in attrs:
                    attrs[k] = {"name": a["name"], "type": a["type"], "format": a.get("format") or "",
                                "refEntity": ref, "isCollection": bool(a.get("isCollection")),
                                "required": bool(a.get("required")), "nullable": bool(a.get("nullable")),
                                "description": a.get("description") or "", "enum": a.get("enum"),
                                "sources": []}
                at = attrs[k]
                at["required"] = at["required"] or bool(a.get("required"))
                if not at["description"] and a.get("description"):
                    at["description"] = a["description"]
                if base_type(at["type"]) != base_type(a["type"]) and not at.get("typeConflict"):
                    at["typeConflict"] = f"{at['type']} vs {a['type']} ({m['appId']})"
                at["sources"].append({"appId": m["appId"], "entity": m["name"],
                                      "schemas": a.get("presentIn") or m["schemaNames"], "attribute": a["name"]})
        dom = Counter(m["domain"] for m in ms if m.get("domain")).most_common(1)
        usage = []
        for m in ms:
            for u in m.get("usage", []):
                usage.append({"appId": m["appId"], "operationId": u["operationId"], "roles": u.get("roles", []),
                              "direct": u.get("direct", True)})
        kind = ms[0]["kind"]
        enum_vals = []
        if kind == "enum":
            for m in ms:
                for v in m.get("enumValues") or []:
                    if v not in enum_vals:
                        enum_vals.append(v)
        out.append({
            "name": c["name"], "kind": kind, "domain": dom[0][0] if dom else "",
            "description": next((m["description"] for m in ms if m.get("description")), ""),
            "roles": sorted({r for m in ms for r in m.get("roles", [])}),
            "members": [{"appId": m["appId"], "entity": m["name"], "schemas": m["schemaNames"],
                         "sourceProjects": m.get("sourceProjects", [])} for m in ms],
            "apps": sorted({m["appId"] for m in ms}),
            "attributes": list(attrs.values()), "enumValues": enum_vals, "usage": usage,
        })
    return out, a2c


# ----------------------------------------------------------------------------- matching
class Matcher:
    def __init__(self, refs: list, vocab: Vocab, cfg: dict):
        self.v = vocab
        self.cfg = cfg
        self.ref_entities = []
        for r in refs:
            for e in r["entities"]:
                e2 = dict(e)
                e2["_source"] = r.get("source", "acord")
                e2["_refName"] = r.get("name", "")
                e2["_allAttrs"] = list(e.get("attributes", [])) + list(e.get("inheritedAttributes", []))
                self.ref_entities.append(e2)
        self.ref_by_name = {}
        for e in self.ref_entities:
            self.ref_by_name.setdefault(e["name"], e)
        self.best_ref_of_cluster = {}

    def name_sim(self, ours: str, ref: dict) -> float:
        k1 = self.v.ent_key(ours)
        names = [ref["name"]] + list(ref.get("synonyms") or []) + ([ref["referenceEntity"]] if ref.get("referenceEntity") else [])
        best = 0.0
        for n in names:
            k2 = self.v.ent_key(n)
            if k1 == k2:
                return 1.0
            t1, t2 = set(self.v.tokens(ours)), set(self.v.tokens(n))
            s = jaccard(t1, t2)
            if t2 and t2 <= t1:
                s = max(s, 0.8)
            elif t1 and t1 <= t2:
                s = max(s, 0.7)
            best = max(best, s)
        return best

    def type_compat(self, a: dict, r: dict) -> float:
        a_ref, r_ref = a.get("refEntity"), r.get("refEntity")
        if a_ref and r_ref:
            known = self.best_ref_of_cluster.get(a_ref)
            if known:
                return 1.0 if known == r_ref else 0.4
            return 0.9 if self.v.ent_key(a_ref) == self.v.ent_key(r_ref) else 0.6
        if a_ref and r.get("codeValues"):
            return 0.8
        if bool(a_ref) != bool(r_ref):
            return 0.1
        ta, tr = base_type(a["type"]), base_type(r["type"])
        fa, fr = (a.get("format") or ""), (r.get("format") or "")
        if a.get("isCollection") != r.get("isCollection"):
            return 0.3
        if ta == tr:
            if fa == fr or not fa or not fr:
                return 1.0
            if {fa, fr} <= {"date", "date-time"}:
                return 0.7
            if {fa, fr} <= {"int32", "int64", "double", "float"}:
                return 0.9
            if ta == "string":
                return 0.85
            return 0.8
        if {ta, tr} == {"integer", "number"}:
            return 0.8
        return 0.2

    def match_attrs(self, ours_e: dict, ref_e: dict, forced: dict) -> list:
        ours = ours_e["attributes"]
        refs = ref_e["_allAttrs"]
        o_names = [ours_e["name"]] + [m["entity"] for m in ours_e.get("members", [])]
        r_names = [ref_e["name"]]
        pairs = []
        okeys = [self.v.attr_key(a["name"], o_names) for a in ours]
        rkeys = [self.v.attr_key(r["name"], r_names) for r in refs]
        for i, a in enumerate(ours):
            for j, r in enumerate(refs):
                ka, ta = okeys[i]
                kr, tr = rkeys[j]
                syn = [self.v.compounds.get(x.lower()) for x in (r.get("synonyms") or [])]
                if ka == kr or ka in syn:
                    sim = 1.0
                else:
                    sim = jaccard(ta, tr)
                    if ta and tr and (ta <= tr or tr <= ta):
                        sim = max(sim, 0.6)
                comp = self.type_compat(a, r)
                if a.get("refEntity") and r.get("refEntity") and comp >= 1.0 and \
                        bool(a.get("isCollection")) == bool(r.get("isCollection")):
                    sim = max(sim, 0.6)      # both point to the same (aligned) entity: strong structural evidence
                ok = sim >= 0.75 or (sim >= 0.5 and comp >= 0.9)
                if ok:
                    raw = jaccard(set(self.v.tokens(a["name"])), set(self.v.tokens(r["name"])))
                    pairs.append((0.75 * sim + 0.25 * comp, raw, sim, comp, i, j))
        pairs.sort(reverse=True)
        used_o, used_r, res = set(), set(), {}
        for i, a in enumerate(ours):
            f = forced.get(a["name"])
            if f is not None:
                j = next((j for j, r in enumerate(refs) if r["name"] == f), None) if f else None
                used_o.add(i)
                if j is not None:
                    used_r.add(j)
                    comp = self.type_compat(a, refs[j])
                    res[i] = (1.0, 1.0, comp, j, "override")
                else:
                    res[i] = None
        for score, _raw, sim, comp, i, j in pairs:
            if i in used_o or j in used_r:
                continue
            used_o.add(i)
            used_r.add(j)
            res[i] = (score, sim, comp, j, "auto")
        out = []
        for i, a in enumerate(ours):
            m = res.get(i)
            if not m:
                out.append({"name": a["name"], "status": "no-match", "reference": None, "score": 0.0})
                continue
            score, sim, comp, j, how = m
            r = refs[j]
            status = "match" if sim >= 0.9 and comp >= 0.9 else ("type-conflict" if comp < 0.7 else "similar")
            out.append({"name": a["name"], "status": status, "reference": r["name"], "score": round(score, 3),
                        "nameSimilarity": round(sim, 2), "typeCompatibility": round(comp, 2), "how": how,
                        "referenceType": (("list of " if r.get("isCollection") else "") + r["refEntity"]) if r.get("refEntity")
                        else (r["type"] + (f"({r['format']})" if r.get("format") else "")),
                        "referenceRequired": bool(r.get("required")), "referenceDescription": r.get("description", ""),
                        "referenceInherited": bool(r.get("inherited")), "referenceCodeValues": r.get("codeValues") or []})
        return out

    def score_entity(self, ours: dict, ref: dict, forced_attrs: dict) -> dict:
        ns = self.name_sim(ours["name"], ref)
        if ours["kind"] == "enum" or ref.get("kind") == "enum":
            if ours["kind"] != ref.get("kind"):
                return None
            ov = {"".join(self.v.tokens(x)) for x in ours["enumValues"]}
            rv = {"".join(self.v.tokens(x)) for x in ref.get("codeValues", [])}
            cov = len(ov & rv) / len(ov) if ov else 0
            score = 0.4 * ns + 0.6 * cov
            return {"reference": ref["name"], "source": ref["_source"], "score": round(min(1.0, score), 3),
                    "nameSimilarity": round(ns, 2), "coverage": round(cov, 2),
                    "valueMatches": sorted(ov & rv), "valuesOnlyOurs": sorted(ov - rv), "valuesOnlyReference": sorted(rv - ov),
                    "typeConflicts": 0, "attributes": []}
        attrs = self.match_attrs(ours, ref, forced_attrs)
        n = len(attrs)
        matched = [a for a in attrs if a["status"] != "no-match"]
        cov = len(matched) / n if n else 0.0
        q = sum(a["score"] for a in matched) / len(matched) if matched else 0.0
        conflicts = sum(1 for a in matched if a["status"] == "type-conflict")
        score = 0.3 * ns + 0.7 * cov * q
        if ref["_source"] == "baseline":
            score += float(self.cfg.get("baselinePreference", 0.05))
        ref_cov = len(matched) / len(ref["_allAttrs"]) if ref["_allAttrs"] else 0
        return {"reference": ref["name"], "source": ref["_source"], "score": round(min(1.0, score), 3),
                "nameSimilarity": round(ns, 2), "coverage": round(cov, 2), "referenceCoverage": round(ref_cov, 2),
                "typeConflicts": conflicts, "attributes": attrs}

    def candidates(self, ours: dict, forced_attrs: dict, top=3) -> list:
        res = []
        for ref in self.ref_entities:
            s = self.score_entity(ours, ref, forced_attrs)
            if s and (s["score"] > 0.15 or s["nameSimilarity"] >= 0.5):
                res.append(s)
        res.sort(key=lambda x: (-x["score"], x["source"] != "baseline"))
        return res[:top]


def classify(best: dict | None, cfg: dict) -> tuple:
    full_t = float(cfg.get("fullMatchThreshold", 0.8))
    part_t = float(cfg.get("partialMatchThreshold", 0.45))
    if not best or best["score"] < part_t:
        return "none", "custom"
    full = best["score"] >= full_t and best["coverage"] >= 1.0 and not best["typeConflicts"]
    return ("full", "use-as-is") if full else ("partial", "extend")


# ----------------------------------------------------------------------------- endpoints
def proposed_path(path: str, cluster_names: dict, canonical_names: dict, vocab: Vocab) -> str:
    segs = []
    for s in path.split("/"):
        if not s or s.lower() in ("api", "fn") or re.match(r"^v\d+(\.\d+)?$", s, re.I):
            continue
        if s.startswith("{"):
            segs.append(s)
            continue
        key = "".join(singular(w) for w in split_words(s))
        target = None
        for cn, canon in canonical_names.items():
            if "".join(singular(w) for w in split_words(cn)) == key or vocab.ent_key(cn) == vocab.ent_key(s):
                target = canon
                break
        if target:
            words = split_words(target)
            words[-1] = plural(words[-1])
            segs.append("-".join(words))
        else:
            segs.append(s)
    return "/" + "/".join(segs)


# ----------------------------------------------------------------------------- main
def run_alignment(data: dict, refs: list, overrides: dict, approvals: dict, scope: dict, cfg: dict, vocab_extra: dict) -> dict:
    overrides = overrides or {}
    vocab = Vocab(vocab_extra)
    clusters, a2c = build_clusters(data, scope, overrides)
    excl = {x["entity"]: x.get("reason", "") for x in overrides.get("excludeEntities", []) or []}
    if scope.get("entities"):
        wanted = set(scope["entities"])
        clusters = [c for c in clusters if c["name"] in wanted or any(m["entity"] in wanted for m in c["members"])]
    if scope.get("domains"):
        wd = set(scope["domains"])
        clusters = [c for c in clusters if c["domain"] in wd]
    m = Matcher(refs, vocab, cfg)
    ent_ov = overrides.get("entityMatches", {}) or {}
    attr_ov = defaultdict(dict)
    for k, v in (overrides.get("attributeMatches", {}) or {}).items():
        en, an = k.split(".", 1)
        attr_ov[en][an] = (v or {}).get("reference")

    def evaluate(c):
        forced = attr_ov.get(c["name"], {})
        cands = m.candidates(c, forced)
        chosen, how = (cands[0] if cands else None), "auto"
        if c["name"] in ent_ov:
            o = ent_ov[c["name"]] or {}
            if o.get("reference") in (None, "", "none"):
                chosen, how = None, "override-none"
            else:
                ref = next((r for r in m.ref_entities if r["name"] == o["reference"]
                            and (not o.get("source") or r["_source"] == o["source"])), None)
                if ref:
                    chosen = m.score_entity(c, ref, forced)
                    how = "override"
                    if chosen and all(x["reference"] != chosen["reference"] for x in cands):
                        cands = [chosen] + cands[:2]
                else:
                    chosen, how = None, "override-unknown"
        return cands, chosen, how

    # pass 1 -> learn which reference each cluster maps to, pass 2 -> refs compare precisely
    for c in clusters:
        _, chosen, _ = evaluate(c)
        if chosen:
            m.best_ref_of_cluster[c["name"]] = chosen["reference"]
    rows = []
    for c in clusters:
        cands, chosen, how = evaluate(c)
        status, rec = classify(chosen, cfg)
        if how == "override-none":
            status, rec = "none", "custom"
        if chosen and status != "none":
            m.best_ref_of_cluster[c["name"]] = chosen["reference"]
        ambiguous = (how == "auto" and len(cands) > 1 and cands[0]["score"] >= float(cfg.get("partialMatchThreshold", 0.45))
                     and cands[0]["score"] - cands[1]["score"] < float(cfg.get("ambiguityMargin", 0.05))
                     and cands[0]["reference"] != cands[1]["reference"])
        src = chosen["source"] if chosen and status != "none" else None
        rec_label = {"use-as-is": "Use reference as-is", "extend": "Extend reference", "custom": "Custom canonical entity"}[rec]
        if src == "baseline":
            rec_label = {"use-as-is": "Reuse baseline canonical", "extend": "Extend baseline canonical"}.get(rec, rec_label)
        canonical_name = chosen["reference"] if chosen and status != "none" else c["name"]
        attr_rows = []
        match_by = {a["name"]: a for a in (chosen["attributes"] if chosen and status != "none" else [])}
        for a in c["attributes"]:
            mm = match_by.get(a["name"], {"status": "no-match", "reference": None, "score": 0})
            canon_attr = mm["reference"] if mm.get("reference") else a["name"]
            attr_rows.append(dict(a, match=mm, proposedCanonicalName=canon_attr,
                                  recommendation=("map-to-reference" if mm.get("reference") else
                                                  ("extension" if status != "none" else "custom")),
                                  id=f"{c['name']}.{a['name']}",
                                  basis=basis_hash(a["name"], a["type"], mm.get("reference"))))
        score = chosen["score"] if chosen and status != "none" else (chosen["score"] if chosen else 0.0)
        rows.append({
            "id": c["name"], "name": c["name"], "kind": c["kind"], "domain": c["domain"], "description": c["description"],
            "roles": c["roles"], "apps": c["apps"], "members": c["members"], "usage": c["usage"],
            "enumValues": c["enumValues"],
            "excluded": excl.get(c["name"]),
            "status": status, "recommendation": rec, "recommendationLabel": rec_label,
            "alignmentPercent": round(100 * score), "match": chosen if status != "none" else None,
            "bestCandidate": cands[0] if cands else None, "candidates": cands, "matchHow": how,
            "ambiguous": ambiguous, "proposedCanonicalName": canonical_name,
            "referenceSource": src, "attributes": attr_rows,
            "basis": basis_hash(c["name"], sorted((a["name"], a["type"]) for a in c["attributes"]),
                                chosen["reference"] if chosen else None, c["enumValues"]),
        })
    # entities sharing a reference -> they will merge into one canonical entity
    by_ref = defaultdict(list)
    for r in rows:
        if r["status"] != "none":
            by_ref[(r["referenceSource"], r["match"]["reference"])].append(r["name"])
    for r in rows:
        r["mergesWith"] = [x for x in by_ref.get((r["referenceSource"], r["match"]["reference"]), []) if x != r["name"]] \
            if r["status"] != "none" else []

    # ----- endpoints
    canon_names = {r["name"]: r["proposedCanonicalName"] for r in rows}
    for r in rows:
        for mbr in r["members"]:
            canon_names.setdefault(mbr["entity"], r["proposedCanonicalName"])
    ent_score = {r["name"]: r["alignmentPercent"] for r in rows}
    ent_of_op = defaultdict(set)
    in_scope_names = {r["name"] for r in rows}
    app_info = {a["id"]: a for a in data["apps"]}
    for o in data["operations"]:
        ai = app_info.get(o["appId"], {})
        s2e = ai.get("schemaToEntity", {})
        env = {x["schema"]: x.get("itemsSchema") for x in ai.get("excludedSchemas", []) if x.get("reason") == "envelope"}
        schemas = [(o.get("request") or {}).get("schema")] + \
                  [(v or {}).get("schema") for k, v in (o.get("responses") or {}).items() if str(k).startswith("2")] + \
                  [p.get("schema") for p in o.get("parameters", [])]
        for sc in schemas:
            if not sc:
                continue
            sc = env.get(sc, sc)
            ent = s2e.get(sc)
            cl = a2c.get(f"{o['appId']}:{ent}") if ent else None
            if cl in in_scope_names:
                ent_of_op[(o["appId"], o["operationId"])].add(cl)
    endpoints = []
    for o in data["operations"]:
        if o["appId"] not in scope["appIds"]:
            continue
        if scope.get("domains") and o["domain"] not in scope["domains"]:
            continue
        es = sorted(ent_of_op.get((o["appId"], o["operationId"]), set()))
        if scope.get("entities") and not es:
            continue
        pct = round(sum(ent_score.get(e, 0) for e in es) / len(es)) if es else None
        endpoints.append({
            "id": f"{o['appId']}:{o['operationId']}", "appId": o["appId"], "operationId": o["operationId"],
            "method": o["method"], "path": o["path"], "domain": o["domain"], "capability": o.get("capability", ""),
            "summary": o.get("summary", ""), "entities": es, "alignmentPercent": pct,
            "status": "n/a" if pct is None else ("full" if pct >= 90 else ("partial" if pct >= 45 else "none")),
            "proposedPath": proposed_path(o["path"], {}, canon_names, vocab),
            "request": o.get("request"), "responses": o.get("responses", {}), "parameters": o.get("parameters", []),
            "security": o.get("security", []),
            "basis": basis_hash(o["method"], o["path"], es),
        })

    # ----- domain & app roll-ups
    def rollup(items, keyf):
        g = defaultdict(list)
        for r in items:
            for k in keyf(r):
                g[k].append(r)
        out = []
        for k, rs in sorted(g.items()):
            sa = Counter(next((e.get("subjectArea") for e in m.ref_entities if r["match"] and e["name"] == r["match"]["reference"]), "")
                         for r in rs if r["match"])
            out.append({"name": k, "entities": len(rs),
                        "full": sum(1 for r in rs if r["status"] == "full"),
                        "partial": sum(1 for r in rs if r["status"] == "partial"),
                        "none": sum(1 for r in rs if r["status"] == "none"),
                        "alignmentPercent": round(sum(r["alignmentPercent"] for r in rs) / len(rs)) if rs else 0,
                        "referenceSubjectAreas": [x for x, _ in sa.most_common(3) if x]})
        return out
    domains = rollup(rows, lambda r: [r["domain"] or "Unclassified"])
    apps = rollup(rows, lambda r: r["apps"])
    for d in domains:
        eps = [e for e in endpoints if e["domain"] == d["name"] and e["alignmentPercent"] is not None]
        d["endpoints"] = len([e for e in endpoints if e["domain"] == d["name"]])
        d["endpointAlignmentPercent"] = round(sum(e["alignmentPercent"] for e in eps) / len(eps)) if eps else None

    # ----- review state
    review = review_state(rows, endpoints, approvals or {})
    total = len(rows)
    summary = {
        "entities": total, "full": sum(1 for r in rows if r["status"] == "full"),
        "partial": sum(1 for r in rows if r["status"] == "partial"), "none": sum(1 for r in rows if r["status"] == "none"),
        "ambiguous": sum(1 for r in rows if r["ambiguous"]),
        "attributes": sum(len(r["attributes"]) for r in rows),
        "attributesMatched": sum(1 for r in rows for a in r["attributes"] if a["match"].get("reference")),
        "typeConflicts": sum(1 for r in rows for a in r["attributes"] if a["match"].get("status") == "type-conflict"),
        "endpoints": len(endpoints),
        "alignmentPercent": round(sum(r["alignmentPercent"] for r in rows) / total) if total else 0,
        "review": review["counts"],
    }
    return {"entities": rows, "endpoints": endpoints, "domains": domains, "apps": apps, "summary": summary,
            "review": review, "appEntityToRegional": a2c,
            "references": [{"name": r.get("name"), "source": r.get("source"), "version": r.get("version", ""),
                            "entities": len(r["entities"]), "sourceFile": Path(r.get("sourceFile", "")).name} for r in refs]}


def review_state(rows, endpoints, approvals):
    ea = approvals.get("entities", {}) or {}
    aa = approvals.get("attributes", {}) or {}
    oa = approvals.get("endpoints", {}) or {}
    counts = Counter()
    state = {"entities": {}, "attributes": {}, "endpoints": {}}
    for r in rows:
        a = ea.get(r["id"])
        st = review_status(a, r["basis"])
        state["entities"][r["id"]] = dict(a or {}, state=st)
        counts["entity_" + st] += 1
        for at in r["attributes"]:
            x = aa.get(at["id"])
            st2 = review_status(x, at["basis"]) if x else "default"
            state["attributes"][at["id"]] = dict(x or {}, state=st2)
    for e in endpoints:
        x = oa.get(e["id"])
        st = review_status(x, e["basis"]) if x else "default"
        state["endpoints"][e["id"]] = dict(x or {}, state=st)
        counts["endpoint_" + st] += 1
    for k in list(ea):
        if k not in state["entities"]:
            state.setdefault("stale", []).append(f"entity approval '{k}' has no alignment row")
    return {"counts": dict(counts), "state": state, "staleKeys": state.pop("stale", [])}


def review_status(a, basis):
    if not a or a.get("decision") in (None, "", "pending"):
        return "pending"
    if a.get("basis") and a["basis"] != basis:
        return "changed"
    return "approved" if a["decision"] != "reject" else "rejected"
