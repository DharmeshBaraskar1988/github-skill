# Example run (sample data)

Produced by `bash tests/run_e2e.sh` on the sample repositories in `tests/sample-repos/`.

- `reference/reference-sample.xlsx` is an **invented generic insurance model, NOT ACORD**. Alignment percentages here
  only demonstrate the mechanics.
- Review decisions in `alignment/*/approvals.yaml` were made by a **test script playing the reviewers**
  (`tests/simulate_review.py`): "Asha (Claims architect)" via Excel, "Marco (Policy architect)" and
  "Priya (UK architect)" via the HTML export. In real use only people make these decisions.

Open in a browser:
- `regional-view/regional-view.html` – regional catalogue
- `alignment/EU/acord-alignment.html` – EU alignment review page (also `alignment/EU/claims/` for the claims slice)
- `alignment/UK/acord-alignment.html` – UK aligned against the EU baseline + reference
- `canonical/EU/canonical-viewer.html` – EU canonical OpenAPI + canonical model, YAML ⇄ JSON (released as 1.0.0)
- `regional-view/spec-viewer.html` – every spec in the catalogue as YAML / JSON
- `canonical/UK/…` – UK canonical = EU baseline + Quote
- `canonical/GLOBAL/global-canonical.html` – global canonical (EU 1.0.0 + UK 1.0.0) with region / application / API filters and the filtered spec as YAML or JSON
- `style-examples/_global/house-style-example.yaml` – invented house-style example used by discovery (conventions only)
