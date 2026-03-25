"""
Skill discovery — scans directories for SKILL.md files and parses metadata.

Each SKILL.md can have optional YAML frontmatter::

    ---
    name: My Skill
    description: A short description
    triggers:
      - "when the user asks about X"
      - "keyword: foo"
    ---

    # Instructions
    ...
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

_DEFAULT_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"


@dataclass
class SkillDefinition:
    """Parsed skill with metadata and content."""

    name: str
    description: str
    content: str
    path: Path
    triggers: list[str] = field(default_factory=list)
    category: str = "global"


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter from markdown text.

    Returns (metadata_dict, remaining_content). Uses a minimal parser
    to avoid requiring PyYAML as a hard dependency.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    raw = match.group(1)
    body = text[match.end():]
    meta: dict = {}
    current_key: Optional[str] = None
    current_list: Optional[list] = None

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- ") and current_key and current_list is not None:
            val = stripped[2:].strip().strip('"').strip("'")
            current_list.append(val)
            continue

        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if current_key and current_list is not None:
                meta[current_key] = current_list

            if value:
                meta[key] = value
                current_key = None
                current_list = None
            else:
                current_key = key
                current_list = []

    if current_key and current_list is not None:
        meta[current_key] = current_list

    return meta, body


def discover_skills(
    skills_dir: Optional[Path] = None,
    category: Optional[str] = None,
    categories: Optional[list[str]] = None,
) -> list[SkillDefinition]:
    """Scan a directory tree for SKILL.md files and return parsed definitions.

    Supports hierarchical skill directories: ``global/`` skills are always
    included, plus any category-specific directories. This mirrors
    ml-infra's ``build_skills_middleware(module)`` pattern.

    Args:
        skills_dir: Root directory to scan. Defaults to ``cortex/skills/``.
        category: Single category to include alongside global.
        categories: Multiple categories to include (takes precedence
            over ``category`` when both are given).

    Returns:
        List of discovered SkillDefinition objects.
    """
    root = skills_dir or _DEFAULT_SKILLS_DIR
    skills: list[SkillDefinition] = []

    dirs_to_scan: list[tuple[Path, str]] = []

    global_dir = root / "global"
    if global_dir.is_dir():
        dirs_to_scan.append((global_dir, "global"))

    # Resolve the list of categories to scan
    cats: list[str] = []
    if categories:
        cats = list(categories)
    elif category:
        cats = [category]

    for cat_name in cats:
        cat_dir = root / cat_name.lower()
        if cat_dir.is_dir():
            dirs_to_scan.append((cat_dir, cat_name.lower()))
        else:
            logger.debug("No skills directory for category %s at %s", cat_name, cat_dir)

    for scan_dir, cat in dirs_to_scan:
        for skill_md in sorted(scan_dir.rglob("SKILL.md")):
            try:
                text = skill_md.read_text(encoding="utf-8")
            except Exception:
                logger.exception("Failed to read skill file %s", skill_md)
                continue

            meta, content = _parse_frontmatter(text)
            name = meta.get("name", skill_md.parent.name)
            desc = meta.get("description", "")
            triggers = meta.get("triggers", [])
            if isinstance(triggers, str):
                triggers = [triggers]

            skills.append(
                SkillDefinition(
                    name=name,
                    description=desc,
                    content=content.strip(),
                    path=skill_md,
                    triggers=triggers,
                    category=cat,
                )
            )

    logger.info(
        "Discovered %d skills from %s (categories=%s)",
        len(skills), root, cats or [category],
    )
    return skills
