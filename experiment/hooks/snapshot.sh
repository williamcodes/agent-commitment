#!/bin/bash
# PostToolUse hook for the agent under test (v2: paths passed as arguments, no ACX_* environment variables). Appends the hook payload (tool name, input, response,
# timestamp) to $ACX_RUN_DIR/hooks.jsonl and commits a snapshot of the working tree into a shadow
# bare git repository at $ACX_RUN_DIR/shadow.git, so every file change can be attributed to the
# tool call that produced it. Never fails the tool call.
RUN_DIR="$1"; WORK="$2"
[ -n "$RUN_DIR" ] && [ -n "$WORK" ] || exit 0
payload=$(cat)
ts=$(python3 -c 'import datetime;print(datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]+"Z")' 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)
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
