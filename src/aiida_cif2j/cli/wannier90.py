"""CLI commands for installing and managing the Wannier90 AiiDA plugins."""

import subprocess
import sys

import click

AIIDA_WANNIER90_REQUIREMENT = (
    "aiida-wannier90 @ git+https://github.com/aiidateam/aiida-wannier90.git@v2.2.0"
)
AIIDA_WANNIER90_WORKFLOWS_REQUIREMENT = (
    "aiida-wannier90-workflows @ "
    "git+https://github.com/aiidateam/aiida-wannier90-workflows.git@v3.1.0"
)


@click.group(name="wannier90")
def wannier90_group():
    """Commands for the Wannier90 integration (`WannierTB2JWorkChain`)."""


@wannier90_group.command("install")
def install():
    """Install 'aiida-wannier90' and 'aiida-wannier90-workflows' from GitHub.

    Neither package is released on PyPI, so this installs the pinned versions that
    this project is developed and tested against directly from their git
    repositories, into the current Python environment.
    """
    requirements = [AIIDA_WANNIER90_REQUIREMENT, AIIDA_WANNIER90_WORKFLOWS_REQUIREMENT]

    click.echo("Installing the Wannier90 AiiDA plugins:")
    for requirement in requirements:
        click.echo(f"  {requirement}")

    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", *requirements], check=True
        )
    except subprocess.CalledProcessError as exception:
        raise click.ClickException(
            "Failed to install the Wannier90 AiiDA plugins; see the pip output "
            "above for details."
        ) from exception

    click.secho("Successfully installed the Wannier90 AiiDA plugins.", fg="green")
