# Skill Activation Guide

**Practical guide for using skills in cortex-ai development**

## What Works (Use These!)

| Method | Status | When to Use |
|--------|--------|-------------|
| **Path-based activation** | ✅ Works perfectly | Editing files (automatic) |
| **PostToolUse hooks** | ✅ Works perfectly | After editing (automatic feedback) |
| **Manual skill check** | ✅ Works perfectly | Planning work (before starting) |
| **Direct invocation** | ✅ Works perfectly | Ask Claude to use a skill |
| **UserPromptSubmit** | ❌ Doesn't work | ~~Skip this~~ |

## Quick Start (3 Ways to Use Skills)

### Method 1: Just Edit Files (Automatic)

**Best for:** Normal development workflow

```bash
# Edit any file in cortex/orchestration/
vim cortex/orchestration/agent.py

# Skills and rules auto-load based on path
# ✅ orchestration-dev skill activates
# ✅ orchestration.md rules load
# ✅ PostToolUse hook confirms after save
```

**You'll see:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 Edited: Orchestration module
💡 Skill available: /orchestration-dev
   (Agent development patterns)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Method 2: Check Before Starting (Manual)

**Best for:** Planning complex work

```bash
./check-skill "create a data analysis agent with RAG"
```

**Output:**
```
🎯 CORTEX-AI SKILL ACTIVATION
📚 RECOMMENDED SKILLS:
  → /orchestration-dev (Agent development patterns)
  → /rag-query (RAG optimization)
```

### Method 3: Ask Claude Directly

**Best for:** Mid-conversation guidance

```
Use the orchestration-dev skill to help me create an agent
```

Or:
```
Follow the agent development patterns from orchestration-dev
```

## How Auto-Activation Works

### Path-Based Activation (Primary Method)

Skills have a `paths:` field in their SKILL.md frontmatter:

```yaml
---
name: orchestration-dev
paths:
  - "cortex/orchestration/**/*.py"
  - "tests/orchestration/**/*.py"
---
```

**When you edit matching files:** Skill automatically loads

### PostToolUse Hook (Confirmation)

After editing files, the hook shows what activated:

**File:** `.claude/settings.json`
```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Edit|MultiEdit|Write",
      "hooks": [{
        "command": "/path/to/file-tracker.sh"
      }]
    }]
  }
}
```

**Status:** ✅ Working (implemented in Option B)

## Skill Trigger Patterns

### orchestration-dev

**Triggers on:**
- Keywords: agent, tool, orchestration, async/await, thread_id
- Patterns: `(create|add).*?agent`, `(how to).*?orchestration`

**Example prompts:**
- "create a new agent"
- "add a tool to my agent"
- "how do I use thread_id"

### rag-query

**Triggers on:**
- Keywords: RAG, vector search, embeddings, Qdrant, GraphRAG
- Patterns: `(optimize|improve).*?RAG`, `(chunk|embed).*?document`

**Example prompts:**
- "optimize my RAG search"
- "how do I chunk documents"
- "improve vector search performance"

### api-endpoint

**Triggers on:**
- Keywords: API, endpoint, FastAPI, route, SSE, streaming
- Patterns: `(create|add).*?(API|endpoint)`, `(validate|authenticate).*?request`

**Example prompts:**
- "create a new API endpoint"
- "add authentication to route"
- "how do I stream responses"

## Customizing Triggers

Edit `.claude/skills/skill-rules.json`:

```json
{
  "skills": {
    "orchestration-dev": {
      "promptTriggers": {
        "keywords": [
          "agent",
          "orchestration",
          "YOUR_KEYWORD_HERE"
        ],
        "intentPatterns": [
          "(create|add).*?agent",
          "YOUR_PATTERN_HERE"
        ]
      }
    }
  }
}
```

Test your changes:
```bash
./manual-skill-check.sh "prompt with YOUR_KEYWORD_HERE"
```

## File Structure

```
.claude/
├── settings.json                    # Hook configuration
├── skills/
│   ├── skill-rules.json            # Trigger patterns
│   ├── orchestration-dev/SKILL.md  # Agent development
│   ├── rag-query/SKILL.md          # RAG optimization
│   └── api-endpoint/SKILL.md       # API development
└── hooks/
    ├── skill-activation-prompt.sh           # Auto hook (configured)
    ├── skill-activation-prompt-langfuse.ts  # Main logic
    ├── manual-skill-check.sh                # Manual trigger ✅
    └── test-input.json                      # Test data
```

## Testing

### Test Hook Logic

```bash
cd .claude/hooks
npx tsx skill-activation-prompt-langfuse.ts < test-input.json
```

### Test Different Prompts

```bash
# Agent creation
./manual-skill-check.sh "create a new data analysis agent"

# RAG optimization
./manual-skill-check.sh "optimize my vector search"

# API endpoint
./manual-skill-check.sh "add a new FastAPI route"
```

### Test with Real Prompt

```bash
./manual-skill-check.sh "$(cat <<'EOF'
I want to create a new agent that analyzes customer feedback
and generates insights using sentiment analysis
EOF
)"
```

## Real-World Workflows

### Workflow 1: Creating a New Agent

```bash
# Step 1: Plan (manual check)
./check-skill "create a data analysis agent"
# Output: /orchestration-dev

# Step 2: Edit files
vim cortex/orchestration/agents/data_analysis.py
# → orchestration-dev auto-loads
# → PostToolUse hook confirms

# Step 3: Ask Claude for help (already has context)
# Claude uses loaded skill automatically
```

### Workflow 2: Optimizing RAG Search

```bash
# Step 1: Edit RAG code
vim cortex/rag/retriever.py
# → rag-query skill auto-loads
# → rag.md rules load

# Step 2: Ask Claude
"Help me optimize this search query"
# Claude uses rag-query patterns automatically
```

### Workflow 3: Adding API Endpoint

```bash
# Path-based activation handles everything
vim cortex/api/routes/new_endpoint.py
# → api-endpoint skill loads
# → api.md rules load
# → PostToolUse confirms

# Just start coding, Claude has full context
```

## Troubleshooting

### PostToolUse hook not showing

**Check jq is installed:**
```bash
jq --version
# If not: brew install jq
```

**Test manually:**
```bash
echo '{"tool_name":"Edit","tool_input":{"file_path":"cortex/orchestration/agent.py"}}' | ./.claude/hooks/file-tracker.sh
```

### Manual skill check fails

**Install dependencies:**
```bash
cd .claude/hooks
npm install
chmod +x manual-skill-check.sh
```

**Test:**
```bash
./manual-skill-check.sh "create agent"
```

### Skills not loading when editing files

**Check SKILL.md frontmatter:**
```yaml
---
paths:
  - "cortex/orchestration/**/*.py"  # ✅ Good
  - "**.py"                          # ❌ Too broad
---
```

**Verify path matching:** Skill paths must match actual file paths

### Want to add a custom skill

1. **Create skill file:**
   ```bash
   mkdir -p .claude/skills/my-skill
   vim .claude/skills/my-skill/SKILL.md
   ```

2. **Add frontmatter:**
   ```yaml
   ---
   name: my-skill
   description: What this skill does
   paths:
     - "cortex/my_module/**/*.py"
   ---
   ```

3. **Test path matching:**
   ```bash
   # Edit a file in your path
   vim cortex/my_module/test.py
   # Skill should auto-load
   ```

## What We Learned About Hooks

### UserPromptSubmit Doesn't Work

**Known Claude Code bugs:**
- Issue #8810: Unreliable execution from subdirectories
- Issue #17284: Doesn't trigger with initial arguments
- Issue #27365: Can't modify prompts, only add context

**Affects all projects** (including langfuse, which has identical setup)

**Verdict:** Not worth debugging. Use alternatives.

### PostToolUse DOES Work

**Proven in production:**
- Langfuse uses it successfully
- Reliable file tracking
- Good UX for confirmation

**Implemented in cortex-ai** (Option B)

### Path-Based Activation is Best

**Why it works:**
- Built into Claude Code (no bugs)
- Clean, predictable behavior
- No external dependencies
- Best user experience

**This is the primary method** - hooks are just nice-to-have additions

## Summary

| Feature | Status | Should You Use? |
|---------|--------|-----------------|
| Path-based skills (SKILL.md) | ✅ Production-ready | ✅ Primary method |
| PostToolUse file tracker | ✅ Production-ready | ✅ Nice UX addition |
| Manual skill checker | ✅ Production-ready | ✅ For planning |
| Path-based rules (.md) | ✅ Production-ready | ✅ Already using |
| UserPromptSubmit hooks | ❌ Broken in Claude Code | ❌ Skip entirely |

**Bottom line:** You have 4 working methods for skill activation. UserPromptSubmit is the only one that doesn't work, and you don't need it.

---

**Next Steps:**
- Start editing files in cortex-ai - skills auto-activate
- Use `./check-skill "prompt"` for planning
- See [HOOKS_SETUP_COMPLETE.md](HOOKS_SETUP_COMPLETE.md) for reference
