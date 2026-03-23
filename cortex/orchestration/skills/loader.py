"""
Skill file loader — converts discovered skills into virtual file maps
suitable for seeding into LangGraph state (SwarmState.files).
"""

import logging
from pathlib import Path
from typing import Any, Optional

from .discovery import discover_skills

logger = logging.getLogger(__name__)

_VIRTUAL_ROOT = "/skills"


def _file_entry(content: str) -> dict[str, Any]:
    """Create a file data dict compatible with filesystem middleware."""
    return {
        "content": content,
        "type": "text",
    }


def build_skill_files(
    skills_dir: Optional[Path] = None,
    category: Optional[str] = None,
) -> dict[str, Any]:
    """Load skill files from disk into a dict for seeding LangGraph state.

    The returned dict maps virtual paths to file data dicts and should be
    merged into the ``files`` key when invoking a swarm::

        skill_files = build_skill_files(category="analytics")
        result = graph.ainvoke({"messages": [...], "files": skill_files})

    Args:
        skills_dir: Root directory to scan. Defaults to ``cortex/skills/``.
        category: Optional category to include alongside global skills.

    Returns:
        Dict of virtual-path to file-data for all applicable skills.
    """
    skills = discover_skills(skills_dir=skills_dir, category=category)
    files: dict[str, Any] = {}

    for skill in skills:
        rel = skill.path.parent.name
        virtual_path = f"{_VIRTUAL_ROOT}/{skill.category}/{rel}/SKILL.md"
        full_content = skill.content
        if skill.name or skill.description:
            header = f"# {skill.name}\n\n" if skill.name else ""
            if skill.description:
                header += f"{skill.description}\n\n"
            full_content = header + full_content
        files[virtual_path] = _file_entry(full_content)

    logger.info("Built %d skill files for category=%s", len(files), category)
    return files
