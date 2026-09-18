#!/bin/bash
# Protocol v2 data collection (reduced for budget): fresh arm x1 rep + strong arm x1 rep = 30 runs, after the window reset.
cd "$(dirname "$0")/.."
export ASDF_PYTHON_VERSION=3.12.12
echo "waiting for reset at $(date -u -r 1789702800 2>/dev/null || echo 03:40Z)"
while [ "$(date -u +%s)" -lt 1789702860 ]; do sleep 30; done
echo "v2 start $(date -u)"
/private/tmp/acx-venv/bin/python experiment/run_experiment.py --tasks all --arms fresh-tempt,fresh-evidence --reps 1 --concurrency 12
/private/tmp/acx-venv/bin/python experiment/run_experiment.py --tasks all --arms ctx-strong --reps 1 --concurrency 10
echo "v2 done $(date -u)"
