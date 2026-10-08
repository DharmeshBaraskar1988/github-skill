#!/usr/bin/env bash
# Regression run of the whole kit on the sample repositories. Usage: bash tests/run_e2e.sh
# Re-uses the agent-written overrides/decisions kept in examples/ so the run is deterministic.
set -euo pipefail
cd "$(dirname "$0")/.."
D=.github/skills/api-discovery/scripts; A=.github/skills/api-analysis/scripts; R=.github/skills/regional-view/scripts
O=tests/output/api-catalog; E=examples/api-catalog
rm -rf tests/output && mkdir -p $O && cp -r $E/external $E/style-examples $O/
python3 $A/load_domains.py --xlsx api-catalog/domains.xlsx --out $O/domains.json >/dev/null
for app in claims policy; do
  c=tests/sample-repos/$app-eu/api-catalog.config.yaml
  python3 $D/scan_dotnet.py --config $c >/dev/null
  [ -f $E/discovery/EU/$app/overrides.yaml ] && cp $E/discovery/EU/$app/overrides.yaml $O/discovery/EU/$app/
  python3 $D/build_openapi.py --config $c >/dev/null
  python3 $D/validate_discovery.py --dir $O/discovery/EU/$app >/dev/null || { echo "FAILED: discovery EU/$app pass"; exit 1; }; echo "discovery EU/$app pass"
  mkdir -p $O/analysis/EU/$app
  [ -f $E/analysis/EU/$app/decisions.yaml ] && cp $E/analysis/EU/$app/decisions.yaml $O/analysis/EU/$app/
  python3 $A/analyze.py --spec $O/discovery/EU/$app/openapi.yaml --domains $O/domains.json --out $O/analysis/EU/$app >/dev/null
  python3 $A/validate_analysis.py --dir $O/analysis/EU/$app --spec $O/discovery/EU/$app/openapi.yaml --domains $O/domains.json >/dev/null || { echo "FAILED: analysis EU/$app pass"; exit 1; }; echo "analysis EU/$app pass"
done
python3 $R/build_regional_view.py --input $O --domains $O/domains.json --out $O/regional-view >/dev/null
python3 $R/validate_regional_view.py --out $O/regional-view >/dev/null || { echo "FAILED: regional view pass"; exit 1; }; echo "regional view pass"

# ---- ACORD alignment + review + canonical (SAMPLE reference - not ACORD) ----
AL=.github/skills/acord-alignment/scripts; CA=.github/skills/canonical-model/scripts
mkdir -p $O/reference $O/regions
cp $E/reference/reference-sample.xlsx $O/reference/ && cp $E/regions/*.yaml $O/regions/
python3 $AL/load_reference.py --source $O/reference/reference-sample.xlsx --name "SAMPLE (not ACORD)" --version 0.1 --out $O/reference/acord.reference.json >/dev/null
python3 $AL/align.py --config $O/regions/EU.yaml >/dev/null
python3 $AL/validate_alignment.py --dir $O/alignment/EU >/dev/null || { echo "FAILED: alignment EU pass"; exit 1; }; echo "alignment EU pass"
mkdir -p $O/alignment/EU/claims && cp $E/alignment/EU/claims/alignment-overrides.yaml $O/alignment/EU/claims/
python3 $AL/align.py --config $O/regions/EU.yaml --apps claims >/dev/null
python3 $AL/validate_alignment.py --dir $O/alignment/EU/claims >/dev/null || { echo "FAILED: alignment EU/claims slice pass"; exit 1; }; echo "alignment EU/claims slice pass"
python3 tests/simulate_review.py $O/alignment/EU >/dev/null          # plays the human reviewers
python3 $AL/import_review.py --dir $O/alignment/EU --xlsx $O/alignment/EU/reviewed-claims.xlsx --json $O/alignment/EU/review-decisions.json >/dev/null
python3 $AL/align.py --config $O/regions/EU.yaml >/dev/null
python3 $CA/build_canonical.py --config $O/regions/EU.yaml --release >/dev/null
python3 $CA/validate_canonical.py --config $O/regions/EU.yaml >/dev/null || { echo "FAILED: canonical EU pass (released 1.0.0)"; exit 1; }; echo "canonical EU pass (released 1.0.0)"
python3 $AL/align.py --config $O/regions/UK.yaml >/dev/null
python3 $AL/validate_alignment.py --dir $O/alignment/UK >/dev/null || { echo "FAILED: alignment UK (baseline EU) pass"; exit 1; }; echo "alignment UK (baseline EU) pass"
python3 tests/simulate_review.py $O/alignment/UK approve-all >/dev/null
python3 $AL/import_review.py --dir $O/alignment/UK --json $O/alignment/UK/review-decisions.json >/dev/null
python3 $AL/align.py --config $O/regions/UK.yaml >/dev/null
python3 $CA/build_canonical.py --config $O/regions/UK.yaml --release >/dev/null
python3 $CA/validate_canonical.py --config $O/regions/UK.yaml >/dev/null || { echo "FAILED: canonical UK pass"; exit 1; }; echo "canonical UK pass"
python3 $CA/merge_global.py --catalog $O >/dev/null
python3 $CA/validate_global.py --catalog $O >/dev/null || { echo "FAILED: global canonical"; exit 1; }; echo "global canonical (EU 1.0.0 + UK 1.0.0) pass"
python3 $R/build_regional_view.py --input $O --domains $O/domains.json --out $O/regional-view >/dev/null   # refresh spec viewer incl. canonical
python3 $R/validate_regional_view.py --out $O/regional-view >/dev/null || { echo "FAILED: regional view refresh"; exit 1; }; echo "regional view + spec viewer refreshed"
