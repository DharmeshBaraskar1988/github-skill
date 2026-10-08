# overrides.yaml reference (api-discovery)

`overrides.yaml` lives next to `inventory.json` in the discovery output folder. It is the only
place where the agent corrects or completes what the scanner found. `build_openapi.py` applies it
on every run, so the spec stays reproducible. Every entry should carry a `note` (or `reason` for
excludes) that names the file and line you checked.

```yaml
endpoints:                       # corrections to scanned endpoints
  - match: {operationId: GetFnolStatus}          # or {method: GET, path: /fn/fnol/{reference}}
    note: FnolFunctions.cs:31 writes FnolReceipt
    set:
      summary: Get FNOL processing status
      description: Longer text (optional)
      tags: [Fnol]                               # original tags; domains are added later by api-analysis
      operationId: GetFnolStatus                 # rename (must stay unique)
      requestBody: CreateClaimRequest            # C# type name, or null for no body
      requestContentType: application/json
      responses: {"200": FnolReceipt, "404": null}   # status -> C# type (null = no body)
      params:                                    # replaces all parameters
        - {name: reference, source: path, csType: string}
      addParams:                                 # appends parameters
        - {name: x-correlation-id, source: header, csType: string, required: false}
      auth: required                             # required | anonymous | function-key:Function

  - match: {method: GET, path: /health}
    exclude: true
    reason: Liveness probe for the load balancer, not part of the business contract

addEndpoints:                    # endpoints the scanner could not see (D03)
  - method: POST
    path: /api/v1/claims/{claimId}/notes
    operationId: AddClaimNote
    project: Claims.Api
    file: src/Claims.Api/Endpoints/NoteEndpoints.cs
    line: 42
    tags: [Claims]
    params: [{name: claimId, source: path, csType: Guid}]
    requestBody: AddNoteRequest
    responses: {"201": ClaimNote}

types:                           # descriptions for scanned C# types
  ClaimDto:
    description: Claim summary used in lists.
    properties:
      lossDate: {description: Date the loss occurred (policy local time).}

externalTypes:                   # types from NuGet / other repos, as OpenAPI schemas
  Money:
    type: object
    x-source-project: Contoso.Common (NuGet 4.2.0)
    properties:
      amount: {type: number, format: double}
      currency: {type: string, maxLength: 3}
    required: [amount, currency]

extraTypeFiles:                  # JSON produced by tools/TypeExtractor from compiled DLLs
  - types/contoso-common.types.json
```

Rules
- C# type expressions are allowed anywhere a type is expected: `List<ClaimDto>`, `PagedResult<ClaimDto>`, `Guid?`.
- `responses` replaces the whole response map of the endpoint; include error codes you want documented.
- An override with `set` clears the endpoint's `needsReview` items (you are asserting you checked it).
