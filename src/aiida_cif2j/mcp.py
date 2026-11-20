"""aiida-cif2j tools for aiida-mcp, registered via the aiida_mcp.plugins entry point."""

from typing import Any

from aiida import orm
from aiida.common import MultipleObjectsError, NotExistent
from aiida.engine import submit
from aiida.engine.daemon.client import get_daemon_client
from aiida.manage.configuration import get_profile
from aiida.plugins import WorkflowFactory
from aiida_mcp import connection
from aiida_mcp.plugins.calcjob import (
    calcjob_available,
    describe_calcjob,
    load_code,
    submit_calcjob,
)
from aiida_mcp.plugins.inputs import (
    ControlInput,
    FileInput,
    build_node,
    load_existing_node,
)
from aiida_mcp.plugins.workflow import describe_workflow, workflow_available
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

CALCJOB_ENTRY_POINT = "cif2j.wannier_tb2j"
WORKFLOW_ENTRY_POINT = "cif2j.wannier_tb2j"

CALCJOB_DATA_INPUT_NAMES = (
    "elements",
    "parameters",
    "structure",
    "wannier_folder",
    "wannier_folder_up",
    "wannier_folder_down",
)


def is_available() -> bool:
    """Return whether the aiida-cif2j calcjob plugin is installed.

    Returns
    -------
    bool
        True if the ``cif2j.wannier_tb2j`` calcjob entry point is installed.
    """
    return calcjob_available(CALCJOB_ENTRY_POINT)


def _wannier90_available() -> bool:
    """Return whether the full Wannier90 -> TB2J WorkChain can be used.

    Checks both that the ``cif2j.wannier_tb2j`` workflow entry point is installed, and
    that its underlying third-party dependencies (``aiida-quantumespresso``,
    ``aiida-wannier90-workflows``) are actually importable. The latter are not
    published on PyPI and must be installed separately (see ``cif2j wannier90
    install``), so the workflow entry point can exist in aiida-cif2j's own metadata
    while still being unusable.

    Returns
    -------
    bool
        True if `WannierTB2JWorkChain` can be used.
    """
    if not workflow_available(WORKFLOW_ENTRY_POINT):
        return False
    try:
        import aiida_quantumespresso  # noqa: F401
        import aiida_wannier90_workflows  # noqa: F401
    except ImportError:
        return False
    return True


def submit_job(
    code: str | int,
    elements: list[str],
    parameters: ControlInput,
    structure: FileInput | None = None,
    use_wannier_structure: bool = False,
    wannier_folder: int | None = None,
    wannier_folder_up: int | None = None,
    wannier_folder_down: int | None = None,
    num_machines: int = 1,
    num_mpiprocs_per_machine: int = 1,
    label: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Build the inputs for a WannierTB2JCalculation and submit it to the daemon.

    This is the low-level TB2J step: it reads an existing Wannier90 calculation's
    retrieved output folder directly, so it is only useful once that Wannier90
    calculation has already run. For the full structure-to-exchange-couplings
    pipeline (Quantum ESPRESSO + Wannier90 + TB2J in one go), use
    `submit_wannier_tb2j_workflow` instead.

    Parameters
    ----------
    code : str or int
        Label (e.g. ``tb2j@localhost``) or PK of the TB2J code.
    elements : list of str
        Magnetic elements for which the exchange interaction is considered.
    parameters : ControlInput
        TB2J command-line parameters as a dict of parameters (must include
        ``efermi``), or the path/text/PK of an existing `Dict` node.
    structure : FileInput or None
        The structure, as a path, text, or PK of a `StructureData` or
        `SinglefileData` node. Required unless `use_wannier_structure` is
        true and ``kmesh`` is given explicitly in `parameters`.
    use_wannier_structure : bool
        If true, read atomic positions from the Wannier90 `.win` file
        instead of writing a POSCAR/posfile from `structure`.
    wannier_folder : int or None
        PK of the `retrieved` `FolderData` of a single non-collinear/
        spin-orbit Wannier90 calculation. Mutually exclusive with
        `wannier_folder_up`/`wannier_folder_down`.
    wannier_folder_up : int or None
        PK of the `retrieved` `FolderData` of the spin-up Wannier90
        calculation, for a collinear spin-polarised run. Requires
        `wannier_folder_down` to also be given.
    wannier_folder_down : int or None
        PK of the `retrieved` `FolderData` of the spin-down Wannier90
        calculation. Requires `wannier_folder_up` to also be given.
    num_machines : int
        Number of machines to run on.
    num_mpiprocs_per_machine : int
        MPI processes per machine.
    label : str or None
        Optional label to set on the calcjob node.
    description : str or None
        Optional description to set on the calcjob node.

    Returns
    -------
    dict[str, Any]
        The process PK, uuid, label, description, code, input node PKs, and
        daemon state.

    Raises
    ------
    ToolError
        If `num_machines` or `num_mpiprocs_per_machine` is below 1, `code`
        does not match a known code, or an input fails validation.
    """
    connection.ensure_profile()

    resources = (
        ("num_machines", num_machines),
        ("num_mpiprocs_per_machine", num_mpiprocs_per_machine),
    )
    for name, value in resources:
        if value < 1:
            raise ToolError(f"{name} must be at least 1, got {value}")

    metadata: dict[str, Any] = {
        "options": {
            "resources": {
                "num_machines": num_machines,
                "num_mpiprocs_per_machine": num_mpiprocs_per_machine,
            }
        }
    }
    if label is not None:
        metadata["label"] = label
    if description is not None:
        metadata["description"] = description

    inputs: dict[str, Any] = {
        "code": load_code(code),
        "elements": orm.List(list(elements)),
        "parameters": build_node(
            parameters, "parameters", "parameters.json", (orm.Dict,)
        ),
        "use_wannier_structure": use_wannier_structure,
        "metadata": metadata,
    }
    if structure is not None:
        inputs["structure"] = build_node(
            structure,
            "structure",
            "structure.xyz",
            (orm.StructureData, orm.SinglefileData),
        )
    if wannier_folder is not None:
        inputs["wannier_folder"] = load_existing_node(
            wannier_folder, "wannier_folder", (orm.FolderData,)
        )
    if wannier_folder_up is not None:
        inputs["wannier_folder_up"] = load_existing_node(
            wannier_folder_up, "wannier_folder_up", (orm.FolderData,)
        )
    if wannier_folder_down is not None:
        inputs["wannier_folder_down"] = load_existing_node(
            wannier_folder_down, "wannier_folder_down", (orm.FolderData,)
        )

    node = submit_calcjob(CALCJOB_ENTRY_POINT, inputs)

    daemon_running = get_daemon_client(get_profile().name).is_daemon_running
    result: dict[str, Any] = {
        "pk": node.pk,
        "uuid": node.uuid,
        "label": node.label,
        "description": node.description,
        "code": inputs["code"].full_label,
        "inputs": {
            name: inputs[name].pk for name in CALCJOB_DATA_INPUT_NAMES if name in inputs
        },
        "daemon_running": daemon_running,
    }
    if not daemon_running:
        result["note"] = "The daemon is not running; the job will wait until it starts."
    return result


def submit_workflow_job(
    codes: dict[str, str | int],
    structure: FileInput,
    pseudo_family: str | None = None,
    protocol: str | None = None,
    spin_type: str = "collinear",
    electronic_type: str = "metal",
    projection_type: str = "analytic",
    wannier90_withmpi: bool = False,
    magnetic_elements: list[str] | None = None,
    tb2j_parameters: dict[str, Any] | None = None,
    tb2j_options: dict[str, Any] | None = None,
    label: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Build and submit the full Wannier90 -> TB2J WorkChain from a protocol.

    Runs Quantum ESPRESSO SCF/NSCF, Wannierisation, and TB2J in one pipeline, via
    `WannierTB2JWorkChain.get_builder_from_protocol`. Magnetic elements and the Fermi
    energy are auto-detected unless given explicitly.

    Parameters
    ----------
    codes : dict[str, str or int]
        Code label or PK for each step, keyed by ``pw``, ``pw2wannier90``,
        ``wannier90``, ``tb2j``, and optionally ``projwfc``/``open_grid``. A
        ``tb2j`` entry is required.
    structure : FileInput
        The input structure, as a path, text, or PK of a `StructureData`,
        `MagneticStructureData`, or `SinglefileData` node (an ``MCIF`` file,
        parsed automatically).
    pseudo_family : str or None
        The pseudopotential family to use for the Wannier90/QE steps.
    protocol : str or None
        The protocol to use for the underlying Wannier90BandsWorkChain.
    spin_type : str
        One of ``none``, ``collinear``, ``non_collinear``, ``spin_orbit``.
    electronic_type : str
        One of ``metal``, ``insulator``, ``automatic``.
    projection_type : str
        One of ``analytic``, ``random``, ``scdm``, ``atomic_projectors_qe``.
    wannier90_withmpi : bool
        Whether to run ``wannier90.x`` under MPI. False by default, which also
        forces single-task resources for that step.
    magnetic_elements : list of str or None
        Elements for which the exchange interaction is considered. If not
        given, auto-detected from the resolved structure at runtime.
    tb2j_parameters : dict or None
        TB2J command-line parameters (the ``tb2j.parameters`` input).
        ``efermi`` is auto-filled from the Wannier90 SCF output if omitted.
    tb2j_options : dict or None
        ``metadata.options`` for the TB2J calculation step. Uses
        `submit_cif2j_job`'s defaults if not given.
    label : str or None
        Optional label to set on the workflow node.
    description : str or None
        Optional description to set on the workflow node.

    Returns
    -------
    dict[str, Any]
        The process PK, uuid, label, description, the structure node's PK,
        and daemon state.

    Raises
    ------
    ToolError
        If `spin_type`/`electronic_type`/`projection_type` is not a
        recognised value, `codes` is missing the required ``tb2j`` entry or
        names an unknown code, or `structure` fails validation.
    """
    connection.ensure_profile()

    from aiida_wannier90_workflows.common.types import (
        ElectronicType,
        SpinType,
        WannierProjectionType,
    )
    from aiida_wannier90_workflows.data.structure import MagneticStructureData

    spin_type_enum = _parse_enum(SpinType, spin_type, "spin_type")
    electronic_type_enum = _parse_enum(
        ElectronicType, electronic_type, "electronic_type"
    )
    projection_type_enum = _parse_enum(
        WannierProjectionType, projection_type, "projection_type"
    )

    structure_node = build_node(
        structure,
        "structure",
        "structure.mcif",
        (orm.StructureData, orm.SinglefileData, MagneticStructureData),
    )

    workflow = WorkflowFactory(WORKFLOW_ENTRY_POINT)
    try:
        builder = workflow.get_builder_from_protocol(
            codes=codes,
            structure=structure_node,
            pseudo_family=pseudo_family,
            protocol=protocol,
            spin_type=spin_type_enum,
            electronic_type=electronic_type_enum,
            projection_type=projection_type_enum,
            wannier90_withmpi=wannier90_withmpi,
            magnetic_elements=magnetic_elements,
            tb2j_parameters=tb2j_parameters,
            tb2j_options=tb2j_options,
        )
    except (ValueError, TypeError, NotExistent, MultipleObjectsError) as exc:
        raise ToolError(str(exc)) from exc

    if label is not None:
        builder.metadata.label = label
    if description is not None:
        builder.metadata.description = description

    node = submit(builder)

    daemon_running = get_daemon_client(get_profile().name).is_daemon_running
    result: dict[str, Any] = {
        "pk": node.pk,
        "uuid": node.uuid,
        "label": node.label,
        "description": node.description,
        "structure": structure_node.pk,
        "daemon_running": daemon_running,
    }
    if not daemon_running:
        result["note"] = "The daemon is not running; the job will wait until it starts."
    return result


def _parse_enum(enum_cls, value: str, name: str):
    try:
        return enum_cls(value)
    except ValueError as exc:
        options = ", ".join(member.value for member in enum_cls)
        raise ToolError(f"{name}: {exc}; choose one of {options}") from exc


def register(mcp: MCPServer) -> None:
    """Register the aiida-cif2j tools on the given MCP server.

    Parameters
    ----------
    mcp : MCPServer
        The server to register the aiida-cif2j tools on.
    """

    @mcp.tool()
    def describe_cif2j_calcjob() -> dict[str, Any]:
        """Describe the WannierTB2J calcjob: inputs, outputs, exit codes and defaults.

        Returns
        -------
        dict[str, Any]
            The calcjob's inputs, outputs, exit codes and changed metadata
            option defaults.
        """
        return describe_calcjob(CALCJOB_ENTRY_POINT)

    @mcp.tool()
    def submit_cif2j_job(
        code: str | int,
        elements: list[str],
        parameters: ControlInput,
        structure: FileInput | None = None,
        use_wannier_structure: bool = False,
        wannier_folder: int | None = None,
        wannier_folder_up: int | None = None,
        wannier_folder_down: int | None = None,
        num_machines: int = 1,
        num_mpiprocs_per_machine: int = 1,
        label: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Submit the low-level TB2J calculation to the daemon.

        Creates nodes and starts a run. Reads an existing Wannier90 calculation's
        retrieved output folder directly, so it is only useful once that Wannier90
        calculation has already run. For the full structure-to-exchange-couplings
        pipeline, use `submit_wannier_tb2j_workflow` instead. Follow the job with
        `get_process` and `get_process_report`.

        Parameters
        ----------
        code : str or int
            Label (e.g. ``tb2j@localhost``) or PK of the TB2J code.
        elements : list of str
            Magnetic elements for which the exchange interaction is considered.
        parameters : ControlInput
            TB2J command-line parameters as a dict of parameters (must include
            ``efermi``), or the path/text/PK of an existing `Dict` node.
        structure : FileInput or None
            The structure, as a path, text, or PK of a `StructureData` or
            `SinglefileData` node. Required unless `use_wannier_structure` is
            true and ``kmesh`` is given explicitly in `parameters`.
        use_wannier_structure : bool
            If true, read atomic positions from the Wannier90 `.win` file
            instead of writing a POSCAR/posfile from `structure`.
        wannier_folder : int or None
            PK of the `retrieved` `FolderData` of a single non-collinear/
            spin-orbit Wannier90 calculation. Mutually exclusive with
            `wannier_folder_up`/`wannier_folder_down`.
        wannier_folder_up : int or None
            PK of the `retrieved` `FolderData` of the spin-up Wannier90
            calculation. Requires `wannier_folder_down` to also be given.
        wannier_folder_down : int or None
            PK of the `retrieved` `FolderData` of the spin-down Wannier90
            calculation. Requires `wannier_folder_up` to also be given.
        num_machines : int
            Number of machines to run on.
        num_mpiprocs_per_machine : int
            MPI processes per machine.
        label : str or None
            Optional label to set on the calcjob node.
        description : str or None
            Optional description to set on the calcjob node.

        Returns
        -------
        dict[str, Any]
            The process PK, uuid, label, description, code, input node PKs,
            and daemon state.
        """
        return submit_job(
            code=code,
            elements=elements,
            parameters=parameters,
            structure=structure,
            use_wannier_structure=use_wannier_structure,
            wannier_folder=wannier_folder,
            wannier_folder_up=wannier_folder_up,
            wannier_folder_down=wannier_folder_down,
            num_machines=num_machines,
            num_mpiprocs_per_machine=num_mpiprocs_per_machine,
            label=label,
            description=description,
        )

    if _wannier90_available():

        @mcp.tool()
        def describe_wannier_tb2j_workflow() -> dict[str, Any]:
            """Describe the Wannier90 -> TB2J workflow: outputs and exit codes.

            See `submit_wannier_tb2j_workflow`'s docstring for its actual arguments;
            its deeply nested, exposed input namespace is not usefully describable
            generically.

            Returns
            -------
            dict[str, Any]
                The workflow's outputs and exit codes.
            """
            return describe_workflow(WORKFLOW_ENTRY_POINT)

        @mcp.tool()
        def submit_wannier_tb2j_workflow(
            codes: dict[str, str | int],
            structure: FileInput,
            pseudo_family: str | None = None,
            protocol: str | None = None,
            spin_type: str = "collinear",
            electronic_type: str = "metal",
            projection_type: str = "analytic",
            wannier90_withmpi: bool = False,
            magnetic_elements: list[str] | None = None,
            tb2j_parameters: dict[str, Any] | None = None,
            tb2j_options: dict[str, Any] | None = None,
            label: str | None = None,
            description: str | None = None,
        ) -> dict[str, Any]:
            """Submit the full Wannier90 -> TB2J workflow to the daemon from a protocol.

            Runs Quantum ESPRESSO SCF/NSCF, Wannierisation, and TB2J in one pipeline.
            Magnetic elements and the Fermi energy are auto-detected unless given
            explicitly. Follow the job with `get_process` and `get_process_report`.

            Parameters
            ----------
            codes : dict[str, str or int]
                Code label or PK for each step, keyed by ``pw``, ``pw2wannier90``,
                ``wannier90``, ``tb2j``, and optionally ``projwfc``/``open_grid``. A
                ``tb2j`` entry is required.
            structure : FileInput
                The input structure, as a path, text, or PK of a `StructureData`,
                `MagneticStructureData`, or `SinglefileData` node (an ``MCIF`` file,
                parsed automatically).
            pseudo_family : str or None
                The pseudopotential family to use for the Wannier90/QE steps.
            protocol : str or None
                The protocol to use for the underlying Wannier90BandsWorkChain.
            spin_type : str
                One of ``none``, ``collinear``, ``non_collinear``, ``spin_orbit``.
            electronic_type : str
                One of ``metal``, ``insulator``, ``automatic``.
            projection_type : str
                One of ``analytic``, ``random``, ``scdm``, ``atomic_projectors_qe``.
            wannier90_withmpi : bool
                Whether to run ``wannier90.x`` under MPI. False by default, which
                also forces single-task resources for that step.
            magnetic_elements : list of str or None
                Elements for which the exchange interaction is considered. If not
                given, auto-detected from the resolved structure at runtime.
            tb2j_parameters : dict or None
                TB2J command-line parameters (the ``tb2j.parameters`` input).
                ``efermi`` is auto-filled from the Wannier90 SCF output if omitted.
            tb2j_options : dict or None
                ``metadata.options`` for the TB2J calculation step.
            label : str or None
                Optional label to set on the workflow node.
            description : str or None
                Optional description to set on the workflow node.

            Returns
            -------
            dict[str, Any]
                The process PK, uuid, label, description, the structure node's
                PK, and daemon state.
            """
            return submit_workflow_job(
                codes=codes,
                structure=structure,
                pseudo_family=pseudo_family,
                protocol=protocol,
                spin_type=spin_type,
                electronic_type=electronic_type,
                projection_type=projection_type,
                wannier90_withmpi=wannier90_withmpi,
                magnetic_elements=magnetic_elements,
                tb2j_parameters=tb2j_parameters,
                tb2j_options=tb2j_options,
                label=label,
                description=description,
            )
