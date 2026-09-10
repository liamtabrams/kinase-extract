#!/usr/bin/env bash
#
# revalidate.sh -- re-run ONLY the validator + aggregate eval over papers that
# already have a cached extraction in data/extractions/. No ingest, no reader,
# so it uses NO Anthropic credits. Use this after changing validation/
# normalization logic to re-measure without paying to re-extract.
#
# Usage:
#   ./revalidate.sh                          # every cached extraction (live OmniPath)
#   ./revalidate.sh PMC6582307 PMC7694028    # just these
#   REFERENCE=fixture ./revalidate.sh        # offline reference instead of OmniPath
set -uo pipefail

REFERENCE="${REFERENCE:-omnipath}"

# Papers to validate: command-line args, else every cached extraction on disk.
if [ "$#" -gt 0 ]; then
  PAPERS=("$@")
else
  PAPERS=()
  for f in data/extractions/*.json; do
    [ -e "$f" ] || continue          # guard: glob may not match anything
    PAPERS+=("$(basename "$f" .json)")
  done
fi

if [ "${#PAPERS[@]}" -eq 0 ]; then
  echo "No cached extractions in data/extractions/. Run the reader first." >&2
  exit 1
fi

echo "reference=$REFERENCE  (no re-extraction -- reusing cached extractions)"
echo "papers  : ${PAPERS[*]}"
echo

for id in "${PAPERS[@]}"; do
  echo "=== $id ==="
  python -m pipeline.validator "$id" --reference "$REFERENCE" \
    || echo "  validator failed for $id."
  echo
done

echo "=== aggregate evaluation ==="
python -m pipeline.evaluate --all
