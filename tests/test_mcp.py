"""Tests for the aiida-mcp integration module, aiida_cif2j.mcp.

Requires the optional ``mcp`` extra (``pip install -e .[mcp]``), which installs
aiida-mcp and the ``mcp`` SDK; skipped entirely if that extra is not installed (e.g.
in CI jobs that only install the base package).
"""

import asyncio
from unittest import mock

import pytest

pytest.importorskip("aiida_mcp")

from aiida import orm  # noqa: E402
from aiida_mcp.plugins import calcjob, workflow  # noqa: E402
from aiida_mcp.plugins.inputs import ControlInput, FileInput  # noqa: E402
from aiida_wannier90_workflows.workflows.bands import (  # noqa: E402
    Wannier90BandsWorkChain,
)
from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from aiida_cif2j import mcp as cif2j_mcp  # noqa: E402


def _tool_names(server: MCPServer) -> set[str]:
    return {tool.name for tool in asyncio.run(server.list_tools())}


def test_is_available():
    """is_available reflects whether the calcjob entry point is installed."""
    assert cif2j_mcp.is_available() is True


def test_wannier90_available():
    """_wannier90_available is True when aiida-wannier90-workflows is installed."""
    assert cif2j_mcp._wannier90_available() is True


def test_describe_cif2j_calcjob_inputs():
    """describe_calcjob reports the WannierTB2J-specific inputs."""
    description = calcjob.describe_calcjob("cif2j.wannier_tb2j")
    inputs = {port["name"]: port for port in description["inputs"]}

    assert inputs["elements"]["required"] is True
    assert inputs["wannier_folder"]["types"] == ["FolderData"]
    assert inputs["code"]["required"] is False


def test_describe_wannier_tb2j_workflow_outputs():
    """describe_workflow reports the workflow's outputs, not its exposed inputs."""
    description = workflow.describe_workflow("cif2j.wannier_tb2j")
    outputs = {port["name"]: port for port in description["outputs"]}

    assert "exchange_couplings" in outputs
    assert outputs["exchange_couplings"]["required"] is True
    assert outputs["dmi_vectors"]["required"] is False


def test_register_adds_calcjob_and_workflow_tools():
    """register() adds both the calcjob and (when available) the workflow tools."""
    server = MCPServer("test")
    cif2j_mcp.register(server)
    assert _tool_names(server) == {
        "describe_cif2j_calcjob",
        "submit_cif2j_job",
        "describe_wannier_tb2j_workflow",
        "submit_wannier_tb2j_workflow",
    }


def test_register_skips_workflow_tools_when_wannier90_unavailable(monkeypatch):
    """register() registers only the calcjob tools if wannier90 deps are missing."""
    monkeypatch.setattr(cif2j_mcp, "_wannier90_available", lambda: False)
    server = MCPServer("test")
    cif2j_mcp.register(server)
    assert _tool_names(server) == {"describe_cif2j_calcjob", "submit_cif2j_job"}


# --- calcjob submission ---


@pytest.fixture
def fake_submit():
    """Replace the daemon submit with a stub that returns a process-like node."""
    node = orm.CalcJobNode()
    node.set_process_type("aiida.calculations:cif2j.wannier_tb2j")
    with mock.patch.object(calcjob, "submit", return_value=node) as patched:
        node.store_all = lambda: None
        yield patched


@pytest.fixture
def stored_node_returned(fake_submit):
    """Make the fake submit return an already-stored CalcJobNode."""
    fake_submit.return_value = orm.CalcJobNode().store()
    return fake_submit


def test_submit_cif2j_job_builds_validated_inputs(
    wannier_tb2j_code, generate_structure, generate_folder_data, stored_node_returned
):
    """submit_job builds, stores and submits the required inputs."""
    structure = generate_structure().store()
    folder = generate_folder_data(["aiida_tb.dat"]).store()
    code = wannier_tb2j_code()

    result = cif2j_mcp.submit_job(
        code=code.pk,
        elements=["Fe"],
        parameters=ControlInput(parameters={"efermi": 0.0}),
        structure=FileInput(pk=structure.pk),
        wannier_folder=folder.pk,
    )

    stored_node_returned.assert_called_once()
    submitted = stored_node_returned.call_args.kwargs
    assert submitted["code"].pk == code.pk
    assert submitted["elements"].get_list() == ["Fe"]
    assert isinstance(submitted["parameters"], orm.Dict)
    assert submitted["wannier_folder"].pk == folder.pk

    assert result["pk"] == stored_node_returned.return_value.pk
    expected_inputs = {"elements", "parameters", "structure", "wannier_folder"}
    assert set(result["inputs"]) == expected_inputs
    assert result["code"] == code.full_label


def test_submit_cif2j_job_rejects_bad_resources(wannier_tb2j_code, fake_submit):
    """A resources value below 1 is a ToolError."""
    with pytest.raises(ToolError, match="num_machines must be at least 1"):
        cif2j_mcp.submit_job(
            code=wannier_tb2j_code().pk,
            elements=["Fe"],
            parameters=ControlInput(parameters={"efermi": 0.0}),
            num_machines=0,
        )
    fake_submit.assert_not_called()


def test_submit_cif2j_job_unknown_wannier_folder_pk(wannier_tb2j_code, fake_submit):
    """A wannier_folder PK that doesn't exist is a ToolError."""
    with pytest.raises(ToolError, match="no node with pk 999999"):
        cif2j_mcp.submit_job(
            code=wannier_tb2j_code().pk,
            elements=["Fe"],
            parameters=ControlInput(parameters={"efermi": 0.0}),
            wannier_folder=999999,
        )
    fake_submit.assert_not_called()


def test_submit_cif2j_job_wannier_folder_wrong_type(wannier_tb2j_code, fake_submit):
    """A wannier_folder PK that isn't a FolderData is a ToolError."""
    wrong = orm.Int(1).store()
    with pytest.raises(ToolError, match="expected FolderData"):
        cif2j_mcp.submit_job(
            code=wannier_tb2j_code().pk,
            elements=["Fe"],
            parameters=ControlInput(parameters={"efermi": 0.0}),
            wannier_folder=wrong.pk,
        )
    fake_submit.assert_not_called()


def test_submit_cif2j_job_tool_is_registered_with_input_schema():
    """submit_cif2j_job is registered with the expected input schema."""
    server = MCPServer("test")
    cif2j_mcp.register(server)
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}

    schema = tools["submit_cif2j_job"].input_schema
    assert set(schema["required"]) == {"code", "elements", "parameters"}


# --- workflow submission ---


@pytest.fixture
def fake_workflow_submit():
    """Replace aiida.engine.submit, as imported into aiida_cif2j.mcp, with a stub."""
    node = orm.WorkChainNode()
    node.set_process_type("aiida.workflows:cif2j.wannier_tb2j")
    with mock.patch.object(cif2j_mcp, "submit", return_value=node) as patched:
        node.store_all = lambda: None
        yield patched


@pytest.fixture
def stored_workflow_node_returned(fake_workflow_submit):
    """Make the fake submit return an already-stored WorkChainNode."""
    fake_workflow_submit.return_value = orm.WorkChainNode().store()
    return fake_workflow_submit


def test_submit_wannier_tb2j_workflow_builds_from_protocol(
    generate_wannier_bands_builder,
    generate_magnetic_structure,
    wannier_tb2j_code,
    stored_workflow_node_returned,
):
    """submit_workflow_job builds via get_builder_from_protocol and submits it."""
    structure = generate_magnetic_structure().store()
    fake_builder = generate_wannier_bands_builder(structure)
    tb2j_code = wannier_tb2j_code()

    with mock.patch.object(
        Wannier90BandsWorkChain, "get_builder_from_protocol", return_value=fake_builder
    ):
        result = cif2j_mcp.submit_workflow_job(
            codes={"pw": "x", "tb2j": tb2j_code.pk},
            structure=FileInput(pk=structure.pk),
            pseudo_family="x",
            label="my run",
        )

    stored_workflow_node_returned.assert_called_once()
    submitted_builder = stored_workflow_node_returned.call_args.args[0]
    assert submitted_builder.metadata.label == "my run"
    assert result["pk"] == stored_workflow_node_returned.return_value.pk
    assert result["structure"] == structure.pk


def test_submit_wannier_tb2j_workflow_missing_tb2j_code(
    generate_structure, fake_workflow_submit
):
    """A codes mapping without a 'tb2j' entry is a ToolError."""
    with pytest.raises(ToolError, match="tb2j"):
        cif2j_mcp.submit_workflow_job(
            codes={"pw": "x"},
            structure=FileInput(pk=generate_structure().store().pk),
            pseudo_family="x",
        )
    fake_workflow_submit.assert_not_called()


def test_submit_wannier_tb2j_workflow_plain_structure_collinear_is_tool_error(
    generate_structure, wannier_tb2j_code, fake_workflow_submit
):
    """A plain StructureData under the default collinear spin type is a ToolError."""
    with pytest.raises(ToolError, match="MagneticStructureData"):
        cif2j_mcp.submit_workflow_job(
            codes={"pw": "x", "tb2j": wannier_tb2j_code().pk},
            structure=FileInput(pk=generate_structure().store().pk),
            pseudo_family="x",
        )
    fake_workflow_submit.assert_not_called()


def test_submit_wannier_tb2j_workflow_unknown_spin_type(
    generate_structure, wannier_tb2j_code, fake_workflow_submit
):
    """An unrecognised spin_type is a ToolError."""
    with pytest.raises(ToolError, match="choose one of"):
        cif2j_mcp.submit_workflow_job(
            codes={"pw": "x", "tb2j": wannier_tb2j_code().pk},
            structure=FileInput(pk=generate_structure().store().pk),
            pseudo_family="x",
            spin_type="not-a-real-spin-type",
        )
    fake_workflow_submit.assert_not_called()


def test_submit_wannier_tb2j_workflow_tool_is_registered_with_input_schema():
    """submit_wannier_tb2j_workflow is registered with the expected input schema."""
    server = MCPServer("test")
    cif2j_mcp.register(server)
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}

    schema = tools["submit_wannier_tb2j_workflow"].input_schema
    assert set(schema["required"]) == {"codes", "structure"}
