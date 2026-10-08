# Review workflow (humans)

1. Open `acord-alignment.html` (works offline, any browser) or `acord-alignment.xlsx`.
2. Per entity choose:
   | Decision | Meaning in the canonical model |
   |---|---|
   | approve | take the Recommendation as shown |
   | use-as-is | canonical entity = reference entity; our attributes use reference names/types; our extra attributes are dropped |
   | extend | reference entity + our extra attributes as `x-extension` |
   | custom | new canonical entity from our attributes (no reference) |
   | reject | not canonical (comment required). Endpoints using it are left out of the canonical API |
   | pending | undecided |
   Optional: another candidate as reference, a different canonical name.
3. Attributes (optional): accept (default) / rename (+ new name) / exclude.
4. Endpoints (optional): include (default) / exclude, canonical path, canonical operationId.
   With `canonical.endpointApproval: explicit` every endpoint needs an explicit include.
5. Put your name in Reviewer and export (HTML) / save (Excel). The alignment owner runs `import_review.py`.

Rules enforced by `import_review.py`: reviewer required, reject needs a comment, unknown rows are refused, empty cells
change nothing, `pending` clears an earlier decision. Several reviewers can work in parallel on different domains; the
import reports conflicting decisions for the same row (last file wins).
