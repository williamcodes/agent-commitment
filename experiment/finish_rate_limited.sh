#!/bin/bash
# Re-run the 13 rate-limited runs once the usage window has reset (no overage), then rebuild results.
cd "$(dirname "$0")/.."
RUNS=$(ls runs/rate_limited | paste -sd, -)
echo "waiting for reset at $(date -u -r 1789702800)"
while [ "$(date -u +%s)" -lt 1789702860 ]; do sleep 60; done
echo "starting re-runs at $(date -u): $RUNS"
/private/tmp/acx-venv/bin/python experiment/run_experiment.py --runs "$RUNS" --concurrency 4
echo "re-runs finished at $(date -u)"
