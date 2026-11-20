"""CLI commands for managing the aiida-cif2j Agent Skill."""

import shutil
from importlib.resources import as_file, files
from pathlib import Path

import click

SKILL_NAME = "aiida-cif2j"
DEFAULT_SKILLS_DIR = Path.home() / ".claude" / "skills"


def install_skill(target_dir: Path) -> Path:
    """Copy the aiida-cif2j Agent Skill into a skills directory.

    Parameters
    ----------
    target_dir : Path
        The skills directory to install into, e.g. ``~/.claude/skills``. Created if it
        does not already exist.

    Returns
    -------
    Path
        The path the skill was copied to.
    """
    source = files("aiida_cif2j") / "skills" / SKILL_NAME
    destination = target_dir / SKILL_NAME
    with as_file(source) as source_path:
        shutil.copytree(source_path, destination, dirs_exist_ok=True)
    return destination


@click.group(name="skills")
def skills_group():
    """Manage the aiida-cif2j Agent Skill."""


@skills_group.command("install")
@click.argument(
    "dir_name",
    required=False,
    type=click.Path(path_type=Path),
    default=None,
)
def install(dir_name: Path | None):
    """Copy the aiida-cif2j Agent Skill into a skills directory.

    Installs into DIR_NAME (default: '~/.claude/skills'), e.g. a project-local
    '.claude/skills'.
    """
    destination = install_skill((dir_name or DEFAULT_SKILLS_DIR).expanduser())
    click.echo(f"Installed the aiida-cif2j skill to {destination}")
