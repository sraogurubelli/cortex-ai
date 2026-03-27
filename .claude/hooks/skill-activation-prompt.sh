#!/bin/bash
# Enable logging to debug hook execution
LOGFILE="/tmp/claude-hook-debug-$(date +%s).log"
exec 2>>"$LOGFILE"

echo "[$(date)] Hook triggered" >&2
echo "CLAUDE_PROJECT_DIR=$CLAUDE_PROJECT_DIR" >&2
echo "PWD=$PWD" >&2

# Don't exit on error - log instead
set +e

# Read stdin to a temp file so we can log it and pass it through
STDIN_FILE="/tmp/claude-hook-stdin-$$.txt"
cat > "$STDIN_FILE"
echo "STDIN content:" >&2
cat "$STDIN_FILE" >&2
echo "---" >&2

cd "$CLAUDE_PROJECT_DIR/.claude/hooks" 2>&1 || {
    echo "ERROR: Failed to cd to $CLAUDE_PROJECT_DIR/.claude/hooks" >&2
    rm -f "$STDIN_FILE"
    exit 1
}

echo "Successfully changed to: $(pwd)" >&2
cat "$STDIN_FILE" | npx tsx skill-activation-prompt-langfuse.ts 2>&1 | grep -v "npm warn"
EXIT_CODE=$?
echo "Exit code: $EXIT_CODE" >&2

rm -f "$STDIN_FILE"
exit $EXIT_CODE
