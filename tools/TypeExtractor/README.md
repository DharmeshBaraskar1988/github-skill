# TypeExtractor

Dumps public model types from compiled assemblies (NuGet packages, shared libraries from other repos) into the
JSON format that `build_openapi.py` reads through `extraTypeFiles` in `overrides.yaml`. Use it when discovery
reports **D05 Unresolved C# type** for types you do not have as source.

```bash
dotnet run --project tools/TypeExtractor -- \
  --assembly ~/.nuget/packages/contoso.common/4.2.0/lib/net8.0/Contoso.Common.dll \
  --namespace Contoso.Common.Models \
  --out api-catalog/discovery/EU/claims/types/contoso-common.types.json
```

Then in `overrides.yaml`:
```yaml
extraTypeFiles:
  - types/contoso-common.types.json
```

Assemblies are loaded with `MetadataLoadContext` (inspection only, no code runs). If `Contoso.Common.xml`
is next to the DLL, XML `<summary>` docs become descriptions.

> Status: written against .NET 8 `System.Reflection.MetadataLoadContext` 8.0. It was not compiled in the
> environment where this kit was produced (no .NET SDK there) - build it once (`dotnet build tools/TypeExtractor`)
> and fix any compiler message before relying on it. The JSON contract it must produce is the `types[]` shape in
> `inventory.json`.
