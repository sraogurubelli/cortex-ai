# Cortex-AI Claude Code Setup - Complete! ✅

**Date:** March 26, 2026
**Total Documentation:** ~4,880 lines

---

## ✅ What Was Created

### 1. User-Level Configuration (All Projects)
- **File:** `~/.claude/CLAUDE.md`
- **Size:** 10KB (~430 lines)
- **Scope:** Personal preferences for ALL projects

### 2. Cortex-AI Project Configuration
- **File:** `cortex-ai/.claude/CLAUDE.md`
- **Size:** 5.7KB (~160 lines)
- **Scope:** Cortex-AI project only

### 3. Path-Specific Rules (5 files)
```
cortex-ai/.claude/rules/
├── orchestration.md  (13KB)  - Agent development patterns
├── api.md            (13KB)  - API endpoint conventions
├── rag.md            (7.6KB) - RAG query optimization
├── memory.md         (9.7KB) - Memory middleware patterns
└── testing.md        (14KB)  - Testing requirements
```

### 4. Skills (3 workflows)
```
cortex-ai/.claude/skills/
├── orchestration-dev/SKILL.md  (9.8KB) - Agent development
├── rag-query/SKILL.md          (4.8KB) - RAG debugging
└── api-endpoint/SKILL.md       (9.8KB) - API creation
```

### 5. Documentation
- **cortex-ai/docs/CLAUDE_CODE_GUIDE.md** (~1,400 lines)
  - Complete reference for CLAUDE.md, AGENTS.md, and Skills
- **CLAUDE_AGENTS_INVENTORY.md** (~850 lines)
  - Inventory of all CLAUDE.md/AGENTS.md files across projects

---

## 📖 How It Works

### Loading Hierarchy

**When you open Claude Code in cortex-ai:**

1. **User-level loads first:**
   ```
   ~/.claude/CLAUDE.md (personal preferences)
   ```

2. **Project-level loads second:**
   ```
   cortex-ai/.claude/CLAUDE.md (project guide)
   ```

3. **Path-specific rules auto-load:**
   - Edit `cortex/orchestration/agent.py` → loads `orchestration.md`
   - Edit `cortex/api/routes/chat.py` → loads `api.md`
   - Edit `cortex/rag/graphrag.py` → loads `rag.md`
   - Edit `cortex/memory/postgres_saver.py` → loads `memory.md`
   - Edit `tests/test_agent.py` → loads `testing.md`

### Skills Usage

**Manual invoke:**
```bash
/orchestration-dev  # Agent development patterns
/rag-query          # RAG query optimization
/api-endpoint       # Create API endpoint
```

**Auto-activation:**
- Skills auto-activate based on path patterns in frontmatter
- Example: Working on `cortex/orchestration/agent.py` may auto-suggest `/orchestration-dev`

---

## 🚀 Quick Start

### Test the Setup

```bash
# 1. View user-level configuration
cat ~/.claude/CLAUDE.md | head -50

# 2. View cortex-ai configuration
cat cortex-ai/.claude/CLAUDE.md

# 3. List rules
ls -la cortex-ai/.claude/rules/

# 4. List skills
ls -la cortex-ai/.claude/skills/

# 5. View a rule
cat cortex-ai/.claude/rules/orchestration.md | head -30

# 6. View a skill
cat cortex-ai/.claude/skills/orchestration-dev/SKILL.md | head -30
```

### Use in Claude Code

1. **Open cortex-ai in Claude Code**
   ```bash
   cd /Users/sgurubelli/aiplatform/cortex-ai
   # Open in VS Code with Claude Code extension
   # Or use: claude code .
   ```

2. **Edit a file to trigger rules**
   ```bash
   # This should auto-load orchestration.md rules:
   code cortex/orchestration/agent.py
   ```

3. **Try a skill**
   ```
   # In Claude Code chat:
   /orchestration-dev
   ```

---

## 📚 Key Files Reference

| File | Purpose | When It Loads |
|------|---------|---------------|
| `~/.claude/CLAUDE.md` | Personal preferences | Always (all projects) |
| `cortex-ai/.claude/CLAUDE.md` | Project guide | When in cortex-ai |
| `.claude/rules/orchestration.md` | Agent patterns | Editing orchestration code |
| `.claude/rules/api.md` | API conventions | Editing API code |
| `.claude/rules/rag.md` | RAG optimization | Editing RAG code |
| `.claude/rules/memory.md` | Memory patterns | Editing memory code |
| `.claude/rules/testing.md` | Test requirements | Editing tests |
| `.claude/skills/orchestration-dev/` | Agent workflow | `/orchestration-dev` |
| `.claude/skills/rag-query/` | RAG debugging | `/rag-query` |
| `.claude/skills/api-endpoint/` | API creation | `/api-endpoint` |

---

## 🎯 Common Tasks

### Add a New Rule

```bash
# 1. Create new rule file
vim cortex-ai/.claude/rules/my-new-rule.md

# 2. Add frontmatter with path patterns
---
paths:
  - "cortex/my-module/**/*.py"
---

# My New Rule
...content...
```

### Create a New Skill

```bash
# 1. Create skill directory
mkdir -p cortex-ai/.claude/skills/my-skill

# 2. Create SKILL.md
vim cortex-ai/.claude/skills/my-skill/SKILL.md

# 3. Add frontmatter
---
name: my-skill
description: What this skill does
paths:
  - "cortex/my-module/**/*.py"
---

# My Skill
...content...
```

### Update User Preferences

```bash
# Edit user-level CLAUDE.md
vim ~/.claude/CLAUDE.md
```

---

## 🔧 Customization Guide

### Adjust Code Style Preferences

**File:** `~/.claude/CLAUDE.md`

Change line 12-30 to match your preferences:
```markdown
### Python
- Use **Python 3.11+** with type hints
- Keep functions **under 50 lines**  # ← Adjust this
```

### Add Project-Specific Patterns

**File:** `cortex-ai/.claude/CLAUDE.md`

Add after line 50:
```markdown
## Our Team Patterns

- Use `logger.info()` for all agent operations
- Prefer composition over inheritance
```

### Customize Skills

**File:** `cortex-ai/.claude/skills/orchestration-dev/SKILL.md`

Edit to match your team's agent patterns.

---

## 📊 Statistics

| Category | Count | Total Lines |
|----------|-------|-------------|
| **User Config** | 1 file | ~430 lines |
| **Project Config** | 1 file | ~160 lines |
| **Rules** | 5 files | ~1,500 lines |
| **Skills** | 3 files | ~540 lines |
| **Documentation** | 2 files | ~2,250 lines |
| **TOTAL** | **12 files** | **~4,880 lines** |

---

## 🎓 Learning Path

### Week 1: Basics
1. Read `cortex-ai/.claude/CLAUDE.md`
2. Try editing a file to see rules auto-load
3. Invoke `/orchestration-dev` skill

### Week 2: Deep Dive
4. Read `cortex-ai/docs/CLAUDE_CODE_GUIDE.md`
5. Understand path-specific rules (`.claude/rules/`)
6. Create your first custom skill

### Week 3: Advanced
7. Customize `~/.claude/CLAUDE.md` for personal workflow
8. Add team-specific rules
9. Share skills with team

---

## 🆘 Troubleshooting

### Rules Not Loading?

**Check:**
1. File path matches pattern in frontmatter
2. Frontmatter syntax is correct (YAML)
3. File ends with `.md`

**Example:**
```markdown
---
paths:
  - "cortex/orchestration/**/*.py"  # Must match your file!
---
```

### Skills Not Appearing?

**Check:**
1. SKILL.md exists in skill directory
2. Frontmatter has `name:` field
3. `user-invocable: false` NOT set (hides from `/` menu)

### Can't See Guidelines Being Followed?

**Try:**
1. Ask Claude: "What are the testing requirements for this project?"
2. Should mention pytest-asyncio, 80% coverage, etc.

---

## 📖 Documentation

- **Complete Guide:** [cortex-ai/docs/CLAUDE_CODE_GUIDE.md](cortex-ai/docs/CLAUDE_CODE_GUIDE.md)
- **Inventory Report:** [CLAUDE_AGENTS_INVENTORY.md](CLAUDE_AGENTS_INVENTORY.md)
- **This Summary:** [cortex-ai/CLAUDE_SETUP_COMPLETE.md](cortex-ai/CLAUDE_SETUP_COMPLETE.md)

---

## ✅ Benefits

| Benefit | Description |
|---------|-------------|
| **Consistency** | Same patterns across all cortex-ai development |
| **Auto-loading** | Rules load exactly when you need them |
| **Reusability** | Skills for common workflows |
| **Discoverability** | Clear documentation, easy to find |
| **Scalability** | Easy to add more rules/skills |
| **Multi-project** | User-level config applies everywhere |
| **Team sharing** | Commit `.claude/` to git for team |

---

## 🚀 Next Steps

1. ✅ **Done:** User-level CLAUDE.md created
2. ✅ **Done:** Cortex-AI CLAUDE.md with rules and skills created
3. **Next:** Start coding in cortex-ai and see rules auto-load!
4. **Next:** Try `/orchestration-dev` skill
5. **Next:** Create custom skills for your workflow

---

## 💡 Pro Tips

- **Commit `.claude/` to git** so your team uses the same patterns
- **Keep rules under 200 lines** for better adherence
- **Use `@imports`** to avoid duplication (e.g., `@README.md`)
- **Create skills for repetitive tasks** (saves time)
- **Update rules as patterns evolve** (living documentation)

---

## 🎉 Success!

You now have:
- ✅ Personal preferences (user-level)
- ✅ Project configuration (cortex-ai)
- ✅ Path-specific rules (5 components)
- ✅ Reusable skills (3 workflows)
- ✅ Comprehensive documentation

**Ready to use Claude Code with Cortex-AI!** 🚀

---

**Questions?** Check the [CLAUDE_CODE_GUIDE.md](cortex-ai/docs/CLAUDE_CODE_GUIDE.md) or ask Claude Code!

**Last Updated:** March 26, 2026
