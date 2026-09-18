#!/bin/bash
cd "$(dirname "$0")/../.."
export ACX_MODEL=claude-sonnet-5
/private/tmp/acx-venv/bin/python experiment/hangman/run_hangman.py --conditions bare,tools,tools-note --reveal 0,1 --games 12 --concurrency 4
/private/tmp/acx-venv/bin/python experiment/hangman/run_couplet.py --trials 12 --concurrency 4
echo "EXP2 DONE $(date -u)"
