using Claims.Domain.Models;
using Microsoft.AspNetCore.Mvc;
namespace Claims.Api.Controllers;

[ApiController]
[Route("api/v1/claims/{claimId}/[controller]")]
[Authorize]
public class DocumentsController : ControllerBase
{
    /// <summary>List documents attached to a claim.</summary>
    [HttpGet]
    public ActionResult<IEnumerable<ClaimDocument>> List(Guid claimId) => Ok();

    /// <summary>Upload a document for a claim.</summary>
    [HttpPost]
    [ProducesResponseType(typeof(ClaimDocument), StatusCodes.Status201Created)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public async Task<IActionResult> Upload(Guid claimId, IFormFile file, [FromForm] string documentType) => Ok();

    [HttpDelete("{documentId}")]
    public IActionResult Delete(Guid claimId, Guid documentId) => NoContent();
}
