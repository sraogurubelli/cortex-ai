#!/bin/bash
# Manual skill activation check
# Usage: ./manual-skill-check.sh "your prompt here"

PROMPT="${1:-test prompt}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "MANUAL SKILL CHECK"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Prompt: $PROMPT"
echo ""

# Create JSON input
INPUT=$(cat <<EOF
{
  "session_id": "manual-test",
  "transcript_path": "/tmp/test.jsonl",
  "cwd": "$CLAUDE_PROJECT_DIR",
  "permission_mode": "auto",
  "prompt": "$PROMPT"
}
EOF
)

# Run hook
export CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$(dirname "$0")"
echo "$INPUT" | npx tsx skill-activation-prompt-langfuse.ts 2>&1 | grep -v "npm warn" || exit 0
