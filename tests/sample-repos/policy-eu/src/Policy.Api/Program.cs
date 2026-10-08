var app = WebApplication.CreateBuilder(args).Build();
var policies = app.MapGroup("/api/policies").WithTags("Policies");
policies.MapGet("/", (string? holderName, IPolicyService s) => s.Search(holderName)).Produces<List<PolicySummary>>();
policies.MapGet("/{policyNumber}", (string policyNumber, IPolicyService s) => s.Get(policyNumber)).Produces<PolicyDetails>().Produces(404);
policies.MapPost("/", ([FromBody] IssuePolicyRequest req, IPolicyService s) => s.Issue(req)).Produces<PolicyDetails>(201);
policies.MapPost("/{policyNumber}/renew", (string policyNumber, IPolicyService s) => s.Renew(policyNumber)).Produces<PolicyDetails>();
app.MapGet("/api/policyholders/{id:guid}", (Guid id, IPolicyService s) => s.Holder(id)).Produces<PolicyHolder>();
app.Run();

/// <summary>Lightweight policy row for search results.</summary>
public record PolicySummary(string PolicyNumber, string ProductCode, PolicyStatus Status, string HolderName);
/// <summary>Full policy.</summary>
public class PolicyDetails
{
    public string PolicyNumber { get; set; } = "";
    public string ProductCode { get; set; } = "";
    public PolicyStatus Status { get; set; }
    public DateOnly InceptionDate { get; set; }
    public DateOnly ExpiryDate { get; set; }
    public Money Premium { get; set; } = new(0, "EUR");
    public PolicyHolder Holder { get; set; } = new();
    public List<Coverage> Coverages { get; set; } = new();
}
public class Coverage { public string Code { get; set; } = ""; public string Name { get; set; } = ""; public Money Limit { get; set; } = new(0,"EUR"); public Money? Deductible { get; set; } }
/// <summary>Insured person or company.</summary>
public class PolicyHolder
{
    public Guid PolicyHolderId { get; set; }
    public string FirstName { get; set; } = "";
    public string LastName { get; set; } = "";
    public string? Email { get; set; }
    public Address? Address { get; set; }
}
public class Address { public string Line1 { get; set; } = ""; public string? Line2 { get; set; } public string City { get; set; } = ""; public string PostCode { get; set; } = ""; public string Country { get; set; } = ""; }
public record Money(decimal Amount, string Currency);
public enum PolicyStatus { Quoted, Active, Lapsed, Cancelled, Expired }
public class IssuePolicyRequest { public string QuoteReference { get; set; } = ""; public DateOnly InceptionDate { get; set; } public PolicyHolder Holder { get; set; } = new(); }
