using Claims.Domain.Models;
using Microsoft.AspNetCore.Http.HttpResults;
namespace Claims.Api.Endpoints;

public static class ClaimEndpoints
{
    public static void MapClaimEndpoints(this IEndpointRouteBuilder app)
    {
        var claims = app.MapGroup("/api/v1/claims").WithTags("Claims").RequireAuthorization();

        claims.MapGet("/", ListClaims).WithName("ListClaims");
        claims.MapGet("/{claimId:guid}", GetClaim).WithName("GetClaim");
        claims.MapPost("/", CreateClaim)
              .WithName("CreateClaim")
              .Produces<ClaimResponse>(StatusCodes.Status201Created)
              .ProducesValidationProblem();
        claims.MapPut("/{claimId:guid}", async (Guid claimId, [FromBody] UpdateClaimRequest request, IClaimService svc, CancellationToken ct) =>
        {
            var updated = await svc.UpdateAsync(claimId, request, ct);
            return TypedResults.Ok(updated);
        }).WithName("UpdateClaim").Produces<ClaimDto>(200);
        claims.MapPost("/{claimId:guid}/approve", ApproveClaim).WithName("ApproveClaim");
        claims.MapDelete("/{claimId:guid}", (Guid claimId, IClaimService svc) => svc.DeleteAsync(claimId)).WithName("DeleteClaim").Produces(204);

        var claimants = claims.MapGroup("/{claimId:guid}/claimants");
        claimants.MapGet("/", (Guid claimId, IClaimService svc) => svc.GetClaimants(claimId)).Produces<List<ClaimantDto>>();
    }

    /// <summary>Search claims with paging and optional status filter.</summary>
    private static async Task<Ok<PagedResult<ClaimDto>>> ListClaims(
        [FromQuery] ClaimStatus? status, int page, int pageSize, IClaimService svc) =>
        TypedResults.Ok(await svc.ListAsync(status, page, pageSize));

    /// <summary>Get a single claim by id.</summary>
    private static async Task<Results<Ok<ClaimResponse>, NotFound>> GetClaim(Guid claimId, IClaimService svc)
    {
        var c = await svc.GetAsync(claimId);
        return c is null ? TypedResults.NotFound() : TypedResults.Ok(c);
    }

    /// <summary>Register a first notice of loss.</summary>
    private static async Task<IResult> CreateClaim(CreateClaimRequest request, IClaimService svc)
    {
        var created = await svc.CreateAsync(request);
        return Results.Created($"/api/v1/claims/{created.ClaimId}", created);
    }

    private static async Task<IResult> ApproveClaim(Guid claimId, ApprovalRequest body, IClaimService svc)
    {
        await svc.ApproveAsync(claimId, body);
        return Results.NoContent();
    }
}
