# canonical-model.json (abridged)

```json
{
  "modelType": "canonical", "region": "EU", "version": "1.0.0", "status": "approved|draft",
  "baseline": {"region": "EU", "version": "1.0.0"} | null,
  "references": [{"source": "acord", "name": "ACORD", "version": "..."}],
  "reviewers": ["..."],
  "entities": [{
    "name": "Claim", "kind": "object|enum", "domain": "Claims", "description": "...",
    "approach": "reference-as-is|reference-extended|custom|baseline-reused|baseline-extended",
    "reference": {"source": "acord", "entity": "Claim", "subjectArea": "Claim"},
    "introducedIn": "EU", "status": "approved|baseline|baseline-extended",
    "regionalEntities": [{"entity": "CreateClaimRequest", "decision": "extend", "alignmentPercent": 80, "apps": ["EU/claims"]}],
    "sourceSchemas": ["EU/claims:ClaimDto", "EU/claims:CreateClaimRequest"],
    "attributes": [{"name": "claimNumber", "type": "string", "format": "", "refEntity": null, "isCollection": false,
                    "required": true, "description": "...", "extension": false, "introducedIn": "EU",
                    "reference": {"source": "acord", "entity": "Claim", "attribute": "claimNumber"},
                    "sources": ["EU/claims:ClaimDto/ClaimResponse.claimNumber"]}],
    "enumValues": [], "extensionValues": [], "valueMapping": [{"source": "Rejected", "canonical": "Rejected"}]
  }],
  "relations": [{"from": "Claim", "to": "Address", "via": "lossLocation", "type": "has-one", "cardinality": "0..1"}],
  "endpoints": [{"method": "GET", "path": "/claims/{claimId}", "operationId": "ViewClaim", "domain": "Claims",
                 "sources": [{"id": "EU/claims:GetClaim", "path": "/api/v1/claims/{claimId}"}], "contract": {...}}],
  "lineage": [{"appId": "EU/claims", "sourceSchemas": ["ClaimDto"], "sourceAttribute": "status", "regionalEntity": "Claim",
               "canonicalEntity": "Claim", "canonicalAttribute": "claimStatusCode",
               "referenceAttribute": "acord:Claim.claimStatusCode", "transformation": "rename status -> claimStatusCode", "note": "mapped"}],
  "pending": [], "rejected": [], "excludedEndpoints": [], "changes": {...}, "changesVsBaseline": {...}
}
```
