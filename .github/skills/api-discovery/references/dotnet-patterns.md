# .NET patterns recognised by scan_dotnet.py

## Project classification (from *.csproj)
| Signal | kind |
|---|---|
| PackageReference `Microsoft.Azure.Functions.Worker*` | functions-isolated |
| PackageReference `Microsoft.NET.Sdk.Functions` or `<AzureFunctionsVersion>` | functions-inprocess |
| `Sdk="Microsoft.NET.Sdk.Web"` | web |
| otherwise | library (models, extension-method endpoint registrations are still scanned) |

Test projects (`*Tests*`), `bin`, `obj`, `Migrations` are excluded by default (`exclude:` in config adds more).

## Minimal APIs
- `app.MapGet|MapPost|MapPut|MapDelete|MapPatch("route", handler)` on any builder variable
- `var g = app.MapGroup("/prefix").WithTags(..).RequireAuthorization();` nested groups supported
- Handler: lambda `(params) => ...` or method group (`ListClaims`, `Handlers.ListClaims`) resolved in the same project
- Response: `.Produces<T>(code)`, `.ProducesProblem`, `.ProducesValidationProblem`, return types
  `Task<Ok<T>>`, `Results<Ok<T>, NotFound>`, `T`, or body inference from `TypedResults.Ok(new T(..))`
- Request: `[FromBody]`, `[FromQuery]`, `[FromRoute]`, `[FromHeader]`, `[AsParameters]`, `.Accepts<T>("content/type")`;
  complex types on POST/PUT/PATCH default to body; interfaces / `*Service` / `CancellationToken` / `HttpContext` are ignored
- Metadata: `.WithName` (operationId), `.WithTags`, `.WithSummary`, `.WithDescription`, `.AllowAnonymous`, `.ExcludeFromDescription`

## Controllers
- `[ApiController]` or `: ControllerBase`, `[Route("api/[controller]")]`, `[HttpGet("{id}")]`, `[Route]` on actions, `~/` overrides
- `ActionResult<T>`, `[ProducesResponseType(typeof(T), 200)]`, `[ProducesResponseType<T>(200)]`, `NoContent()`, `Ok(new T{..})`
- `IFormFile` / `[FromForm]` -> multipart/form-data

## Azure Functions
- Isolated `[Function("Name")]` and in-process `[FunctionName("Name")]`
- `[HttpTrigger(AuthorizationLevel.X, "get", "post", Route = "claims/{id}")]`; default route = function name;
  prefix from `host.json` `extensions.http.routePrefix` (default `api`)
- Request: `[OpenApiRequestBody(bodyType: typeof(T))]`, `ReadFromJsonAsync<T>`, `Deserialize<T>`, `DeserializeObject<T>`, `[FromBody] T`
- Response: `[OpenApiResponseWithBody(statusCode: HttpStatusCode.OK, bodyType: typeof(T))]`, `WriteAsJsonAsync(new T())`,
  `new OkObjectResult(new T())`, `[OpenApiParameter]`, `[OpenApiOperation(operationId, tags)]`, `req.Query["x"]`
- Non-HTTP triggers (ServiceBus, Queue, Timer, EventGrid, EventHub, Blob, CosmosDB, Kafka, Durable) are listed in
  `x-non-http-functions`, not in `paths`

## Models
- `class`, `record` (incl. positional), `record struct`, `struct`, `enum`; public instance properties
- Inheritance flattened (`x-base-type` keeps the base), generic types closed (`PagedResult<ClaimDto>` -> `PagedResultOfClaimDto`)
- `[Required]`, `required` keyword, `[MaxLength]`, `[StringLength]`, `[MinLength]`, `[Range]`, `[RegularExpression]`,
  `[EmailAddress]`, `[Url]`, `[JsonPropertyName]`, `[JsonProperty]`, `[JsonIgnore]`, XML `<summary>`
- Same type name in two projects with different shapes -> `Name_Project` schema keys (reported in needsReview)
- JSON names are camelCase (System.Text.Json default). If a service uses PascalCase or snake_case serialisation,
  record it in overrides (`types.<T>.properties`) or set `discovery.jsonNaming` in a future version

## Known blind spots (the agent must cover them)
- Routes built from constants or string interpolation (`app.MapGet(Routes.Claims, ...)`) -> D03 fires, add via `addEndpoints`
- Handlers returning `IResult`/`IActionResult` with the payload built elsewhere -> needsReview
- Functions with `"get","post"` branching inside the body
- Types compiled into NuGet packages / other repos -> D05 (use TypeExtractor or externalTypes)
- Custom model binders, `[ModelBinder]`, polymorphic JSON (`[JsonDerivedType]`) -> describe in overrides
