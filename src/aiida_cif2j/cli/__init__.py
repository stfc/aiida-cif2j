"""Command line interface for the `aiida-cif2j` plugin."""

import click

from aiida_cif2j.cli.wannier90 import wannier90_group


@click.group()
def cli():
    """Command line utilities for the `aiida-cif2j` plugin."""


cli.add_command(wannier90_group)
