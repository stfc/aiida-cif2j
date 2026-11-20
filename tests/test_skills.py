"""Tests for the Agent Skill shipped with aiida-cif2j."""

from importlib import resources

import yaml

SKILL_PATH = resources.files("aiida_cif2j") / "skills" / "aiida-cif2j" / "SKILL.md"


def _read_frontmatter(text: str) -> dict:
    """Parse the YAML frontmatter delimited by ``---`` lines from a SKILL.md body."""
    _, frontmatter, _ = text.split("---", 2)
    return yaml.safe_load(frontmatter)


def test_skill_file_is_packaged():
    """The SKILL.md file is present alongside the installed package."""
    assert SKILL_PATH.is_file()


def test_skill_frontmatter_has_required_fields():
    """The SKILL.md frontmatter declares a non-empty name and description."""
    frontmatter = _read_frontmatter(SKILL_PATH.read_text())

    assert frontmatter["name"].strip() == "aiida-cif2j"
    assert frontmatter["description"].strip()
