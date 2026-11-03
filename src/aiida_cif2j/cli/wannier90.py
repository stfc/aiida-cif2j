"""CLI commands for the Wannier90 integration (`WannierTB2JWorkChain`)."""

import json
import subprocess
import sys
from pathlib import Path

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


class _JsonParamType(click.ParamType):
    """A click parameter accepting inline JSON, or a JSON file prefixed with '@'."""

    name = "json"

    def convert(self, value, param, ctx):
        """Parse `value` as JSON, reading it from a file first if prefixed with '@'."""
        if not isinstance(value, str):
            return value

        if value.startswith("@"):
            path = Path(value[1:])
            try:
                value = path.read_text()
            except OSError as exception:
                self.fail(f"cannot read '{path}': {exception}", param, ctx)

        try:
            return json.loads(value)
        except json.JSONDecodeError as exception:
            self.fail(f"invalid JSON: {exception}", param, ctx)


JSON = _JsonParamType()


@wannier90_group.command("submit")
@click.argument(
    "mcif_file", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.option(
    "--pw-code",
    required=True,
    help="Label or PK of the configured 'pw.x' (Quantum ESPRESSO) code.",
)
@click.option(
    "--pw2wannier90-code",
    required=True,
    help="Label or PK of the configured 'pw2wannier90.x' code.",
)
@click.option(
    "--wannier90-code",
    required=True,
    help="Label or PK of the configured 'wannier90.x' code.",
)
@click.option(
    "--tb2j-code",
    required=True,
    help="Label or PK of the configured 'wann2J.py' (TB2J) code.",
)
@click.option(
    "--projwfc-code",
    default=None,
    help="Label or PK of the configured 'projwfc.x' code. Only needed for "
    "'--projection-type atomic_projectors_qe'.",
)
@click.option(
    "--open-grid-code",
    default=None,
    help="Label or PK of the configured 'open_grid.x' code, if using "
    "'--run-open-grid'.",
)
@click.option(
    "--pseudo-family",
    required=True,
    help="Pseudopotential family to use for the QE/Wannier90 steps (e.g. "
    "'SSSP/1.3/PBE/efficiency').",
)
@click.option(
    "--protocol",
    default=None,
    help="Protocol forwarded to Wannier90BandsWorkChain.get_builder_from_protocol "
    "(e.g. 'fast', 'moderate', 'precise'). Defaults to that workchain's own default "
    "('moderate') if not given.",
)
@click.option(
    "--spin-type",
    type=click.Choice(["none", "collinear", "non_collinear", "spin_orbit"]),
    default="collinear",
    show_default=True,
    help="Spin treatment for the calculation.",
)
@click.option(
    "--electronic-type",
    type=click.Choice(["metal", "insulator"]),
    default="metal",
    show_default=True,
    help="Electronic treatment for the calculation. 'metal' reports a single "
    "'fermi_energy', which the TB2J step's efermi auto-fill requires; 'insulator' + "
    "'collinear' instead produces split 'fermi_energy_up'/'fermi_energy_down' keys "
    "that are not auto-filled.",
)
@click.option(
    "--projection-type",
    type=click.Choice(["analytic", "random", "scdm", "atomic_projectors_qe"]),
    default="atomic_projectors_qe",
    show_default=True,
    help="Wannier90 initial projection type. Some 'wannier90.x' builds reject the "
    "'dis_proj_min'/'dis_proj_max' keywords needed by 'atomic_projectors_qe'; use "
    "'analytic' if so.",
)
@click.option(
    "--wannier90-withmpi",
    is_flag=True,
    default=False,
    help="Run 'wannier90.x' under MPI. By default single-task resources are forced, "
    "to avoid a known file-locking crash from an unintentionally-serial binary "
    "launched under 'mpirun -n N'.",
)
@click.option(
    "--run-open-grid",
    is_flag=True,
    default=False,
    help="Use 'open_grid.x' to unfold the irreducible nscf k-mesh instead of "
    "recomputing it explicitly. Requires '--open-grid-code'.",
)
@click.option(
    "--magnetic-element",
    "magnetic_elements",
    multiple=True,
    metavar="SYMBOL",
    help="Chemical symbol of an element for which the exchange interaction is "
    "considered. Repeat for multiple elements. If not given, auto-detected at "
    "runtime from the parsed 'mcif' structure's per-kind magnetic moments.",
)
@click.option(
    "--tb2j-parameters",
    type=JSON,
    default=None,
    metavar="JSON",
    help="JSON object (or '@file.json') of 'wann2J.py' parameters, e.g. "
    "'{\"kmesh\": [5, 5, 5], \"rcut\": 10.0}'. The 'efermi' key is auto-filled from "
    "the Wannier90 SCF output if omitted.",
)
@click.option(
    "--tb2j-options",
    type=JSON,
    default=None,
    metavar="JSON",
    help="JSON object (or '@file.json') of 'metadata.options' for the TB2J "
    'calculation, e.g. \'{"resources": {"num_machines": 1}}\'. If not given, '
    "WannierTB2JCalculation's own defaults apply.",
)
@click.option(
    "--profile",
    default=None,
    help="AiiDA profile to load. Defaults to the default profile.",
)
@click.option(
    "--label", default=None, help="Label to set on the submitted WorkChain node."
)
@click.option(
    "--description",
    default=None,
    help="Description to set on the submitted WorkChain node.",
)
@click.option(
    "--group",
    default=None,
    help="Label of an AiiDA group to add the submitted WorkChain node to (created if "
    "it does not already exist).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Build and validate the inputs, print a summary, and exit without "
    "submitting anything.",
)
def submit(
    mcif_file,
    pw_code,
    pw2wannier90_code,
    wannier90_code,
    tb2j_code,
    projwfc_code,
    open_grid_code,
    pseudo_family,
    protocol,
    spin_type,
    electronic_type,
    projection_type,
    wannier90_withmpi,
    run_open_grid,
    magnetic_elements,
    tb2j_parameters,
    tb2j_options,
    profile,
    label,
    description,
    group,
    dry_run,
):
    """Submit a `WannierTB2JWorkChain` built from an '.mcif' structure file.

    Builds a ready-to-submit `ProcessBuilder` via
    `WannierTB2JWorkChain.get_builder_from_protocol` and submits it to the AiiDA
    daemon. Defaults for options not given on the command line follow the choices
    documented in that method's own docstring.
    """
    if run_open_grid and not open_grid_code:
        raise click.UsageError("'--run-open-grid' requires '--open-grid-code'.")

    from aiida import load_profile, orm
    from aiida.engine import submit as aiida_submit
    from aiida_quantumespresso.common.types import ElectronicType, SpinType
    from aiida_wannier90_workflows.common.types import WannierProjectionType

    from aiida_cif2j.workflows.wannier import WannierTB2JWorkChain

    load_profile(profile)

    codes: dict[str, str] = {
        "pw": pw_code,
        "pw2wannier90": pw2wannier90_code,
        "wannier90": wannier90_code,
        "tb2j": tb2j_code,
    }
    if projwfc_code:
        codes["projwfc"] = projwfc_code
    if open_grid_code:
        codes["open_grid"] = open_grid_code

    structure = orm.SinglefileData(file=str(mcif_file.resolve()))

    builder = WannierTB2JWorkChain.get_builder_from_protocol(
        codes=codes,
        structure=structure,
        pseudo_family=pseudo_family,
        protocol=protocol,
        spin_type=SpinType(spin_type),
        electronic_type=ElectronicType(electronic_type),
        projection_type=WannierProjectionType(projection_type),
        wannier90_withmpi=wannier90_withmpi,
        magnetic_elements=list(magnetic_elements) or None,
        tb2j_parameters=tb2j_parameters,
        tb2j_options=tb2j_options,
        run_open_grid=run_open_grid,
    )

    if label:
        builder.metadata.label = label
    if description:
        builder.metadata.description = description

    if dry_run:
        click.echo(f"Would submit WannierTB2JWorkChain with inputs:\n{builder}")
        return

    node = aiida_submit(builder)
    click.echo(f"Submitted WannierTB2JWorkChain<{node.pk}>")

    if group:
        aiida_group, _ = orm.Group.collection.get_or_create(label=group)
        aiida_group.add_nodes([node])
        click.echo(f"Added WannierTB2JWorkChain<{node.pk}> to group '{group}'")
