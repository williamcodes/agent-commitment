#!/bin/bash
cd "$(dirname "$0")/../.."
export ACX_MODEL=claude-sonnet-5
/private/tmp/acx-venv/bin/python experiment/hangman/run_hangman.py --conditions tools-careful,tools-auditable --reveal 0,1 --games 12 --concurrency 4
echo "CONSULT DONE $(date -u)"
