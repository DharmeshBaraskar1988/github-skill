Put the export of your **licensed** ACORD model here as `acord-export.xlsx` (or `.xsd` / `.json`), then:

    python .github/skills/acord-alignment/scripts/load_reference.py --source api-catalog/reference/acord-export.xlsx \
           --name ACORD --version "<release>" --out api-catalog/reference/acord.reference.json

Format: `.github/skills/acord-alignment/references/reference-model-format.md`. The kit ships no ACORD content;
`examples/api-catalog/reference/reference-sample.xlsx` is an invented sample for testing only.
`synonyms.yaml` holds your organisation's vocabulary for matching.
