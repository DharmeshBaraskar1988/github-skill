#!/usr/bin/env python3
"""
sensitive_scan.py - one shared policy for data that must never leave the source code or reach the LLM,
the generated artifacts, the HTML/Excel views or chat.

Identical copies live in every skill's scripts/ folder so each skill works on its own. Keep them in sync
(tests/run_e2e.sh checks that they are byte-identical).

Categories (all are errors in the validators; the builders redact them first):
  credential  keys, tokens, passwords, connection strings, private keys, SAS signatures, auth headers
  email       any e-mail address (no exceptions)
  url         any URL, except: a host that is only a template variable (https://{host}), reserved example
              hosts (RFC 2606: *.example, *.test, *.invalid, example.com/.net/.org) and the technical namespaces
              in BUILTIN_ALLOWED_URL_HOSTS / sensitive-data.yaml `allowedUrlHosts`
  host        internal host names (*.internal, *.corp, *.local, *.lan, *.intranet, *.intra) and IPv4 addresses
  pii         phone numbers (+country code), payment card numbers (Luhn), IBAN (mod-97), US SSN, UK NINO,
              India PAN / Aadhaar
  client      client / customer / partner names and other terms listed in sensitive-data.yaml
              (`blockedTerms` in clear text, or `blockedTermHashes` = sha256 of the lower-case term so the list
              itself does not expose the names)

Findings never contain the matched value - only category, label, a masked hint and the location.

CLI
  python sensitive_scan.py --scan <file-or-folder> [...]      exit 1 when anything is found
  python sensitive_scan.py --hash "Acme Insurance Ltd"        prints the sha256 for blockedTermHashes
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

POLICY_FILE = Path("api-catalog") / "reference" / "sensitive-data.yaml"
TEXT_SUFFIXES = {".json", ".yaml", ".yml", ".md", ".html", ".htm", ".csv", ".txt", ".xml", ".xsd"}

BUILTIN_ALLOWED_URL_HOSTS = {
    # technical namespaces that appear in generated HTML / schemas - not data
    "www.w3.org", "w3.org", "json-schema.org", "spec.openapis.org", "swagger.io",
    "schemas.openxmlformats.org", "schemas.microsoft.com", "purl.org",
}
RESERVED_TLDS = (".example", ".test", ".invalid", ".localhost")
RESERVED_HOSTS = {"example.com", "example.net", "example.org", "localhost"}
INTERNAL_TLDS = ("internal", "corp", "local", "lan", "intranet", "intra", "private", "home")

CREDENTIAL_PATTERNS = [
    (r"(?i)\b(AccountKey|SharedAccessKey|SharedAccessSignature|Password|Passwd|Pwd|ClientSecret|Client_Secret|ApiKey|Api_Key|"
     r"AccessKey|SecretKey|Token|AuthToken)\s*[=:]\s*[\"']?[^;\s\"',}]{6,}", "key/password assignment"),
    (r"(?i)\b(Server|Data Source|Host)=[^;]+;.*\b(Database|Initial Catalog|User Id|Uid)=", "database connection string"),
    (r"(?i)DefaultEndpointsProtocol=https?;AccountName=", "storage connection string"),
    (r"(?i)Endpoint=sb://[^;]+;SharedAccessKeyName=", "service bus connection string"),
    (r"(?i)InstrumentationKey=[0-9a-f-]{36}", "instrumentation key"),
    (r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "JWT"),
    (r"(?i)\b(bearer|basic)\s+[A-Za-z0-9\-_.=+/]{16,}", "authorization header value"),
    (r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----", "private key"),
    (r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{16,}", "API key"),
    (r"\bAKIA[0-9A-Z]{16}\b", "cloud access key id"),
    (r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}", "source-control token"),
    (r"\bxox[abprs]-[A-Za-z0-9-]{10,}", "chat token"),
    (r"\bAIza[0-9A-Za-z_-]{35}\b", "API key"),
    (r"(?i)[?&](sig|signature|code|access_token|api_key|apikey|client_secret)=[A-Za-z0-9%_\-.+/=]{8,}", "key in query string"),
    (r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s:@\"']+:[^/\s@\"']+@", "credentials in URL"),
]
EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?![\w-])")
URL = re.compile(r"(?i)\b(?:https?|ftp|ftps|sftp|ssh|sb|amqps?|wss?|jdbc:[a-z]+|mongodb(?:\+srv)?|redis|file)://[^\s\"'<>)\]}`,]+")
WWW = re.compile(r"(?i)(?<![\w./-])www\.[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/[^\s\"'<>)\]}`,]*)?")
HOSTNAME = re.compile(r"(?i)(?<![\w.@/-])(?:[a-z0-9-]+\.)+(" + "|".join(INTERNAL_TLDS) + r")(?![\w.-])")
IPV4 = re.compile(r"(?<![\w.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\w.])")
PHONE = re.compile(r"(?<![\w+])\+\d{1,3}[\s.-]?\(?\d{1,4}\)?(?:[\s.-]?\d{2,5}){2,4}(?!\w)")
CARD = re.compile(r"(?<![\w-])(?:\d[ -]?){12,18}\d(?![\w-])")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b")
SSN = re.compile(r"(?<![\w-])(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?![\w-])")
NINO = re.compile(r"\b(?!BG|GB|NK|KN|TN|NT|ZZ)[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z] ?\d{2} ?\d{2} ?\d{2} ?[A-D]\b")
PAN = re.compile(r"\b[A-Z]{3}[PCHFATBLJG][A-Z]\d{4}[A-Z]\b")
AADHAAR = re.compile(r"(?<![\w-])[2-9]\d{3}[ -]\d{4}[ -]\d{4}(?![\w-])")
SAFE_IPS = {"0.0.0.0", "127.0.0.1", "255.255.255.255"}
WORD = re.compile(r"[a-z0-9]+")


# --------------------------------------------------------------------------- policy
def _load_yaml(p: Path) -> dict:
    try:
        import yaml  # noqa: PLC0415
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}


def find_policy_file(start: Path | None = None) -> Path | None:
    """sensitive-data.yaml: explicit path, else api-catalog/reference/ in the current folder or any parent."""
    here = (start or Path.cwd()).resolve()
    if here.is_file() and here.suffix in (".yaml", ".yml") and here.name.startswith("sensitive"):
        return here
    for d in [here, *here.parents]:
        if (d / POLICY_FILE).exists():
            return d / POLICY_FILE
    return None


def load_policy(path: str | Path | None = None) -> dict:
    p = Path(path) if path else find_policy_file()
    raw = _load_yaml(p) if p and p.exists() else {}
    terms = [str(t).strip() for t in raw.get("blockedTerms") or [] if str(t).strip()]
    hashes = {str(h).strip().lower() for h in raw.get("blockedTermHashes") or [] if str(h).strip()}
    allowed_terms = {str(t).strip().lower() for t in raw.get("allowedTerms") or []}
    return {
        "file": str(p) if p and p.exists() else None,
        "allowedUrlHosts": BUILTIN_ALLOWED_URL_HOSTS | {str(h).lower() for h in raw.get("allowedUrlHosts") or []},
        "terms": [(t, re.compile(r"(?i)(?<![A-Za-z0-9])" + re.escape(t) + r"(?![A-Za-z0-9])")) for t in terms],
        "hashes": hashes,
        "maxWords": max([len(WORD.findall(t.lower())) for t in terms] + [int(raw.get("hashMaxWords", 4))]),
        "allowedTerms": allowed_terms,
        "extraPatterns": [(re.compile(x["regex"]), x.get("label", "custom pattern"), x.get("category", "client"))
                          for x in raw.get("extraPatterns") or [] if isinstance(x, dict) and x.get("regex")],
    }


def term_hash(term: str) -> str:
    return hashlib.sha256(" ".join(WORD.findall(term.lower())).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- helpers
def _host_allowed(host: str, policy: dict) -> bool:
    host = host.lower().strip("[]")
    if not host or "{" in host:          # https://{host} - template variable only
        return True
    host = host.split(":")[0]
    if host in RESERVED_HOSTS or host.endswith(RESERVED_TLDS) or any(host.endswith("." + h) for h in RESERVED_HOSTS):
        return True
    return any(host == h or host.endswith("." + h) for h in policy["allowedUrlHosts"])


def _luhn(digits: str) -> bool:
    s, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        s, alt = s + d, not alt
    return s % 10 == 0


def _iban_ok(v: str) -> bool:
    v = v.replace(" ", "")
    if not 15 <= len(v) <= 34:
        return False
    r = v[4:] + v[:4]
    num = "".join(str(int(c, 36)) for c in r)
    return int(num) % 97 == 1


def _mask(value: str) -> str:
    return f"{len(value.strip())} chars"     # never echo any part of the value


def _spans(text: str, policy: dict):
    """Yield (start, end, category, label)."""
    for pat, label in CREDENTIAL_PATTERNS:
        for m in re.finditer(pat, text):
            yield m.start(), m.end(), "credential", label
    for m in EMAIL.finditer(text):
        yield m.start(), m.end(), "email", "e-mail address"
    for m in URL.finditer(text):
        host = re.sub(r"^[a-z][a-z0-9+.:-]*://", "", m.group(0), flags=re.I).split("/")[0].split("?")[0].split("@")[-1]
        if not _host_allowed(host, policy):
            yield m.start(), m.end(), "url", "URL"
    for m in WWW.finditer(text):
        if not _host_allowed(m.group(0).split("/")[0], policy):
            yield m.start(), m.end(), "url", "URL"
    for m in HOSTNAME.finditer(text):
        if not _host_allowed(m.group(0), policy):
            yield m.start(), m.end(), "host", "internal host name"
    for m in IPV4.finditer(text):
        if m.group(0) not in SAFE_IPS:
            yield m.start(), m.end(), "host", "IP address"
    for m in PHONE.finditer(text):
        if 8 <= len(re.sub(r"\D", "", m.group(0))) <= 15:
            yield m.start(), m.end(), "pii", "phone number"
    for m in CARD.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn(digits) and len(set(digits)) > 1 and not re.fullmatch(r"(19|20)\d{11,17}", digits):
            yield m.start(), m.end(), "pii", "payment card number"
    for m in IBAN.finditer(text):
        if _iban_ok(m.group(0)):
            yield m.start(), m.end(), "pii", "IBAN"
    for rx, label in ((SSN, "national id (SSN)"), (NINO, "national id (NINO)"), (PAN, "tax id (PAN)"), (AADHAAR, "national id (Aadhaar)")):
        for m in rx.finditer(text):
            yield m.start(), m.end(), "pii", label
    for term, rx in policy["terms"]:
        if term.lower() in policy["allowedTerms"]:
            continue
        for m in rx.finditer(text):
            yield m.start(), m.end(), "client", "blocked term"
    if policy["hashes"]:
        toks = [(m.start(), m.end(), m.group(0)) for m in WORD.finditer(text.lower())]
        for i in range(len(toks)):
            for n in range(1, policy["maxWords"] + 1):
                if i + n > len(toks):
                    break
                phrase = " ".join(t[2] for t in toks[i:i + n])
                if phrase in policy["allowedTerms"]:
                    continue
                if hashlib.sha256(phrase.encode("utf-8")).hexdigest() in policy["hashes"]:
                    yield toks[i][0], toks[i + n - 1][1], "client", "blocked term (hashed list)"
    for rx, label, cat in policy["extraPatterns"]:
        for m in rx.finditer(text):
            yield m.start(), m.end(), cat, label


def _merged(text: str, policy: dict):
    spans = sorted(set(_spans(text, policy)), key=lambda s: (s[0], -s[1]))
    out = []
    for s in spans:
        if out and s[0] < out[-1][1]:
            if s[1] > out[-1][1]:
                out[-1] = (out[-1][0], s[1], out[-1][2], out[-1][3])
            continue
        out.append(s)
    return out


# --------------------------------------------------------------------------- API
def scan_text(text: str, policy: dict | None = None, where: str = "") -> list[dict]:
    policy = policy or load_policy()
    found = []
    for s, e, cat, label in _merged(text or "", policy):
        line = text.count("\n", 0, s) + 1
        found.append({"category": cat, "label": label, "hint": _mask(text[s:e]), "where": f"{where}:{line}" if where else f"line {line}"})
    return found


def redact_text(text: str, policy: dict | None = None) -> tuple[str, list[dict]]:
    policy = policy or load_policy()
    spans = _merged(text or "", policy)
    if not spans:
        return text, []
    out, last, found = [], 0, []
    for s, e, cat, label in spans:
        out.append(text[last:s])
        out.append(f"[REDACTED-{cat.upper()}]")
        last = e
        found.append({"category": cat, "label": label})
    out.append(text[last:])
    return "".join(out), found


def redact_obj(obj, policy: dict | None = None, path: str = "", found: list | None = None, skip_keys=("$ref",)):
    """Redact every string value (not keys) in a JSON/YAML structure. Returns (new_obj, findings)."""
    policy = policy or load_policy()
    found = [] if found is None else found
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            if k in skip_keys:
                new[k] = v
            else:
                new[k], _ = redact_obj(v, policy, f"{path}/{k}", found, skip_keys)
        return new, found
    if isinstance(obj, list):
        return [redact_obj(v, policy, f"{path}/{i}", found, skip_keys)[0] for i, v in enumerate(obj)], found
    if isinstance(obj, str):
        txt, f = redact_text(obj, policy)
        for x in f:
            x["path"] = path
        found.extend(f)
        return txt, found
    return obj, found


def scan_paths(paths, policy: dict | None = None) -> list[dict]:
    policy = policy or load_policy()
    found = []
    for p in paths:
        p = Path(p)
        files = [p] if p.is_file() else [f for f in sorted(p.rglob("*")) if f.is_file()]
        for f in files:
            if f.suffix.lower() not in TEXT_SUFFIXES or f.name.startswith("sensitive-data"):   # the policy file itself
                continue
            try:
                txt = f.read_text(encoding="utf-8")
            except Exception:  # noqa: BLE001
                continue
            found.extend(scan_text(txt, policy, str(f)))
    return found


def check_files(files, policy: dict | None = None) -> list[dict]:
    """Scan the given files (missing ones are skipped). Used by every validator."""
    policy = policy or load_policy()
    out = []
    for f in files:
        f = Path(f)
        if f.is_file():
            out.extend(scan_text(f.read_text(encoding="utf-8", errors="ignore"), policy, f.name))
    return out


def report(found: list[dict], err, code: str, fix: str, limit: int = 25):
    """Turn findings into validator errors (value never included)."""
    for x in found[:limit]:
        err(code, f"Sensitive data ({x['category']}: {x['label']}, {x['hint']}) at {x['where']}", fix)
    if len(found) > limit:
        err(code, f"... and {len(found) - limit} more sensitive-data findings ({summarise(found[limit:])})", fix)


def summarise(found: list[dict]) -> str:
    counts: dict = {}
    for f in found:
        counts[f["label"]] = counts.get(f["label"], 0) + 1
    return ", ".join(f"{n}× {k}" for k, n in sorted(counts.items()))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", nargs="*")
    ap.add_argument("--hash")
    ap.add_argument("--policy")
    a = ap.parse_args()
    if a.hash:
        print(term_hash(a.hash))
        return
    found = scan_paths(a.scan or ["."], load_policy(a.policy))
    print(json.dumps({"status": "fail" if found else "pass", "findings": found}, indent=2, ensure_ascii=False))
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()
