# Alignment validation codes

| Code | Severity | Meaning |
|---|---|---|
| AL01 | error | No reference entities loaded |
| AL02 | error | Empty scope, or an in-scope entity has no alignment row |
| AL03 | error | Ambiguous best match without override |
| AL04 | warning | Attribute type conflicts with the matched reference attribute |
| AL05 | error | Override references an unknown entity / reference |
| AL06 | error | Override without note / reason |
| AL07 | error | Regional input newer than alignment / missing |
| AL08 | warning | Same attribute typed differently across applications |
| AL09 | error | Sensitive data (credentials, e-mails, URLs, hosts/IPs, PII, client names) in outputs, `alignment-overrides.yaml` or `approvals.yaml` |
| AL10 | error | HTML / Excel / report missing or HTML without data |
| AL11 | warning | Approvals changed since review or referring to rows that no longer exist |
