// TypeExtractor - dump public model types from compiled assemblies (NuGet packages, shared DLLs)
// into the JSON format used by the api-discovery skill (overrides.yaml -> extraTypeFiles).
//
// Loads assemblies with MetadataLoadContext: types are INSPECTED, never executed.
//
// Usage:
//   dotnet run --project tools/TypeExtractor -- \
//       --assembly path/to/Contoso.Common.dll [--assembly other.dll] \
//       [--probe path/to/bin/folder] [--namespace Contoso.Common.Models] [--type Money --type Address] \
//       --out api-catalog/discovery/EU/claims/types/contoso-common.types.json
//
// XML docs: if Contoso.Common.xml sits next to the DLL, <summary> texts are used as descriptions.

using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Xml.Linq;

var assemblies = new List<string>(); var probes = new List<string>();
var namespaces = new List<string>(); var onlyTypes = new HashSet<string>(); string? outPath = null;
for (int i = 0; i < args.Length; i++)
{
    switch (args[i])
    {
        case "--assembly": assemblies.Add(args[++i]); break;
        case "--probe": probes.Add(args[++i]); break;
        case "--namespace": namespaces.Add(args[++i]); break;
        case "--type": onlyTypes.Add(args[++i]); break;
        case "--out": outPath = args[++i]; break;
    }
}
if (assemblies.Count == 0 || outPath is null)
{
    Console.Error.WriteLine("usage: --assembly <dll> [--probe <dir>] [--namespace <ns>] [--type <Name>] --out <file.json>");
    return 2;
}

var paths = new List<string>(Directory.GetFiles(RuntimeEnvironment.GetRuntimeDirectory(), "*.dll"));
foreach (var a in assemblies) paths.AddRange(Directory.GetFiles(Path.GetDirectoryName(Path.GetFullPath(a))!, "*.dll"));
foreach (var p in probes) paths.AddRange(Directory.GetFiles(p, "*.dll", SearchOption.AllDirectories));
var resolver = new PathAssemblyResolver(paths.Distinct(StringComparer.OrdinalIgnoreCase));
using var mlc = new MetadataLoadContext(resolver);

var result = new List<object>();
foreach (var asmPath in assemblies)
{
    var asm = mlc.LoadFromAssemblyPath(Path.GetFullPath(asmPath));
    var docs = LoadXmlDocs(Path.ChangeExtension(asmPath, ".xml"));
    Type[] types;
    try { types = asm.GetExportedTypes(); }
    catch (ReflectionTypeLoadException ex) { types = ex.Types.Where(t => t != null).ToArray()!; }

    foreach (var t in types)
    {
        if (t.IsInterface || t.IsNested && !t.IsNestedPublic) continue;
        if (IsStaticClass(t) || IsDelegate(t)) continue;
        if (namespaces.Count > 0 && !namespaces.Any(n => (t.Namespace ?? "").StartsWith(n))) continue;
        var simple = SimpleName(t);
        if (onlyTypes.Count > 0 && !onlyTypes.Contains(simple)) continue;

        var props = new List<object>();
        if (!t.IsEnum)
        {
            foreach (var p in t.GetProperties(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly))
            {
                if (p.GetIndexParameters().Length > 0 || p.GetMethod is null || !p.GetMethod.IsPublic) continue;
                var attrs = p.GetCustomAttributesData();
                if (attrs.Any(a => a.AttributeType.Name is "JsonIgnoreAttribute" or "IgnoreDataMemberAttribute")) continue;
                var jsonName = attrs.FirstOrDefault(a => a.AttributeType.Name is "JsonPropertyNameAttribute" or "JsonPropertyAttribute")
                                    ?.ConstructorArguments.FirstOrDefault().Value as string;
                var required = attrs.Any(a => a.AttributeType.Name is "RequiredAttribute" or "JsonRequiredAttribute" or "RequiredMemberAttribute");
                int? maxLen = attrs.FirstOrDefault(a => a.AttributeType.Name is "MaxLengthAttribute" or "StringLengthAttribute")
                                   ?.ConstructorArguments.FirstOrDefault().Value as int?;
                var csType = CsName(p.PropertyType);
                props.Add(new
                {
                    name = p.Name,
                    csType,
                    jsonName = jsonName ?? char.ToLowerInvariant(p.Name[0]) + p.Name[1..],
                    required,
                    nullable = csType.EndsWith("?"),
                    description = docs.GetValueOrDefault($"P:{t.FullName}.{p.Name}", ""),
                    maxLength = maxLen,
                });
            }
        }
        result.Add(new
        {
            name = simple,
            kind = t.IsEnum ? "enum" : (t.IsValueType ? "struct" : "class"),
            @namespace = t.Namespace ?? "",
            project = asm.GetName().Name,
            file = Path.GetFileName(asmPath),
            line = 0,
            description = docs.GetValueOrDefault($"T:{t.FullName}", ""),
            baseType = t.BaseType is { } b && !b.FullName!.StartsWith("System.") ? CsName(b) : null,
            genericParams = t.IsGenericTypeDefinition ? t.GetGenericArguments().Select(g => g.Name).ToArray() : Array.Empty<string>(),
            properties = props,
            enumValues = t.IsEnum ? t.GetFields(BindingFlags.Public | BindingFlags.Static).Select(f => f.Name).ToArray() : Array.Empty<string>(),
            isAbstract = t.IsAbstract && !t.IsSealed,
            schemaKey = simple,
        });
    }
}

Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(outPath))!);
File.WriteAllText(outPath, JsonSerializer.Serialize(new { types = result }, new JsonSerializerOptions { WriteIndented = true }));
Console.WriteLine($"{result.Count} types written to {outPath}");
return 0;

static bool IsStaticClass(Type t) => t.IsClass && t.IsAbstract && t.IsSealed;
static bool IsDelegate(Type t) => t.BaseType?.FullName is "System.MulticastDelegate";
static string SimpleName(Type t) { var n = t.Name; var i = n.IndexOf('`'); return i > 0 ? n[..i] : n; }

static string CsName(Type t)
{
    if (t.IsGenericParameter) return t.Name;
    if (t.IsArray) return CsName(t.GetElementType()!) + "[]";
    if (t.IsGenericType && t.GetGenericTypeDefinition().FullName == "System.Nullable`1") return CsName(t.GetGenericArguments()[0]) + "?";
    var keyword = t.FullName switch
    {
        "System.String" => "string", "System.Int32" => "int", "System.Int64" => "long", "System.Int16" => "short",
        "System.Boolean" => "bool", "System.Decimal" => "decimal", "System.Double" => "double", "System.Single" => "float",
        "System.Byte" => "byte", "System.Object" => "object", "System.Char" => "char", _ => null,
    };
    if (keyword != null) return keyword;
    if (t.IsGenericType) return SimpleName(t) + "<" + string.Join(",", t.GetGenericArguments().Select(CsName)) + ">";
    return t.Name;
}

static Dictionary<string, string> LoadXmlDocs(string path)
{
    var d = new Dictionary<string, string>();
    if (!File.Exists(path)) return d;
    foreach (var m in XDocument.Load(path).Descendants("member"))
    {
        var name = m.Attribute("name")?.Value; var summary = m.Element("summary")?.Value;
        if (name != null && summary != null) d[name] = string.Join(" ", summary.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries));
    }
    return d;
}
