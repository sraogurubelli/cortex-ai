"""
Skills middleware — injects discovered skill instructions into agent context.

Lightweight replacement for deepagents.SkillsMiddleware that works
with the cortex middleware pipeline.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from .discovery import SkillDefinition, discover_skills

logger = logging.getLogger(__name__)


class SkillsMiddleware:
    """Middleware that prepends skill instructions to the message state.

    On each invocation it checks the latest user message against skill
    triggers and injects matching skill content as a system-level context
    block.

    Args:
        skills_dir: Root skills directory. Defaults to ``cortex/skills/``.
        category: Skill category to load alongside global.
        always_include_global: Whether to always inject global skill content
            regardless of trigger matches (default True).
    """

    def __init__(
        self,
        skills_dir: Optional[Path] = None,
        category: Optional[str] = None,
        always_include_global: bool = True,
    ):
        self._skills = discover_skills(skills_dir=skills_dir, category=category)
        self._always_global = always_include_global
        logger.info(
            "SkillsMiddleware initialized with %d skills", len(self._skills)
        )

    @property
    def skills(self) -> list[SkillDefinition]:
        return list(self._skills)

    def _match_triggers(self, text: str) -> list[SkillDefinition]:
        """Return skills whose triggers match the given text."""
        text_lower = text.lower()
        matched: list[SkillDefinition] = []
        for skill in self._skills:
            if not skill.triggers:
                continue
            for trigger in skill.triggers:
                if trigger.lower() in text_lower:
                    matched.append(skill)
                    break
        return matched

    def get_skill_context(self, user_message: str = "") -> str:
        """Build the skill context string to inject into the agent.

        Args:
            user_message: Latest user message for trigger matching.

        Returns:
            Formatted skill instructions string (may be empty).
        """
        relevant: list[SkillDefinition] = []

        if self._always_global:
            relevant.extend(s for s in self._skills if s.category == "global")

        triggered = self._match_triggers(user_message)
        seen_names = {s.name for s in relevant}
        for s in triggered:
            if s.name not in seen_names:
                relevant.append(s)
                seen_names.add(s.name)

        if not relevant:
            return ""

        parts = ["<agent_skills>"]
        for skill in relevant:
            parts.append(f"\n## {skill.name}")
            if skill.description:
                parts.append(skill.description)
            parts.append(skill.content)
        parts.append("\n</agent_skills>")
        return "\n".join(parts)

    def transform_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """Transform LangGraph state by injecting skill context.

        Adds a system message with skill instructions at the beginning
        of the messages list.
        """
        messages = state.get("messages", [])
        last_user_msg = ""
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "human":
                last_user_msg = str(msg.content)
                break
            elif isinstance(msg, dict) and msg.get("role") == "user":
                last_user_msg = str(msg.get("content", ""))
                break

        context = self.get_skill_context(last_user_msg)
        if not context:
            return state

        from langchain_core.messages import SystemMessage

        skill_msg = SystemMessage(content=context)
        new_messages = [skill_msg] + list(messages)
        return {**state, "messages": new_messages}
