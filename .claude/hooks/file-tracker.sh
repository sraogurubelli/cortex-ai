#!/bin/bash
# PostToolUse hook that suggests skills based on edited files
# Runs after Edit, MultiEdit, or Write tools complete

# Read tool information from stdin
tool_info=$(cat)

# Extract relevant data
tool_name=$(echo "$tool_info" | jq -r '.tool_name // empty')
file_path=$(echo "$tool_info" | jq -r '.tool_input.file_path // empty')

# Skip if not an edit tool or no file path
if [[ ! "$tool_name" =~ ^(Edit|MultiEdit|Write)$ ]] || [[ -z "$file_path" ]]; then
    exit 0
fi

# Skip documentation files
if [[ "$file_path" =~ \.(md|markdown|txt)$ ]]; then
    exit 0
fi

# Detect which cortex-ai module was edited and suggest relevant skill
suggest_skill() {
    local file="$1"

    case "$file" in
        */cortex/orchestration/*)
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo "📝 Edited: Orchestration module"
            echo "💡 Skill available: /orchestration-dev"
            echo "   (Agent development patterns)"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ;;
        */cortex/rag/*)
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo "📝 Edited: RAG module"
            echo "💡 Skill available: /rag-query"
            echo "   (RAG optimization and debugging)"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ;;
        */cortex/api/*)
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo "📝 Edited: API module"
            echo "💡 Skill available: /api-endpoint"
            echo "   (FastAPI endpoint patterns)"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ;;
        */cortex/memory/*)
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo "📝 Edited: Memory module"
            echo "💡 See: .claude/rules/memory.md"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ;;
        */tests/orchestration/*)
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo "📝 Edited: Orchestration tests"
            echo "💡 Skill available: /orchestration-dev"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ;;
        */tests/*)
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo "📝 Edited: Tests"
            echo "💡 See: .claude/rules/testing.md"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ;;
    esac
}

# Suggest skill based on file path
suggest_skill "$file_path"

exit 0
