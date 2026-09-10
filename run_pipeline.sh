#!/usr/bin/env bash
#
# run_pipeline.sh -- run the OFFLINE pipeline over a batch of papers, then
# evaluate the whole batch. For each paper: ingest -> reader -> validator.
# The interactive review UI is a separate step: `streamlit run app.py`.
#
# Usage:
#   ./run_pipeline.sh                         # default paper list (claude + omnipath)
#   ./run_pipeline.sh PMC6582307 PMC7694028   # your own list of PMCIDs
#   BACKEND=mock REFERENCE=fixture ./run_pipeline.sh PMC_SAMPLE   # offline demo, no cost
#
# We intentionally do NOT use `set -e`: a single non-open-access paper should
# be skipped, not abort the whole batch. We handle failures per step instead.
set -uo pipefail

BACKEND="${BACKEND:-claude}"        # override: BACKEND=mock ./run_pipeline.sh
REFERENCE="${REFERENCE:-omnipath}"  # override: REFERENCE=fixture ./run_pipeline.sh

# Papers to process: use command-line args if given, else this default set.
if [ "$#" -gt 0 ]; then
  PAPERS=("$@")
else
  PAPERS=(PMC6582307 PMC7694028 PMC9390817 PMC10779188 PMC9456575)
fi

echo "backend=$BACKEND  reference=$REFERENCE"
echo "papers : ${PAPERS[*]}"
echo

for id in "${PAPERS[@]}"; do
  echo "=== $id ==="
  if ! python -m pipeline.ingest "$id"; then
    echo "  ingest failed for $id (maybe not open-access) -- skipping."
    echo; continue
  fi
  if ! python -m pipeline.reader "$id" --backend "$BACKEND"; then
    echo "  reader failed for $id -- skipping validation."
    echo; continue
  fi
  python -m pipeline.validator "$id" --reference "$REFERENCE" \
    || echo "  validator failed for $id."
  echo
done

echo "=== aggregate evaluation ==="
python -m pipeline.evaluate --all
