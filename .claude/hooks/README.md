# Claude Code Hooks

Automatically suggests relevant skills based on your prompts.

## Quick Start

```bash
cd .claude/hooks
npm install  # Install dependencies (already done)
```

## Test It

```bash
# Test with sample prompt
npx tsx skill-activation-prompt-langfuse.ts < test-input.json
```

**Expected output:**
```
🎯 CORTEX-AI SKILL ACTIVATION
📚 RECOMMENDED SKILLS:
  → /orchestration-dev
    Agent development patterns
```

## How It Works

Type: `"create a new agent"` → Hook suggests: `/orchestration-dev` skill

## Customize Triggers

Edit `.claude/skills/skill-rules.json`:

```json
{
  "skills": {
    "orchestration-dev": {
      "promptTriggers": {
        "keywords": ["agent", "tool", "orchestration"],
        "intentPatterns": ["(create|add).*?(agent|tool)"]
      }
    }
  }
}
```

Add keywords or regex patterns to match your workflow.

## Add New Skill

1. Create `.claude/skills/my-skill/SKILL.md`
2. Add trigger rules to `skill-rules.json`
3. Test: `echo '{"prompt":"test"}' | npx tsx skill-activation-prompt-langfuse.ts`

## Files

- `skill-activation-prompt.sh` - Shell wrapper
- `skill-activation-prompt-langfuse.ts` - Main logic
- `../skills/skill-rules.json` - Trigger configuration
- `test-input.json` - Sample test data

## Reference

See [CLAUDE_CODE_GUIDE.md](../../docs/CLAUDE_CODE_GUIDE.md) for complete documentation.
