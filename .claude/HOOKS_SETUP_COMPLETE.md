# Skills & Hooks - Setup Complete ✅

**Status:** Production-ready skill activation using proven techniques

## What Actually Works

### ✅ Working Now (Use These)

1. **Path-based skill activation** (SKILL.md frontmatter)
   - Edit `cortex/orchestration/*.py` → orchestration-dev loads automatically
   - Edit `cortex/rag/*.py` → rag-query loads automatically
   - Edit `cortex/api/*.py` → api-endpoint loads automatically

2. **PostToolUse file tracker** (NEW!)
   - After editing files, suggests relevant skills
   - Shows which module you're working in
   - **Proven to work** (adapted from langfuse)

3. **Manual skill checking**
   ```bash
   ./check-skill "create a new agent"
   # Shows: /orchestration-dev recommended
   ```

4. **Path-based rules** (`.claude/rules/*.md`)
   - Auto-load when editing matching files
   - Already working across all modules

### ⏸️ Configured But Not Working

- **UserPromptSubmit hooks** - Due to known Claude Code bugs (#8810, #17284)
- Auto-activation on prompts doesn't work yet
- Use manual checking instead: `./check-skill "prompt"`

## Files Installed

```
.claude/
├── settings.json                           # Hook configuration
├── skills/
│   ├── skill-rules.json                   # Trigger patterns
│   ├── orchestration-dev/SKILL.md         # Agent development
│   ├── rag-query/SKILL.md                 # RAG optimization
│   └── api-endpoint/SKILL.md              # API endpoints
└── hooks/
    ├── file-tracker.sh                    # ✅ PostToolUse (working)
    ├── skill-activation-prompt.sh         # ⏸️ UserPromptSubmit (not working)
    ├── skill-activation-prompt-langfuse.ts
    ├── manual-skill-check.sh              # ✅ Manual testing (working)
    └── package.json
```

## Quick Test

### Test PostToolUse Hook

Edit any file in cortex-ai and you'll see:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 Edited: Orchestration module
💡 Skill available: /orchestration-dev
   (Agent development patterns)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Test Manual Skill Check

```bash
./check-skill "I want to optimize my RAG search"
```

**Output:**
```
🎯 CORTEX-AI SKILL ACTIVATION
📚 RECOMMENDED SKILLS:
  → /rag-query
    RAG optimization and debugging
```

## Available Skills

| Skill | Auto-loads When | Manual Invoke |
|-------|----------------|---------------|
| **orchestration-dev** | Editing `cortex/orchestration/**/*.py` | `/orchestration-dev` |
| **rag-query** | Editing `cortex/rag/**/*.py` | `/rag-query` |
| **api-endpoint** | Editing `cortex/api/**/*.py` | `/api-endpoint` |

## Usage Patterns

### Pattern 1: Planning Work
```bash
# Before starting, check which skills apply
./check-skill "create a data analysis agent with RAG"

# Shows: /orchestration-dev, /rag-query
```

### Pattern 2: Working in Files
```bash
# Just edit files - path-based activation works automatically
# Edit cortex/orchestration/agent.py
# → orchestration-dev SKILL.md loads
# → orchestration.md rules load
# → PostToolUse hook confirms
```

### Pattern 3: Manual Skill Load
```
# In conversation, ask Claude:
"Use the orchestration-dev skill to help me create an agent"
```

## What We Learned

**UserPromptSubmit hooks don't work reliably:**
- Claude Code bugs: #8810, #17284, #27365
- Affects ALL projects (including langfuse)
- Not worth debugging further
- Use alternatives instead

**PostToolUse hooks DO work:**
- Proven in production (langfuse uses them)
- Reliable file tracking
- Good user experience

**Path-based activation is best:**
- SKILL.md frontmatter with `paths:` field
- Works today, no bugs
- Cleanest user experience

## Status Summary

| Feature | Status | Use It? |
|---------|--------|---------|
| Path-based skills | ✅ Working | ✅ Primary method |
| PostToolUse hooks | ✅ Working | ✅ Great UX addition |
| Manual skill check | ✅ Working | ✅ For planning |
| UserPromptSubmit hooks | ❌ Not working | ❌ Skip it |
| Path-based rules | ✅ Working | ✅ Already using |

## Troubleshooting

**Q: PostToolUse hook not showing output?**
A: Check that `jq` is installed: `brew install jq`

**Q: Want to customize file tracker?**
A: Edit `.claude/hooks/file-tracker.sh` and add your own patterns

**Q: Manual skill check fails?**
A: Ensure dependencies installed:
```bash
cd .claude/hooks
npm install
```

---

**Next:** See [SKILL_ACTIVATION_GUIDE.md](SKILL_ACTIVATION_GUIDE.md) for complete guide
