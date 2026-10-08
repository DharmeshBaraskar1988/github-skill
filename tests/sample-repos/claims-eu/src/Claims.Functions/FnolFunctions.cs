using System.Net;
using Claims.Domain.Models;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Http;
using Microsoft.Azure.WebJobs.Extensions.OpenApi.Core.Attributes;
namespace Claims.Functions;

public class FnolFunctions
{
    /// <summary>Receive a first notice of loss from a broker portal.</summary>
    [Function("SubmitFnol")]
    [OpenApiOperation(operationId: "SubmitFnol", tags: new[] { "FNOL" }, Summary = "Submit first notice of loss")]
    [OpenApiRequestBody(contentType: "application/json", bodyType: typeof(FnolSubmission), Required = true)]
    [OpenApiResponseWithBody(statusCode: HttpStatusCode.Accepted, contentType: "application/json", bodyType: typeof(FnolReceipt))]
    public async Task<HttpResponseData> Submit(
        [HttpTrigger(AuthorizationLevel.Function, "post", Route = "fnol")] HttpRequestData req)
    {
        var body = await req.ReadFromJsonAsync<FnolSubmission>();
        var res = req.CreateResponse(HttpStatusCode.Accepted);
        await res.WriteAsJsonAsync(new FnolReceipt());
        return res;
    }

    [Function("GetFnolStatus")]
    public async Task<HttpResponseData> GetStatus(
        [HttpTrigger(AuthorizationLevel.Function, "get", Route = "fnol/{reference}")] HttpRequestData req, string reference)
    {
        var status = await Lookup(reference);
        var res = req.CreateResponse(HttpStatusCode.OK);
        await res.WriteAsJsonAsync(status);
        return res;
    }

    [Function("ProcessFnolQueue")]
    public Task Process([ServiceBusTrigger("fnol-inbound", Connection = "ServiceBus")] FnolSubmission msg) => Task.CompletedTask;
}

/// <summary>FNOL payload sent by brokers.</summary>
public class FnolSubmission
{
    public string BrokerCode { get; set; } = "";
    public string PolicyNumber { get; set; } = "";
    public DateTime LossDateTime { get; set; }
    public string Description { get; set; } = "";
    public Address? Location { get; set; }
    public PolicyHolderInfo? Reporter { get; set; }
}

public class FnolReceipt
{
    public string Reference { get; set; } = "";
    public DateTimeOffset ReceivedAt { get; set; }
}

/// <summary>Reporter of the loss.</summary>
public class PolicyHolderInfo
{
    public string FirstName { get; set; } = "";
    public string LastName { get; set; } = "";
    public string? Email { get; set; }
    public Address? Address { get; set; }
}
