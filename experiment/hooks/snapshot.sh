#!/bin/bash
# PostToolUse hook for the agent under test. Appends the hook payload (tool name, input, response,
# timestamp) to $ACX_RUN_DIR/hooks.jsonl and commits a snapshot of the working tree into a shadow
# bare git repository at $ACX_RUN_DIR/shadow.git, so every file change can be attributed to the
# tool call that produced it. Never fails the tool call.
RUN_DIR="$ACX_RUN_DIR"; WORK="$ACX_WORK_DIR"
[ -n "$RUN_DIR" ] && [ -n "$WORK" ] || exit 0
payload=$(cat)
ts=$(/private/tmp/acx-venv/bin/python -c 'import datetime;print(datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]+"Z")')
printf '%s\n' "$(printf '%s' "$payload" | jq -c --arg ts "$ts" '. + {hook_ts: $ts}')" >> "$RUN_DIR/hooks.jsonl"
tool=$(printf '%s' "$payload" | jq -r '.tool_name // "unknown"')
tid=$(printf '%s' "$payload" | jq -r '.tool_use_id // ""')
SHADOW="$RUN_DIR/shadow.git"
if [ ! -d "$SHADOW" ]; then
  env -u GIT_DIR -u GIT_WORK_TREE git init -q --bare "$SHADOW" >/dev/null 2>&1
  git --git-dir="$SHADOW" config user.email acx@example.invalid
  git --git-dir="$SHADOW" config user.name acx-snapshot
fi
export GIT_DIR="$SHADOW" GIT_WORK_TREE="$WORK"
git add -A >/dev/null 2>&1
if ! git diff --cached --quiet 2>/dev/null; then
  git commit -q -m "post:$tool $ts $tid" >/dev/null 2>&1
fi
exit 0
