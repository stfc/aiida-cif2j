"""PyTest configurations."""

import io
import pathlib

import pytest
from aiida.common import AttributeDict
from aiida.common.folders import Folder
from aiida.common.links import LinkType
from aiida.engine import CalcJob, ProcessState, WorkChain
from aiida.engine.utils import instantiate_process
from aiida.manage.manager import get_manager
from aiida.orm import (
    CalcJobNode,
    Data,
    Dict,
    FolderData,
    InstalledCode,
    KpointsData,
    List,
    SinglefileData,
    StructureData,
    WorkChainNode,
)
from aiida_wannier90_workflows.data.structure import MagneticStructureData
from aiida_wannier90_workflows.workflows.bands import Wannier90BandsWorkChain

pytest_plugins = "aiida.tools.pytest_fixtures"


@pytest.fixture
def get_data_filepath() -> pathlib.Path:
    """Return the path to the tests data folder."""
    return pathlib.Path(__file__).resolve().parent / "data"


@pytest.fixture
def get_test_data_file(get_data_filepath):
    """Return a factory for a `SinglefileData` node from a file in the data folder."""

    def factory(fname: str) -> SinglefileData:
        return SinglefileData(file=str(get_data_filepath / fname))

    return factory


@pytest.fixture
def generate_magnetic_structure():
    """Return a factory to build a `MagneticStructureData` node with explicit magmom."""

    def factory(
        kinds: tuple[tuple[str, tuple[float, float, float] | None], ...] = (
            ("Fe", (0.0, 0.0, 2.0)),
            ("O", (0.0, 0.0, 0.0)),
        ),
        cell=((4.0, 0.0, 0.0), (0.0, 4.0, 0.0), (0.0, 0.0, 4.0)),
    ) -> MagneticStructureData:
        structure = MagneticStructureData(cell=cell, pbc=(True, True, True))
        for index, (symbol, magmom) in enumerate(kinds):
            structure.append_atom(
                position=(float(index), 0.0, 0.0),
                symbols=symbol,
                name=f"{symbol}{index}",
                magmom=magmom,
            )
        return structure

    return factory


@pytest.fixture
def generate_structure():
    """Return a factory to build a simple `StructureData` node."""

    def factory(
        cell=((2.87, 0.0, 0.0), (0.0, 2.87, 0.0), (0.0, 0.0, 2.87)),
        pbc=(True, True, True),
        symbol="Fe",
    ) -> StructureData:
        structure = StructureData(cell=cell, pbc=pbc)
        structure.append_atom(position=(0.0, 0.0, 0.0), symbols=symbol)
        return structure

    return factory


@pytest.fixture
def generate_folder_data():
    """Return a factory to build a `FolderData` node of given, empty files."""

    def factory(filenames: list[str]) -> FolderData:
        folder_data = FolderData()
        for filename in filenames:
            folder_data.put_object_from_filelike(io.BytesIO(b""), filename)
        return folder_data

    return factory


@pytest.fixture
def wannier_tb2j_code(aiida_code_installed):
    """Return a factory for an `InstalledCode` for the `WannierTB2JCalculation`."""

    def factory() -> InstalledCode:
        return aiida_code_installed(
            filepath_executable="wann2J.py",
            default_calc_job_plugin="cif2j.wannier_tb2j",
        )

    return factory


@pytest.fixture
def generate_inputs(wannier_tb2j_code, generate_structure, generate_folder_data):
    """Return a factory for a dictionary of inputs for the `WannierTB2JCalculation`."""

    def factory(
        spinor: bool = True,
        elements: tuple[str, ...] = ("Fe",),
        parameters: dict | None = None,
        structure: StructureData | None = None,
        wannier_files: tuple[str, ...] = ("aiida_tb.dat",),
    ) -> dict:
        parameters = {"efermi": 0.0} if parameters is None else parameters
        inputs = {
            "code": wannier_tb2j_code(),
            "elements": List(list(elements)),
            "parameters": Dict(parameters),
            "structure": structure if structure is not None else generate_structure(),
        }
        if spinor:
            inputs["wannier_folder"] = generate_folder_data(list(wannier_files))
        else:
            inputs["wannier_folder_up"] = generate_folder_data(list(wannier_files))
            inputs["wannier_folder_down"] = generate_folder_data(list(wannier_files))
        return inputs

    return factory


@pytest.fixture
def generate_calcjob(tmp_path, generate_inputs):
    """Return a factory to instantiate a `CalcJob` and run `prepare_for_submission`."""

    def factory(
        process_class: CalcJob, inputs: dict | None = None, return_process: bool = False
    ):
        inputs = generate_inputs() if inputs is None else inputs
        manager = get_manager()
        runner = manager.get_runner()
        process = instantiate_process(runner, process_class, **inputs)

        if return_process:
            return process

        calc_info = process.prepare_for_submission(Folder(tmp_path))
        return tmp_path, calc_info

    return factory


@pytest.fixture
def generate_calc_job_node(aiida_localhost):
    """Return a factory to build a `CalcJobNode` with a `retrieved` output node."""

    def factory(
        process_class: type[CalcJob], retrieved: FolderData, exit_status: int = 0
    ) -> CalcJobNode:
        process_type = f"{process_class.__module__}.{process_class.__name__}"
        node = CalcJobNode(computer=aiida_localhost, process_type=process_type)
        node.set_option("resources", {"num_machines": 1, "num_mpiprocs_per_machine": 1})
        node.set_process_state(ProcessState.FINISHED)
        node.set_exit_status(exit_status)
        node.store()

        retrieved.base.links.add_incoming(
            node, link_type=LinkType.CREATE, link_label="retrieved"
        )
        retrieved.store()

        return node

    return factory


@pytest.fixture
def generate_workchain_node():
    """Return a factory to build a finished `WorkChainNode` with RETURN output links."""

    def factory(
        exit_status: int = 0, outputs: dict[str, Data] | None = None
    ) -> WorkChainNode:
        node = WorkChainNode()
        node.set_process_state(ProcessState.FINISHED)
        node.set_exit_status(exit_status)
        node.store()

        for link_label, output_node in (outputs or {}).items():
            output_node.store()
            output_node.base.links.add_incoming(
                node, link_type=LinkType.RETURN, link_label=link_label
            )

        return node

    return factory


@pytest.fixture
def generate_workchain_process():
    """Return a factory to build a bare `WorkChain` instance to unit-test step methods.

    This bypasses `Process.__init__`/`on_create`, avoiding the need to satisfy the full
    input specification of the `WorkChain` (which may expose inputs from other, heavier
    processes). Only the private attributes touched by `self.inputs`, `self.ctx`,
    `self.out` and `self.report` are set up; `self.submit` is not usable on the result.
    """

    def factory(
        process_class: type[WorkChain],
        inputs: dict | None = None,
        ctx: dict | None = None,
    ) -> WorkChain:
        from plumpy.event_helper import EventHelper
        from plumpy.process_listener import ProcessListener

        process = object.__new__(process_class)
        process._parsed_inputs = AttributeDict(inputs or {})
        process._context = AttributeDict(ctx or {})
        process._outputs = {}
        process._logger = None
        process._event_helper = EventHelper(ProcessListener)
        process._node = WorkChainNode()
        process._node.store()
        return process

    return factory


@pytest.fixture
def generate_wannier_bands_builder(aiida_code_installed):
    """Return a factory for a cheaply-populated, structurally valid builder.

    Stands in for what `Wannier90BandsWorkChain.get_builder_from_protocol` would
    return, without needing a real registered pseudopotential family.
    """

    def factory(structure: StructureData, with_nscf: bool = True):
        pw_code = aiida_code_installed(default_calc_job_plugin="quantumespresso.pw")
        w90_code = aiida_code_installed(default_calc_job_plugin="wannier90.wannier90")

        builder = Wannier90BandsWorkChain.get_builder()
        builder.structure = structure
        builder.scf.pw.code = pw_code
        builder.scf.pw.parameters = Dict({"SYSTEM": {}})
        builder.scf.pw.metadata.options.resources = {"num_machines": 1}
        if with_nscf:
            builder.nscf.pw.code = pw_code
            builder.nscf.pw.parameters = Dict({"SYSTEM": {}})
            builder.nscf.pw.metadata.options.resources = {"num_machines": 1}
        builder.wannier90.wannier90.code = w90_code
        builder.wannier90.wannier90.parameters = Dict({})
        builder.wannier90.wannier90.kpoints = KpointsData()
        builder.wannier90.wannier90.metadata.options.resources = {"num_machines": 1}
        builder.wannier90.wannier90.metadata.options.withmpi = True
        return builder

    return factory
