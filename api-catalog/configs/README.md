Central-repo mode: one config per application, e.g. `EU-claims.yaml`, with `repoRoot` pointing at the
checked-out application repository (submodule or CI checkout) and output dirs under `api-catalog/`.
Paths in a config are relative to the config file.

```yaml
repoRoot: ../../repos/claims          # the application repository
region: EU
application: claims
sourceRoots: [src]
maxIterations: 5
discovery: {outputDir: ../discovery/EU/claims}
analysis:  {outputDir: ../analysis/EU/claims, domainsXlsx: ../domains.xlsx, domainsJson: ../domains.json}
```
