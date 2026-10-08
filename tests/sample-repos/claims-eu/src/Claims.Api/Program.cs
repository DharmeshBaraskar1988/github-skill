using Claims.Api.Endpoints;
var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();
app.MapClaimEndpoints();
app.MapGet("/health", () => Results.Ok("healthy")).AllowAnonymous().ExcludeFromDescription();
app.Run();
