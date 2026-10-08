"""
Lightweight, dependency-free C# source scanner for .NET API discovery.

It is NOT a full C# compiler. It recognises the patterns that matter for
OpenAPI generation in typical .NET 6/7/8/9 enterprise solutions:

  * Minimal APIs ............ app.MapGet/MapPost/... incl. MapGroup prefixes,
                              .Produces<T>(), .Accepts<T>(), .WithName/.WithTags
  * MVC / Web API controllers [ApiController], [Route], [HttpGet(...)], ActionResult<T>,
                              [ProducesResponseType]
  * Azure Functions ......... isolated ([Function]) and in-process ([FunctionName]),
                              [HttpTrigger(...)], [OpenApiRequestBody], [OpenApiResponseWithBody],
                              ReadFromJsonAsync<T>, Deserialize<T>; non-HTTP triggers are inventoried
  * Models .................. classes, records (incl. positional), structs, enums,
                              inheritance, XML doc <summary>, DataAnnotations, JsonPropertyName

Anything it cannot determine statically is reported as `needsReview` so the
Copilot agent can read the code and resolve it through overrides.yaml.

SECURITY: this module only ever opens *.cs, *.csproj and host.json files.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------- #
# Files that must never be opened (secrets / config). Enforced here AND by hooks.
# --------------------------------------------------------------------------- #
FORBIDDEN_FILE_PATTERNS = [
    "appsettings*.json", "local.settings.json", "secrets.json", "*.env", ".env*",
    "*.pfx", "*.p12", "*.pem", "*.key", "*.snk", "*.publishsettings", "*.pubxml",
    "*.user", "launchSettings.json", "web.config", "app.config", "*.Secrets.*",
]

DEFAULT_EXCLUDES = [
    "**/bin/**", "**/obj/**", "**/.git/**", "**/node_modules/**", "**/.vs/**",
    "**/*.Tests/**", "**/*.Test/**", "**/*Tests/**", "**/*.UnitTests/**",
    "**/*.IntegrationTests/**", "**/TestResults/**", "**/Migrations/**",
]

HTTP_VERBS = ["Get", "Post", "Put", "Delete", "Patch", "Head", "Options"]

PRIMITIVES = {
    "string": ("string", None), "String": ("string", None),
    "char": ("string", None), "Char": ("string", None),
    "bool": ("boolean", None), "Boolean": ("boolean", None),
    "byte": ("integer", "int32"), "sbyte": ("integer", "int32"),
    "short": ("integer", "int32"), "ushort": ("integer", "int32"),
    "int": ("integer", "int32"), "Int32": ("integer", "int32"),
    "uint": ("integer", "int64"), "UInt32": ("integer", "int64"),
    "long": ("integer", "int64"), "Int64": ("integer", "int64"),
    "ulong": ("integer", "int64"), "UInt64": ("integer", "int64"),
    "float": ("number", "float"), "Single": ("number", "float"),
    "double": ("number", "double"), "Double": ("number", "double"),
    "decimal": ("number", "double"), "Decimal": ("number", "double"),
    "DateTime": ("string", "date-time"), "DateTimeOffset": ("string", "date-time"),
    "DateOnly": ("string", "date"), "TimeOnly": ("string", "time"),
    "TimeSpan": ("string", "duration"), "Guid": ("string", "uuid"),
    "Uri": ("string", "uri"), "byte[]": ("string", "byte"),
    "IFormFile": ("string", "binary"), "Stream": ("string", "binary"),
    "object": ("object", None), "Object": ("object", None),
    "JsonElement": ("object", None), "JsonNode": ("object", None),
    "JObject": ("object", None), "dynamic": ("object", None),
}

COLLECTION_GENERICS = {
    "List", "IList", "IEnumerable", "ICollection", "IReadOnlyList",
    "IReadOnlyCollection", "Collection", "HashSet", "ISet", "IAsyncEnumerable",
    "ImmutableList", "ImmutableArray", "ReadOnlyCollection",
}
DICT_GENERICS = {"Dictionary", "IDictionary", "IReadOnlyDictionary", "ImmutableDictionary"}
WRAPPER_GENERICS = {
    "Task", "ValueTask", "ActionResult", "Ok", "Created", "CreatedAtRoute",
    "Accepted", "AcceptedAtRoute", "Nullable", "JsonHttpResult",
}

# Parameter types that are injected services, never part of the HTTP contract
SERVICE_TYPES = {
    "CancellationToken", "HttpContext", "HttpRequest", "HttpResponse",
    "HttpRequestData", "HttpResponseData", "FunctionContext", "ExecutionContext",
    "ClaimsPrincipal", "ILogger", "LinkGenerator", "IServiceProvider",
}

NON_HTTP_TRIGGERS = [
    "ServiceBusTrigger", "QueueTrigger", "TimerTrigger", "EventGridTrigger",
    "EventHubTrigger", "BlobTrigger", "CosmosDBTrigger", "KafkaTrigger",
    "RabbitMQTrigger", "SqlTrigger", "DurableClient", "OrchestrationTrigger",
    "ActivityTrigger",
]


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class Prop:
    name: str
    csType: str
    jsonName: str
    required: bool = False
    nullable: bool = False
    description: str = ""
    maxLength: Optional[int] = None
    minLength: Optional[int] = None
    pattern: Optional[str] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    format: Optional[str] = None


@dataclass
class TypeDef:
    name: str
    kind: str                      # class | record | struct | enum | interface
    namespace: str
    project: str
    file: str
    line: int
    description: str = ""
    baseType: Optional[str] = None
    genericParams: list = field(default_factory=list)
    properties: list = field(default_factory=list)   # list[Prop]
    enumValues: list = field(default_factory=list)
    isAbstract: bool = False


@dataclass
class Param:
    name: str
    csType: str
    source: str            # path | query | header | body | form | services | asparameters
    required: bool = True
    description: str = ""


@dataclass
class Endpoint:
    method: str
    path: str
    style: str             # minimal-api | controller | azure-function
    project: str
    file: str
    line: int
    handler: str = ""
    operationId: str = ""
    tags: list = field(default_factory=list)
    summary: str = ""
    description: str = ""
    params: list = field(default_factory=list)       # list[Param]
    requestBody: Optional[str] = None                # C# type
    requestContentType: str = "application/json"
    responses: dict = field(default_factory=dict)    # status -> C# type or None
    auth: str = ""                                   # anonymous | required | function-key | ...
    needsReview: list = field(default_factory=list)  # human/LLM follow-ups


@dataclass
class Project:
    name: str
    path: str
    sdk: str
    kind: str              # web | functions-isolated | functions-inprocess | library
    targetFrameworks: list
    packages: dict
    projectReferences: list
    routePrefix: str = ""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def is_forbidden(path: str) -> bool:
    base = os.path.basename(path)
    return any(fnmatch.fnmatch(base, p) or fnmatch.fnmatch(base.lower(), p.lower())
               for p in FORBIDDEN_FILE_PATTERNS)


def is_excluded(rel_path: str, excludes: list) -> bool:
    p = "/" + rel_path.replace("\\", "/")
    for pat in excludes:
        pat2 = "/" + pat.lstrip("/")
        if fnmatch.fnmatch(p, pat2) or fnmatch.fnmatch(p + "/", pat2):
            return True
        # allow "**/Foo/**" to match "/Foo/x"
        if pat.startswith("**/") and fnmatch.fnmatch(p, "/" + pat[3:]):
            return True
    return False


def read_text(path: Path) -> str:
    if is_forbidden(str(path)):
        raise PermissionError(f"Refusing to read forbidden file: {path}")
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return ""


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def strip_comments_keep_layout(text: str) -> str:
    """Blank out // (not ///) and /* */ comments and string contents are kept.
    Keeps newlines so line numbers stay valid."""
    out = []
    i, n = 0, len(text)
    in_str = None
    verbatim = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if verbatim:
                if c == '"' and i + 1 < n and text[i + 1] == '"':
                    out.append('"'); i += 2; continue
                if c == '"':
                    in_str = None
            else:
                if c == "\\":
                    if i + 1 < n:
                        out.append(text[i + 1]); i += 2; continue
                elif c == in_str:
                    in_str = None
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            if i + 2 < n and text[i + 2] == "/":       # XML doc comment: keep
                j = text.find("\n", i)
                j = n if j == -1 else j
                out.append(text[i:j]); i = j; continue
            j = text.find("\n", i)
            j = n if j == -1 else j
            out.append(" " * (j - i)); i = j; continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append("".join("\n" if ch == "\n" else " " for ch in text[i:j])); i = j; continue
        if c == '"' or c == "'":
            verbatim = (i > 0 and text[i - 1] == "@") or (i > 1 and text[i - 2:i] in ("$@", "@$"))
            in_str = c
        out.append(c)
        i += 1
    return "".join(out)


def match_brace(text: str, open_pos: int, open_ch="{", close_ch="}") -> int:
    """Return index of matching close char, skipping strings."""
    depth = 0
    i, n = open_pos, len(text)
    in_str = None
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\" and in_str != "@":
                i += 2; continue
            if c == '"' and in_str in ('"', "@"):
                if in_str == "@" and i + 1 < n and text[i + 1] == '"':
                    i += 2; continue
                in_str = None
            elif c == "'" and in_str == "'":
                in_str = None
            i += 1; continue
        if c == '"':
            in_str = "@" if i > 0 and text[i - 1] == "@" else '"'
        elif c == "'":
            in_str = "'"
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n - 1


def split_top_level(s: str, sep=",") -> list:
    parts, depth, cur, in_str = [], 0, [], False
    for ch in s:
        if ch == '"':
            in_str = not in_str
        if not in_str:
            if ch in "<([{":
                depth += 1
            elif ch in ">)]}":
                depth -= 1
            elif ch == sep and depth == 0:
                parts.append("".join(cur).strip()); cur = []; continue
        cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur).strip())
    return parts


def doc_summary(doc_block: str) -> str:
    if not doc_block:
        return ""
    lines = [re.sub(r"^\s*///\s?", "", l) for l in doc_block.splitlines() if l.strip().startswith("///")]
    joined = " ".join(lines)
    m = re.search(r"<summary>(.*?)</summary>", joined, re.S)
    text = m.group(1) if m else joined
    text = re.sub(r"<see\s+cref=\"[A-Z]:?([^\"]+)\"\s*/>", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_generic(t: str):
    """'Task<List<Foo>>' -> ('Task', ['List<Foo>'])"""
    t = t.strip()
    m = re.match(r"^([\w\.]+)\s*<(.*)>$", t)
    if not m:
        return t, []
    return m.group(1).split(".")[-1], split_top_level(m.group(2))


def unwrap_result_type(t: Optional[str]) -> Optional[str]:
    """Strip Task/ValueTask/ActionResult/Ok<>/Results<...> wrappers. Returns
    the payload C# type, or None if it is a non-typed result (IResult, IActionResult...)."""
    if not t:
        return None
    t = t.strip().rstrip("?")
    for _ in range(10):
        base, args = parse_generic(t)
        if base in WRAPPER_GENERICS and args:
            t = args[0].strip().rstrip("?")
            continue
        if base == "Results" and args:
            # Results<Ok<A>, NotFound, Created<B>> -> first typed success
            for a in args:
                ab, aa = parse_generic(a)
                if ab in ("Ok", "Created", "CreatedAtRoute", "Accepted", "AcceptedAtRoute") and aa:
                    return unwrap_result_type(aa[0])
            return None
        break
    if t in ("IResult", "IActionResult", "ActionResult", "Task", "ValueTask", "void",
             "HttpResponseData", "IStatusCodeActionResult", "NoContent", "NotFound",
             "Ok", "BadRequest", "Created", "Accepted", "HttpResponseMessage"):
        return None
    return t


def results_status_codes(t: Optional[str]) -> dict:
    """Results<Ok<A>, NotFound, ValidationProblem> -> {'200': 'A', '404': None, '400': 'HttpValidationProblemDetails'}"""
    codes = {}
    if not t:
        return codes
    t = t.strip()
    base, args = parse_generic(t)
    while base in ("Task", "ValueTask") and args:
        base, args = parse_generic(args[0])
    if base != "Results":
        return codes
    mapping = {
        "Ok": "200", "Created": "201", "CreatedAtRoute": "201", "Accepted": "202",
        "AcceptedAtRoute": "202", "NoContent": "204", "BadRequest": "400",
        "UnauthorizedHttpResult": "401", "ForbidHttpResult": "403", "NotFound": "404",
        "Conflict": "409", "UnprocessableEntity": "422", "ValidationProblem": "400",
        "ProblemHttpResult": "500", "StatusCodeHttpResult": "default",
    }
    for a in args:
        ab, aa = parse_generic(a)
        code = mapping.get(ab)
        if not code:
            continue
        if ab == "ValidationProblem":
            codes[code] = "HttpValidationProblemDetails"
        elif ab == "ProblemHttpResult":
            codes[code] = "ProblemDetails"
        else:
            codes[code] = aa[0].strip() if aa else None
    return codes


def to_camel(name: str) -> str:
    return name[:1].lower() + name[1:] if name else name


def to_pascal_words(s: str) -> str:
    return "".join(w[:1].upper() + w[1:] for w in re.split(r"[^A-Za-z0-9]+", s) if w)


# --------------------------------------------------------------------------- #
# Project discovery
# --------------------------------------------------------------------------- #
def parse_csproj(path: Path, root: Path) -> Project:
    xml = read_text(path)
    sdk_m = re.search(r'<Project\s+Sdk="([^"]+)"', xml)
    sdk = sdk_m.group(1) if sdk_m else "Microsoft.NET.Sdk"
    tfs = re.findall(r"<TargetFrameworks?>([^<]+)</TargetFrameworks?>", xml)
    tfs = [t.strip() for x in tfs for t in x.split(";") if t.strip()]
    pkgs = {}
    for m in re.finditer(r'<PackageReference\s+Include="([^"]+)"(?:\s+Version="([^"]*)")?', xml):
        pkgs[m.group(1)] = m.group(2) or ""
    refs = [Path(r.replace("\\", "/")).stem for r in re.findall(r'<ProjectReference\s+Include="([^"]+)"', xml)]
    az_ver = re.search(r"<AzureFunctionsVersion>([^<]+)</AzureFunctionsVersion>", xml)
    if any(p.startswith("Microsoft.Azure.Functions.Worker") for p in pkgs):
        kind = "functions-isolated"
    elif "Microsoft.NET.Sdk.Functions" in pkgs or az_ver:
        kind = "functions-inprocess"
    elif sdk.endswith(".Web"):
        kind = "web"
    else:
        kind = "library"
    proj = Project(
        name=path.stem, path=str(path.parent.relative_to(root)).replace("\\", "/") or ".",
        sdk=sdk, kind=kind, targetFrameworks=tfs, packages=pkgs, projectReferences=refs,
    )
    if kind.startswith("functions"):
        proj.routePrefix = "api"
        host = path.parent / "host.json"
        if host.exists():
            try:
                h = json.loads(read_text(host))
                rp = h.get("extensions", {}).get("http", {}).get("routePrefix")
                if rp is not None:
                    proj.routePrefix = rp
            except Exception:
                pass
    return proj


def find_projects(root: Path, source_roots: list, excludes: list) -> list:
    projects = []
    for sr in source_roots or ["."]:
        base = (root / sr).resolve()
        for p in base.rglob("*.csproj"):
            rel = str(p.relative_to(root)).replace("\\", "/")
            if is_excluded(rel, excludes):
                continue
            projects.append(parse_csproj(p, root))
    # de-dup
    seen, out = set(), []
    for p in projects:
        if p.path not in seen:
            seen.add(p.path); out.append(p)
    return out


def iter_cs_files(root: Path, project: Project, excludes: list, all_project_paths: list):
    pdir = (root / project.path).resolve()
    nested = [(root / pp).resolve() for pp in all_project_paths if pp != project.path]
    for f in pdir.rglob("*.cs"):
        rel = str(f.relative_to(root)).replace("\\", "/")
        if is_excluded(rel, excludes):
            continue
        # skip files that belong to a nested project
        if any(n != pdir and str(f).startswith(str(n) + os.sep) and str(n).startswith(str(pdir)) for n in nested):
            continue
        yield f, rel


# --------------------------------------------------------------------------- #
# Type (model) extraction
# --------------------------------------------------------------------------- #
TYPE_DECL_RE = re.compile(
    r"(?P<doc>(?:^[ \t]*///[^\n]*\n)*)"
    r"(?P<attrs>(?:^[ \t]*\[[^\n]*\][ \t]*\n)*)"
    r"^[ \t]*(?P<mods>(?:(?:public|internal|private|protected|sealed|abstract|static|partial|readonly|file|new|unsafe)\s+)*)"
    r"(?P<kind>record\s+class|record\s+struct|record|class|struct|enum|interface)\s+"
    r"(?P<name>[A-Za-z_]\w*)"
    r"(?P<generic>\s*<[^>{(]*>)?",
    re.M,
)

PROP_RE = re.compile(
    r"(?P<doc>(?:^[ \t]*///[^\n]*\n)*)"
    r"(?P<attrs>(?:^[ \t]*\[[^\n]*\][ \t]*\n)*)"
    r"^[ \t]*(?P<inline_attrs>(?:\[[^\]\n]*\]\s*)*)"
    r"public\s+(?P<mods>(?:(?:required|virtual|override|new|static|abstract|sealed)\s+)*)"
    r"(?P<type>[\w\.]+(?:\s*<.+?>)?(?:\[\])*\??)\s+(?P<name>[A-Za-z_]\w*)\s*(?P<tail>\{|=>)",
    re.M,
)


def parse_attrs(attr_text: str) -> dict:
    a = {}
    if not attr_text:
        return a
    if re.search(r"\[\s*(?:Required|JsonRequired)\b", attr_text):
        a["required"] = True
    m = re.search(r"JsonPropertyName\(\s*\"([^\"]+)\"", attr_text) or re.search(r"JsonProperty\(\s*(?:PropertyName\s*=\s*)?\"([^\"]+)\"", attr_text)
    if m:
        a["jsonName"] = m.group(1)
    if re.search(r"\[\s*(?:JsonIgnore|IgnoreDataMember)\b(?!\s*\(\s*Condition)", attr_text):
        a["ignore"] = True
    m = re.search(r"(?:MaxLength|StringLength)\(\s*(\d+)", attr_text)
    if m:
        a["maxLength"] = int(m.group(1))
    m = re.search(r"MinLength\(\s*(\d+)|MinimumLength\s*=\s*(\d+)", attr_text)
    if m:
        a["minLength"] = int(m.group(1) or m.group(2))
    m = re.search(r"Range\(\s*([-\d\.]+)\s*,\s*([-\d\.]+)", attr_text)
    if m:
        try:
            a["minimum"], a["maximum"] = float(m.group(1)), float(m.group(2))
        except ValueError:
            pass
    m = re.search(r"RegularExpression\(\s*@?\"([^\"]+)\"", attr_text)
    if m:
        a["pattern"] = m.group(1)
    if re.search(r"\[\s*EmailAddress\b", attr_text):
        a["format"] = "email"
    if re.search(r"\[\s*Url\b", attr_text):
        a["format"] = "uri"
    if re.search(r"\[\s*Phone\b", attr_text):
        a["format"] = "phone"
    return a


def body_depth_mask(body: str) -> list:
    """depth[i] = brace depth at char i within body (body excludes outer braces)."""
    depth, d = [], 0
    in_str = False
    for i, ch in enumerate(body):
        if ch == '"' and (i == 0 or body[i - 1] != "\\"):
            in_str = not in_str
        if not in_str:
            if ch == "{":
                depth.append(d); d += 1; continue
            if ch == "}":
                d -= 1
        depth.append(d)
    return depth


def parse_positional_record_params(param_text: str) -> list:
    props = []
    for p in split_top_level(param_text):
        p = p.strip()
        if not p:
            continue
        attrs = " ".join(re.findall(r"\[[^\]]*\]", p))
        p2 = re.sub(r"\[[^\]]*\]", "", p).strip()
        p2 = p2.split("=")[0].strip()
        m = re.match(r"^(?P<type>[\w\.]+(?:\s*<.+>)?(?:\[\])*\??)\s+(?P<name>\w+)$", p2)
        if not m:
            continue
        a = parse_attrs(attrs)
        if a.get("ignore"):
            continue
        t = m.group("type").replace(" ", "")
        props.append(Prop(
            name=m.group("name"), csType=t,
            jsonName=a.get("jsonName", to_camel(m.group("name"))),
            required=a.get("required", not t.endswith("?")) and "=" not in p,
            nullable=t.endswith("?"),
            maxLength=a.get("maxLength"), minLength=a.get("minLength"),
            pattern=a.get("pattern"), minimum=a.get("minimum"), maximum=a.get("maximum"),
            format=a.get("format"),
        ))
    return props


def extract_types(text: str, project: str, rel: str) -> list:
    clean = strip_comments_keep_layout(text)
    ns_m = re.search(r"^\s*namespace\s+([\w\.]+)", clean, re.M)
    ns = ns_m.group(1) if ns_m else ""
    types = []
    for m in TYPE_DECL_RE.finditer(clean):
        kind = re.sub(r"\s+", " ", m.group("kind"))
        name = m.group("name")
        mods = m.group("mods") or ""
        if "private" in mods or "protected" in mods:
            continue
        after = m.end()
        # find '{' or ';' or '(' (positional record) — whichever comes first
        rest = clean[after:]
        positional = None
        if kind.startswith("record"):
            pm = re.match(r"\s*\(", rest)
            if pm:
                open_p = after + pm.end() - 1
                close_p = match_brace(clean, open_p, "(", ")")
                positional = clean[open_p + 1:close_p]
                after = close_p + 1
                rest = clean[after:]
        hdr_m = re.match(r"([^{;]*)([{;])", rest, re.S)
        if not hdr_m:
            continue
        header = hdr_m.group(1)
        base = None
        bm = re.search(r":\s*([\w\.]+(?:<[^>]+>)?)", header)
        if bm:
            cand = bm.group(1)
            short = cand.split(".")[-1]
            if not (re.match(r"^I[A-Z]", short) and kind != "interface"):
                base = re.sub(r"\(.*", "", cand)
        td = TypeDef(
            name=name, kind=kind.split(" ")[0], namespace=ns, project=project, file=rel,
            line=line_of(clean, m.start("name")), description=doc_summary(m.group("doc")),
            baseType=base, isAbstract="abstract" in mods,
            genericParams=[g.strip() for g in (m.group("generic") or "").strip(" <>").split(",") if g.strip()],
        )
        if positional is not None:
            td.properties.extend(parse_positional_record_params(positional))
        if hdr_m.group(2) == "{":
            open_b = after + hdr_m.end() - 1
            close_b = match_brace(clean, open_b)
            body = clean[open_b + 1:close_b]
            if td.kind == "enum":
                for item in split_top_level(re.sub(r"\[[^\]]*\]|///[^\n]*", "", body)):
                    em = re.match(r"^\s*(\w+)", item)
                    if em:
                        td.enumValues.append(em.group(1))
            elif td.kind != "interface":
                # several members on one line ("{ get; set; } public X Y { get; set; }") -> one per line
                body = re.sub(r"([;}])(?=[ \t]*(?:\[[^\]\n]*\][ \t]*)*public\b)", "\\1\n", body)
                depth = body_depth_mask(body)
                for pm in PROP_RE.finditer(body):
                    if pm.start("type") >= len(depth) or depth[pm.start("type")] != 0:
                        continue
                    mods_p = pm.group("mods") or ""
                    if "static" in mods_p:
                        continue
                    attr_text = (pm.group("attrs") or "") + (pm.group("inline_attrs") or "")
                    a = parse_attrs(attr_text)
                    if a.get("ignore"):
                        continue
                    t = re.sub(r"\s+", "", pm.group("type"))
                    td.properties.append(Prop(
                        name=pm.group("name"), csType=t,
                        jsonName=a.get("jsonName", to_camel(pm.group("name"))),
                        required=a.get("required", False) or "required" in mods_p,
                        nullable=t.endswith("?"),
                        description=doc_summary(pm.group("doc")),
                        maxLength=a.get("maxLength"), minLength=a.get("minLength"),
                        pattern=a.get("pattern"), minimum=a.get("minimum"),
                        maximum=a.get("maximum"), format=a.get("format"),
                    ))
        types.append(td)
    return types


# --------------------------------------------------------------------------- #
# Endpoint extraction
# --------------------------------------------------------------------------- #
def classify_param(raw: str, route_params: set, verb: str, known_types: set) -> Optional[Param]:
    raw = raw.strip()
    if not raw:
        return None
    attrs = " ".join(re.findall(r"\[[^\]]*\]", raw))
    body = re.sub(r"\[[^\]]*\]", "", raw).strip()
    body = re.sub(r"^(this|ref|out|in|params)\s+", "", body)
    default = None
    if "=" in body:
        body, default = [x.strip() for x in body.split("=", 1)]
    m = re.match(r"^(?P<type>[\w\.]+(?:\s*<.+>)?(?:\[\])*\??)\s+(?P<name>\w+)$", body)
    if not m:
        return None
    t = m.group("type").replace(" ", "")
    name = m.group("name")
    short = parse_generic(t)[0].split(".")[-1].rstrip("?")
    name_attr = re.search(r"From\w+\(\s*Name\s*=\s*\"([^\"]+)\"", attrs)
    pname = name_attr.group(1) if name_attr else name
    optional = t.endswith("?") or default is not None

    if "FromServices" in attrs or "FromKeyedServices" in attrs:
        return None
    if short in SERVICE_TYPES or (re.match(r"^I[A-Z]", short) and short not in ("IFormFile", "IFormFileCollection")):
        return None
    if re.search(r"(Service|Repository|Context|Client|Handler|Mediator|Factory|Provider|Options|Logger)$", short) and short not in known_types:
        return None
    if "FromBody" in attrs:
        return Param(name=name, csType=t, source="body", required=not optional)
    if "FromForm" in attrs or short in ("IFormFile", "IFormFileCollection"):
        return Param(name=pname, csType=t, source="form", required=not optional)
    if "FromRoute" in attrs:
        return Param(name=pname, csType=t, source="path", required=True)
    if "FromQuery" in attrs:
        return Param(name=pname, csType=t, source="query", required=not optional)
    if "FromHeader" in attrs:
        return Param(name=pname, csType=t, source="header", required=not optional)
    if "AsParameters" in attrs:
        return Param(name=name, csType=t, source="asparameters", required=True)
    if name in route_params or name.lower() in {r.lower() for r in route_params}:
        rp = next((r for r in route_params if r.lower() == name.lower()), name)
        return Param(name=rp, csType=t, source="path", required=True)
    base_short = short.replace("[]", "")
    is_simple = base_short in PRIMITIVES or t.rstrip("?") in PRIMITIVES
    if is_simple or base_short in ("List", "IEnumerable") and all(
            a.strip().rstrip("?") in PRIMITIVES for a in parse_generic(t)[1]):
        return Param(name=pname, csType=t, source="query", required=not optional)
    if verb in ("POST", "PUT", "PATCH"):
        return Param(name=name, csType=t, source="body", required=not optional)
    return Param(name=name, csType=t, source="query", required=not optional)


def route_params_of(path: str) -> set:
    return {re.split(r"[:?=]", p)[0].lstrip("*") for p in re.findall(r"\{([^}]+)\}", path)}


def normalize_route(path: str) -> str:
    """ASP.NET route template -> OpenAPI path: strip constraints/defaults/catch-all."""
    def repl(m):
        inner = m.group(1).lstrip("*")
        return "{" + re.split(r"[:?=]", inner)[0] + "}"
    path = re.sub(r"\{([^}]+)\}", repl, path)
    path = "/" + path.strip("/")
    return re.sub(r"/+", "/", path)


def join_route(*parts) -> str:
    segs = [p.strip("/") for p in parts if p and p.strip("/")]
    return "/" + "/".join(segs)


def find_method(clean: str, name: str):
    m = re.search(
        r"(?P<doc>(?:^[ \t]*///[^\n]*\n)*)(?P<attrs>(?:^[ \t]*\[[^\n]*\][ \t]*\n)*)"
        r"^[ \t]*(?:(?:public|internal|private|protected|static|async|virtual|override)\s+)+"
        r"(?P<ret>[\w\.]+(?:\s*<.+?>)?\??)\s+" + re.escape(name) + r"\s*\(",
        clean, re.M)
    if not m:
        return None
    open_p = m.end() - 1
    close_p = match_brace(clean, open_p, "(", ")")
    return {
        "returnType": re.sub(r"\s+", "", m.group("ret")),
        "params": clean[open_p + 1:close_p],
        "doc": doc_summary(m.group("doc")),
        "attrs": m.group("attrs") or "",
        "line": line_of(clean, m.start("ret")),
        "bodyStart": close_p + 1,
    }


def method_body(clean: str, start: int) -> str:
    m = re.match(r"\s*(\{|=>)", clean[start:])
    if not m:
        return ""
    if m.group(1) == "=>":
        end = clean.find(";", start)
        return clean[start:end]
    ob = start + m.end() - 1
    return clean[ob:match_brace(clean, ob) + 1]


def produces_from_chain(chain: str) -> dict:
    res = {}
    for m in re.finditer(r"\.Produces(?:<\s*(?P<t>[^>(]+(?:<[^()]*>)?)\s*>)?\(\s*(?:(?:statusCode\s*:\s*)?(?:StatusCodes\.Status(?P<sc>\d{3})\w*|(?P<num>\d{3})))?", chain):
        code = m.group("sc") or m.group("num") or "200"
        res[code] = m.group("t").strip() if m.group("t") else None
    for m in re.finditer(r"\.ProducesProblem\(\s*(?:StatusCodes\.Status(\d{3})\w*|(\d{3}))", chain):
        res[m.group(1) or m.group(2)] = "ProblemDetails"
    if ".ProducesValidationProblem(" in chain:
        res["400"] = "HttpValidationProblemDetails"
    return res


def chain_meta(chain: str) -> dict:
    meta = {}
    m = re.search(r"\.WithName\(\s*\"([^\"]+)\"", chain)
    if m:
        meta["operationId"] = m.group(1)
    tags = []
    for tm in re.finditer(r"\.WithTags\(([^)]*)\)", chain):
        tags += re.findall(r"\"([^\"]+)\"", tm.group(1))
    if tags:
        meta["tags"] = tags
    m = re.search(r"\.WithSummary\(\s*\"([^\"]+)\"", chain)
    if m:
        meta["summary"] = m.group(1)
    m = re.search(r"\.WithDescription\(\s*\"([^\"]+)\"", chain)
    if m:
        meta["description"] = m.group(1)
    m = re.search(r"\.Accepts<\s*([^>]+?)\s*>\(\s*\"([^\"]+)\"", chain)
    if m:
        meta["accepts"] = (m.group(1), m.group(2))
    if ".AllowAnonymous(" in chain:
        meta["auth"] = "anonymous"
    elif ".RequireAuthorization(" in chain:
        meta["auth"] = "required"
    if ".ExcludeFromDescription(" in chain:
        meta["excluded"] = True
    return meta


def statement_end(clean: str, start: int) -> int:
    """End of a C# statement beginning at start (balanced parens/braces until ';')."""
    depth, i, n = 0, start, len(clean)
    in_str = False
    while i < n:
        c = clean[i]
        if c == '"' and clean[i - 1] != "\\":
            in_str = not in_str
        elif not in_str:
            if c in "({[":
                depth += 1
            elif c in ")}]":
                depth -= 1
            elif c == ";" and depth <= 0:
                return i
        i += 1
    return n


def extract_minimal_apis(text: str, project: str, rel: str, known_types: set, file_index: dict) -> list:
    clean = strip_comments_keep_layout(text)
    endpoints = []
    # group prefixes: var claims = app.MapGroup("/api/claims").WithTags("Claims");
    groups = {}
    for gm in re.finditer(r"(?:var|RouteGroupBuilder)\s+(\w+)\s*=\s*(\w+)\s*\.MapGroup\(\s*\"([^\"]*)\"\s*\)", clean):
        var, parent, prefix = gm.group(1), gm.group(2), gm.group(3)
        stmt = clean[gm.start():statement_end(clean, gm.start())]
        parent_prefix, parent_tags, parent_auth = groups.get(parent, ("", [], ""))
        meta = chain_meta(stmt)
        groups[var] = (join_route(parent_prefix, prefix), parent_tags + meta.get("tags", []), meta.get("auth", parent_auth))
    # extension-method groups: static void MapClaimEndpoints(this IEndpointRouteBuilder app) ...
    for m in re.finditer(r"\b(\w+)\s*\.\s*Map(" + "|".join(HTTP_VERBS) + r")\s*\(\s*\"([^\"]*)\"\s*,", clean):
        var, verb, route = m.group(1), m.group(2).upper(), m.group(3)
        end = statement_end(clean, m.start())
        stmt = clean[m.start():end]
        open_p = m.start() + clean[m.start():].find("(")
        close_p = match_brace(clean, open_p, "(", ")")
        args = clean[open_p + 1:close_p]
        chain = clean[close_p + 1:end]
        handler_expr = split_top_level(args)[1] if len(split_top_level(args)) > 1 else ""
        prefix, gtags, gauth = groups.get(var, ("", [], ""))
        full_path = normalize_route(join_route(prefix, route))
        rparams = route_params_of(join_route(prefix, route))
        meta = chain_meta(chain)
        ep = Endpoint(method=verb, path=full_path, style="minimal-api", project=project, file=rel,
                      line=line_of(clean, m.start()))
        ep.tags = meta.get("tags") or gtags
        ep.operationId = meta.get("operationId", "")
        ep.summary = meta.get("summary", "")
        ep.description = meta.get("description", "")
        ep.auth = meta.get("auth", gauth)
        if meta.get("excluded"):
            ep.needsReview.append("ExcludeFromDescription() is set - confirm whether to include")

        ret_type = None
        lam = re.match(r"^\s*(?:static\s+)?(?:async\s+)?\((?P<params>.*?)\)\s*(?::\s*(?P<ret>[^=]+?))?\s*=>(?P<body>.*)$", handler_expr, re.S)
        lam_single = re.match(r"^\s*(?:async\s+)?(?P<p>\w+)\s*=>", handler_expr)
        param_text, body_text = "", ""
        if lam:
            param_text, body_text = lam.group("params"), lam.group("body")
            ret_type = lam.group("ret")
            ep.handler = "lambda"
        elif lam_single:
            ep.handler = "lambda"
            body_text = handler_expr
        else:
            hname = handler_expr.strip().split(".")[-1]
            hname = re.sub(r"<.*", "", hname)
            ep.handler = handler_expr.strip()
            found = find_method(clean, hname)
            src_clean = clean
            if not found:
                for other_rel, other_clean in file_index.get(project, {}).items():
                    found = find_method(other_clean, hname)
                    if found:
                        src_clean = other_clean
                        break
            if found:
                param_text = found["params"]
                ret_type = found["returnType"]
                body_text = method_body(src_clean, found["bodyStart"])
                if found["doc"] and not ep.summary:
                    ep.summary = found["doc"]
                if not ep.operationId:
                    ep.operationId = hname
            else:
                ep.needsReview.append(f"Handler '{ep.handler}' not found in project source - specify request/response in overrides")

        for raw in split_top_level(param_text):
            p = classify_param(raw, rparams, verb, known_types)
            if not p:
                continue
            if p.source == "body":
                ep.requestBody = p.csType
            else:
                ep.params.append(p)

        if "accepts" in meta:
            ep.requestBody, ep.requestContentType = meta["accepts"]

        responses = produces_from_chain(chain)
        typed = results_status_codes(ret_type)
        for k, v in typed.items():
            responses.setdefault(k, v)
        if not any(k.startswith("2") for k in responses):
            payload = unwrap_result_type(ret_type)
            if payload:
                responses["200"] = payload
            else:
                inferred = infer_from_body(body_text, verb)
                if inferred:
                    responses.update({k: v for k, v in inferred.items() if k not in responses})
        if not any(k.startswith("2") for k in responses):
            responses["200"] = None
            ep.needsReview.append("Success response type could not be determined statically")
        ep.responses = responses
        endpoints.append(ep)
    return endpoints


def infer_from_body(body: str, verb: str) -> dict:
    """Best-effort: TypedResults.Ok(new Foo(...)) / Results.Created(..., new Foo{...})."""
    res = {}
    for m in re.finditer(r"(?:TypedResults|Results)\.(Ok|Created|Accepted|NoContent|NotFound|BadRequest|Conflict)\s*(?:<\s*([^>]+)\s*>)?\(([^;]*)", body):
        kind, gen, args = m.group(1), m.group(2), m.group(3)
        code = {"Ok": "200", "Created": "201", "Accepted": "202", "NoContent": "204",
                "NotFound": "404", "BadRequest": "400", "Conflict": "409"}[kind]
        typ = gen
        if not typ:
            nm = re.search(r"new\s+([A-Z]\w*(?:<[^>]+>)?)\s*[({]", args)
            typ = nm.group(1) if nm else None
        if code not in res or (typ and not res[code]):
            res[code] = typ
    for m in re.finditer(r"new\s+(Ok|Created|Accepted)ObjectResult\(\s*new\s+([A-Z]\w*)", body):
        res.setdefault({"Ok": "200", "Created": "201", "Accepted": "202"}[m.group(1)], m.group(2))
    # MVC controller helpers: return NoContent(); return Ok(new Foo{..}); CreatedAtAction(.., new Foo(..))
    if re.search(r"(?<![\w.])NoContent\(\s*\)", body):
        res.setdefault("204", None)
    if re.search(r"(?<![\w.])NotFound\(", body):
        res.setdefault("404", None)
    for m in re.finditer(r"(?<![\w.])(Ok|Accepted|CreatedAtAction|CreatedAtRoute|Created)\(([^;]*)", body):
        code = {"Ok": "200", "Accepted": "202"}.get(m.group(1), "201")
        nm = re.search(r"new\s+([A-Z]\w*(?:<[^>]+>)?)\s*[({]", m.group(2))
        if nm:
            res[code] = nm.group(1)
    return res


def extract_controllers(text: str, project: str, rel: str, known_types: set) -> list:
    clean = strip_comments_keep_layout(text)
    endpoints = []
    for cm in re.finditer(
            r"(?P<attrs>(?:^[ \t]*\[[^\n]*\][ \t]*\n)*)^[ \t]*(?:public\s+)?(?:sealed\s+|abstract\s+|partial\s+)*class\s+(?P<name>\w+)\s*(?:\([^)]*\))?\s*:\s*(?P<base>[^{]+)\{",
            clean, re.M):
        attrs, cname, base = cm.group("attrs"), cm.group("name"), cm.group("base")
        if "[ApiController" not in attrs and not re.search(r"\b(ControllerBase|Controller|ApiControllerBase)\b", base):
            continue
        croute = ""
        rm = re.search(r"\[Route\(\s*\"([^\"]*)\"", attrs)
        if rm:
            croute = rm.group(1)
        ctag = cname[:-10] if cname.endswith("Controller") else cname
        croute = croute.replace("[controller]", ctag.lower() if "[controller]" in croute else ctag)
        class_auth = "anonymous" if "[AllowAnonymous" in attrs else ("required" if "[Authorize" in attrs else "")
        ob = cm.end() - 1
        cb = match_brace(clean, ob)
        body = clean[ob + 1:cb]
        offset = ob + 1
        for mm in re.finditer(
                r"(?P<doc>(?:^[ \t]*///[^\n]*\n)*)(?P<attrs>(?:^[ \t]*\[[^\n]*\][ \t]*\n)+)"
                r"^[ \t]*public\s+(?:(?:async|virtual|override)\s+)*(?P<ret>[\w\.]+(?:\s*<.+?>)?\??)\s+(?P<name>\w+)\s*\(",
                body, re.M):
            mattrs = mm.group("attrs")
            vm = re.search(r"\[Http(" + "|".join(HTTP_VERBS) + r")(?:\(\s*\"([^\"]*)\"[^)]*\))?\]", mattrs)
            if not vm:
                vm2 = re.search(r"\[Http(" + "|".join(HTTP_VERBS) + r")\b", mattrs)
                if not vm2:
                    continue
                verb, mroute = vm2.group(1).upper(), ""
            else:
                verb, mroute = vm.group(1).upper(), vm.group(2) or ""
            rm2 = re.search(r"\[Route\(\s*\"([^\"]*)\"", mattrs)
            if rm2:
                mroute = rm2.group(1)
            if mroute.startswith("~/"):
                path_t = mroute[1:]
            elif mroute.startswith("/"):
                path_t = mroute
            else:
                path_t = join_route(croute, mroute)
            path_t = path_t.replace("[action]", mm.group("name"))
            open_p = mm.end() - 1
            close_p = match_brace(body, open_p, "(", ")")
            ep = Endpoint(method=verb, path=normalize_route(path_t), style="controller", project=project,
                          file=rel, line=line_of(clean, offset + mm.start("ret")),
                          handler=f"{cname}.{mm.group('name')}",
                          operationId=(mm.group("name") if ctag.lower().rstrip("s") in mm.group("name").lower()
                                       else mm.group("name") + ctag),
                          tags=[ctag], summary=doc_summary(mm.group("doc")))
            ep.auth = "anonymous" if "[AllowAnonymous" in mattrs else ("required" if "[Authorize" in mattrs else class_auth)
            nm = re.search(r"Name\s*=\s*\"([^\"]+)\"", vm.group(0) if vm else "")
            if nm:
                ep.operationId = nm.group(1)
            rparams = route_params_of(path_t)
            for raw in split_top_level(body[open_p + 1:close_p]):
                p = classify_param(raw, rparams, verb, known_types)
                if not p:
                    continue
                if p.source == "body":
                    ep.requestBody = p.csType
                else:
                    ep.params.append(p)
            responses = {}
            for pr in re.finditer(r"\[ProducesResponseType(?:<\s*([^>]+)\s*>)?\(\s*(?:typeof\(\s*([^)]+)\)\s*,\s*)?(?:StatusCodes\.Status(\d{3})\w*|(\d{3}))", mattrs):
                code = pr.group(3) or pr.group(4)
                responses[code] = (pr.group(1) or pr.group(2) or "").strip() or None
            if not any(k.startswith("2") for k in responses):
                payload = unwrap_result_type(re.sub(r"\s+", "", mm.group("ret")))
                if payload:
                    responses["200"] = payload
                else:
                    inferred = infer_from_body(method_body(body, close_p + 1), verb)
                    responses.update({k: v for k, v in inferred.items() if k not in responses})
            if not any(k.startswith("2") for k in responses):
                responses["200"] = None
                ep.needsReview.append("Success response type could not be determined statically (IActionResult)")
            ep.responses = responses
            endpoints.append(ep)
    return endpoints


def extract_functions(text: str, project: Project, rel: str, known_types: set) -> tuple:
    clean = strip_comments_keep_layout(text)
    endpoints, others = [], []
    for fm in re.finditer(r"\[(Function|FunctionName)\(\s*(?:nameof\((\w+)\)|\"([^\"]+)\")\s*\)\]", clean):
        fname = fm.group(2) or fm.group(3)
        # method signature after the attribute
        sig_m = re.compile(
            r"(?:\s*\[[^\n]*\]\s*)*\s*(?:(?:public|internal|static|async|private)\s+)+(?P<ret>[\w\.]+(?:\s*<.+?>)?\??)\s+(?P<name>\w+)\s*\(",
            re.S).match(clean, fm.end())
        if not sig_m:
            continue
        open_p = sig_m.end() - 1
        close_p = match_brace(clean, open_p, "(", ")")
        params_text = clean[open_p + 1:close_p]
        # attributes stacked above [Function] (OpenApi* attrs) + between
        attr_start = clean.rfind("\n\n", 0, fm.start())
        above = clean[max(attr_start, 0):fm.start()]
        attr_block = above + clean[fm.end():open_p]
        doc = doc_summary(above)
        ht = re.search(r"\[HttpTrigger\(([^\]]*)\)\]", params_text, re.S)
        if not ht:
            trig = next((t for t in NON_HTTP_TRIGGERS if f"[{t}" in params_text), None)
            if trig:
                detail = re.search(r"\[" + trig + r"\(([^\]]*)\)\]", params_text)
                others.append({"function": fname, "trigger": trig, "project": project.name, "file": rel,
                               "line": line_of(clean, fm.start()),
                               "binding": (detail.group(1).strip() if detail else "")})
            continue
        targs = ht.group(1)
        verbs = [v.upper() for v in re.findall(r"\"(get|post|put|delete|patch|head|options)\"", targs, re.I)]
        if not verbs:
            verbs = ["GET", "POST"]     # Functions default: all methods; treat get/post as needs-review
        route_m = re.search(r"Route\s*=\s*\"([^\"]*)\"", targs)
        route = route_m.group(1) if route_m else fname
        level = re.search(r"AuthorizationLevel\.(\w+)", targs)
        full = normalize_route(join_route(project.routePrefix, route))
        rparams = route_params_of(route)
        body = method_body(clean, close_p + 1)

        req_type = None
        rb = re.search(r"\[OpenApiRequestBody\([^\]]*?bodyType\s*:\s*typeof\(\s*([^)]+)\)", attr_block, re.S) or \
             re.search(r"\[OpenApiRequestBody\(\s*(?:contentType\s*:\s*)?\"[^\"]*\"\s*,\s*typeof\(\s*([^)]+)\)", attr_block, re.S)
        if rb:
            req_type = rb.group(1).strip()
        else:
            for pat in (r"ReadFromJsonAsync<\s*([^>]+?)\s*>", r"Deserialize(?:Async)?<\s*([^>]+?)\s*>",
                        r"DeserializeObject<\s*([^>]+?)\s*>", r"ReadAsAsync<\s*([^>]+?)\s*>"):
                bm = re.search(pat, body)
                if bm:
                    req_type = bm.group(1).strip(); break
        fb = re.search(r"\[FromBody\]\s*([\w\.<>\[\]?]+)\s+\w+", params_text)
        if fb:
            req_type = fb.group(1)

        responses = {}
        for orb in re.finditer(r"\[OpenApiResponseWith(?:out)?Body\(([^\]]*)\)\]", attr_block, re.S):
            a = orb.group(1)
            sc = re.search(r"HttpStatusCode\.(\w+)", a)
            code = http_status_code(sc.group(1)) if sc else "200"
            bt = re.search(r"bodyType\s*:\s*typeof\(\s*([^)]+)\)", a) or re.search(r"typeof\(\s*([^)]+)\)", a)
            responses[code] = bt.group(1).strip() if bt else None
        if not any(k.startswith("2") for k in responses):
            inferred = infer_from_body(body, verbs[0])
            responses.update({k: v for k, v in inferred.items() if k not in responses})
            if not any(k.startswith("2") for k in responses):
                wm = re.search(r"WriteAsJsonAsync\(\s*(?:new\s+([A-Z]\w*)|(\w+))", body)
                payload = None
                if wm and wm.group(1):
                    payload = wm.group(1)
                elif wm and wm.group(2):
                    vm = re.search(r"(?:var|[A-Z][\w<>]*)\s+" + re.escape(wm.group(2)) + r"\s*=\s*(?:await\s+)?new\s+([A-Z]\w*)", body)
                    payload = vm.group(1) if vm else None
                responses["200"] = payload

        op_attr = re.search(r"\[OpenApiOperation\(([^\]]*)\)\]", attr_block, re.S)
        tags, summary, op_id = [], doc, ""
        if op_attr:
            oa = op_attr.group(1)
            m1 = re.search(r"operationId\s*:\s*\"([^\"]+)\"", oa) or re.search(r"^\s*\"([^\"]+)\"", oa)
            op_id = m1.group(1) if m1 else ""
            tags = re.findall(r"tags\s*:\s*new\s*\[\]\s*\{([^}]*)\}", oa)
            tags = re.findall(r"\"([^\"]+)\"", tags[0]) if tags else []
            sm = re.search(r"Summary\s*=\s*\"([^\"]+)\"", oa)
            summary = sm.group(1) if sm else summary

        extra_params = []
        for op in re.finditer(r"\[OpenApiParameter\(([^\]]*)\)\]", attr_block, re.S):
            a = op.group(1)
            nm = re.search(r"name\s*:\s*\"([^\"]+)\"", a) or re.search(r"^\s*\"([^\"]+)\"", a)
            if not nm:
                continue
            loc = re.search(r"ParameterLocation\.(\w+)", a)
            ty = re.search(r"Type\s*=\s*typeof\(\s*([^)]+)\)", a)
            reqd = re.search(r"Required\s*=\s*(true|false)", a)
            extra_params.append(Param(name=nm.group(1), csType=(ty.group(1) if ty else "string"),
                                      source=(loc.group(1).lower() if loc else "query"),
                                      required=(reqd.group(1) == "true") if reqd else False,
                                      description=(re.search(r"Description\s*=\s*\"([^\"]+)\"", a) or [None, ""])[1] if re.search(r"Description\s*=\s*\"([^\"]+)\"", a) else ""))
        for verb in verbs:
            ep = Endpoint(method=verb, path=full, style="azure-function", project=project.name, file=rel,
                          line=line_of(clean, fm.start()), handler=f"{fname} ({sig_m.group('name')})",
                          operationId=(op_id or fname) + ("" if len(verbs) == 1 else to_pascal_words(verb.lower())),
                          tags=tags, summary=summary)
            ep.auth = f"function-key:{level.group(1)}" if level else ""
            for rp in sorted(rparams):
                tm = re.search(r"\b([\w\.]+\??)\s+" + re.escape(rp) + r"\b", params_text)
                ep.params.append(Param(name=rp, csType=(tm.group(1) if tm and "HttpTrigger" not in tm.group(1) else "string"), source="path"))
            for qp in re.finditer(r"req\.Query\[\s*\"([^\"]+)\"\s*\]|GetQueryParameterDictionary\(\)\[\s*\"([^\"]+)\"\s*\]", body):
                qn = qp.group(1) or qp.group(2)
                if not any(p.name == qn for p in ep.params):
                    ep.params.append(Param(name=qn, csType="string", source="query", required=False))
            for p in extra_params:
                if not any(x.name == p.name for x in ep.params):
                    ep.params.append(p)
            if verb in ("POST", "PUT", "PATCH"):
                ep.requestBody = req_type
                if not req_type:
                    ep.needsReview.append("Request body type not found (no OpenApiRequestBody / ReadFromJsonAsync<T>)")
            ep.responses = dict(responses)
            if not route_m:
                ep.needsReview.append("No Route on HttpTrigger - path defaults to function name")
            if not re.findall(r"\"(get|post|put|delete|patch|head|options)\"", targs, re.I):
                ep.needsReview.append("HttpTrigger declares no methods (accepts all) - confirm which verbs are real")
            if any(k.startswith("2") and v is None for k, v in responses.items()) and "204" not in responses:
                ep.needsReview.append("Response body type not statically declared - read the function body and set it in overrides")
            endpoints.append(ep)
    return endpoints, others


def http_status_code(name: str) -> str:
    table = {"OK": "200", "Created": "201", "Accepted": "202", "NoContent": "204",
             "BadRequest": "400", "Unauthorized": "401", "Forbidden": "403", "NotFound": "404",
             "Conflict": "409", "UnprocessableEntity": "422", "InternalServerError": "500"}
    return table.get(name, "default")


def to_dict(obj):
    if isinstance(obj, list):
        return [to_dict(o) for o in obj]
    if hasattr(obj, "__dataclass_fields__"):
        return {k: to_dict(v) for k, v in asdict(obj).items()}
    return obj
