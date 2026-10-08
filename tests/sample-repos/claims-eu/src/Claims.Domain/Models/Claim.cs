using System.ComponentModel.DataAnnotations;
using System.Text.Json.Serialization;
namespace Claims.Domain.Models;

/// <summary>Lifecycle status of an insurance claim.</summary>
public enum ClaimStatus { Draft, Submitted, UnderReview, Approved, Rejected, Closed }

/// <summary>Monetary amount with ISO currency.</summary>
public record Money(decimal Amount, [property: MaxLength(3)] string Currency);

/// <summary>Postal address.</summary>
public class Address
{
    public string Line1 { get; set; } = "";
    public string? Line2 { get; set; }
    public string City { get; set; } = "";
    public string PostCode { get; set; } = "";
    /// <summary>ISO 3166 alpha-2 country code.</summary>
    [MaxLength(2)]
    public string Country { get; set; } = "";
}

/// <summary>Base for auditable resources.</summary>
public abstract class AuditableDto
{
    public DateTimeOffset CreatedAt { get; set; }
    public string? CreatedBy { get; set; }
}

/// <summary>Claim summary used in lists.</summary>
public class ClaimDto : AuditableDto
{
    public Guid ClaimId { get; set; }
    /// <summary>Business claim number, e.g. CLM-2026-000123.</summary>
    [Required]
    public string ClaimNumber { get; set; } = "";
    public string PolicyNumber { get; set; } = "";
    public ClaimStatus Status { get; set; }
    public Money? ReserveAmount { get; set; }
    public DateOnly LossDate { get; set; }
}

/// <summary>Claim details returned by the API.</summary>
public class ClaimResponse : AuditableDto
{
    public Guid ClaimId { get; set; }
    [Required]
    public string ClaimNumber { get; set; } = "";
    public string PolicyNumber { get; set; } = "";
    public ClaimStatus Status { get; set; }
    public Money? ReserveAmount { get; set; }
    public DateOnly LossDate { get; set; }
}

public class CreateClaimRequest
{
    [Required]
    public string PolicyNumber { get; set; } = "";
    [Required]
    public DateOnly LossDate { get; set; }
    [MaxLength(2000)]
    public string? Description { get; set; }
    public Address? LossLocation { get; set; }
    public List<ClaimantDto> Claimants { get; set; } = new();
    [JsonIgnore]
    public string InternalTrace { get; set; } = "";
}

public class UpdateClaimRequest
{
    public string? Description { get; set; }
    public Address? LossLocation { get; set; }
    public ClaimStatus? Status { get; set; }
}

public record ApprovalRequest(string ApprovedBy, Money SettlementAmount, string? Comment = null);

/// <summary>Person or organisation claiming under the policy.</summary>
public class ClaimantDto
{
    public Guid ClaimantId { get; set; }
    public string FirstName { get; set; } = "";
    public string LastName { get; set; } = "";
    [EmailAddress]
    public string? Email { get; set; }
    public Address? Address { get; set; }
    public string? PolicyHolderId { get; set; }
}

public class ClaimDocument
{
    public Guid DocumentId { get; set; }
    public Guid ClaimId { get; set; }
    public string FileName { get; set; } = "";
    public string DocumentType { get; set; } = "";
    public long SizeBytes { get; set; }
}

public class PagedResult<T>
{
    public List<T> Items { get; set; } = new();
    public int Page { get; set; }
    public int PageSize { get; set; }
    public int TotalCount { get; set; }
}
