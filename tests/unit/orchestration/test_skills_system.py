"""Unit tests for skills discovery, loader, and middleware."""

from pathlib import Path
import pytest
from langchain_core.messages import HumanMessage

from cortex.orchestration.skills.discovery import discover_skills
from cortex.orchestration.skills.loader import build_skill_files
from cortex.orchestration.skills.middleware import SkillsMiddleware


@pytest.mark.unit
class TestSkillDiscovery:
    def test_discovers_skills_from_filesystem(self, tmp_path: Path):
        global_dir = tmp_path / "global" / "my_skill"
        global_dir.mkdir(parents=True)
        skill_md = global_dir / "SKILL.md"
        skill_md.write_text(
            """---
name: My Skill
description: Does a thing
triggers:
  - "hello world"
---

# Instructions

Run the workflow.
""",
            encoding="utf-8",
        )
        skills = discover_skills(skills_dir=tmp_path, category=None)
        assert len(skills) == 1
        s = skills[0]
        assert s.name == "My Skill"
        assert "Does a thing" in s.description
        assert "hello world" in s.triggers
        assert "Run the workflow" in s.content
        assert s.category == "global"


@pytest.mark.unit
class TestSkillLoader:
    def test_build_skill_files_from_definitions(self, tmp_path: Path):
        skill_path = tmp_path / "global" / "pack" / "SKILL.md"
        skill_path.parent.mkdir(parents=True)
        skill_path.write_text("---\nname: Pack\n---\nCore text.", encoding="utf-8")

        files = build_skill_files(skills_dir=tmp_path)
        assert len(files) == 1
        key = "/skills/global/pack/SKILL.md"
        assert key in files
        assert files[key]["type"] == "text"
        assert "Pack" in files[key]["content"]
        assert "Core text" in files[key]["content"]


@pytest.mark.unit
class TestSkillsMiddleware:
    def test_trigger_matching_includes_matching_skill(self, tmp_path: Path):
        d = tmp_path / "global" / "t_skill"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            """---
name: Triggered
description: Desc
triggers:
  - "deploy to production"
---

Content here.
""",
            encoding="utf-8",
        )
        mw = SkillsMiddleware(skills_dir=tmp_path, always_include_global=False)
        ctx = mw.get_skill_context("Please deploy to production now")
        assert "<agent_skills>" in ctx
        assert "Triggered" in ctx
        assert "Content here" in ctx

    def test_trigger_matching_case_insensitive(self, tmp_path: Path):
        d = tmp_path / "global" / "x"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            '---\nname: X\ntriggers:\n  - "UPPERCASE"\n---\n\nbody',
            encoding="utf-8",
        )
        mw = SkillsMiddleware(skills_dir=tmp_path, always_include_global=False)
        ctx = mw.get_skill_context("use uppercase token here")
        assert "X" in ctx

    def test_transform_state_prepends_system_message(self, tmp_path: Path):
        d = tmp_path / "global" / "g"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("---\nname: GSkill\ntriggers:\n  - help\n---\n", encoding="utf-8")
        mw = SkillsMiddleware(skills_dir=tmp_path, always_include_global=False)
        state = {"messages": [HumanMessage(content="need help please")]}
        new_state = mw.transform_state(state)
        assert len(new_state["messages"]) == len(state["messages"]) + 1
        first = new_state["messages"][0]
        assert first.type == "system"
        assert "GSkill" in first.content
