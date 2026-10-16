"""Tests for the `WannierTB2JWorkChain`."""

import pytest
from aiida.orm import Dict, List

from aiida_cif2j.workflows.wannier import WannierTB2JWorkChain


def test_workchain_spec():
    """Regression test for the input/output wiring bugs fixed in this WorkChain.

    `tb2j_options` must not be a top-level input (it does not exist; `run_tb2j` used
    to reference it directly and crash), `tb2j.parameters` must not require 'efermi'
    up front (that conflicts with the auto-fill-from-SCF logic in `run_tb2j`), and
    the declared 'retrieved' output must actually be produced (see
    `test_collate_results_success`).
    """
    spec = WannierTB2JWorkChain.spec()

    assert "tb2j_options" not in spec.inputs
    assert "metadata" in spec.inputs["tb2j"]
    assert spec.inputs["tb2j"]["parameters"].validator is None
    assert spec.outputs["retrieved"].required


@pytest.mark.parametrize(
    "use_file, expected",
    [(True, True), (False, False)],
)
def test_should_parse_structure_from_file(
    generate_workchain_process,
    get_test_data_file,
    generate_structure,
    use_file,
    expected,
):
    """A file structure should trigger file parsing, a `StructureData` should not."""
    structure = get_test_data_file("nacl.cif") if use_file else generate_structure()
    process = generate_workchain_process(
        WannierTB2JWorkChain, inputs={"structure": structure}
    )

    assert process._should_parse_structure_from_file() is expected


@pytest.mark.parametrize(
    "given, expected",
    [(False, True), (True, False)],
)
def test_should_auto_detect_magnetic_elements(
    generate_workchain_process, generate_structure, given, expected
):
    """Auto-detection should only be requested when `magnetic_elements` is absent."""
    inputs = {"structure": generate_structure()}
    if given:
        inputs["magnetic_elements"] = List(["Fe"])
    process = generate_workchain_process(WannierTB2JWorkChain, inputs=inputs)

    assert process._should_auto_detect_magnetic_elements() is expected


def test_parse_structure_from_file(generate_workchain_process, get_test_data_file):
    """The CIF structure input should be parsed into `ctx.structure`."""
    from aiida_wannier90_workflows.data.structure import MagneticStructureData

    structure_file = get_test_data_file("nacl.cif")
    process = generate_workchain_process(
        WannierTB2JWorkChain, inputs={"structure": structure_file}
    )

    process.parse_structure_from_file()

    assert isinstance(process.ctx.structure, MagneticStructureData)
    assert {site.kind_name for site in process.ctx.structure.sites} == {"Na", "Cl"}


def test_auto_detect_magnetic_elements_wrong_type(
    generate_workchain_process, generate_structure
):
    """A plain `StructureData` cannot be auto-detected and should fail cleanly."""
    structure = generate_structure()
    process = generate_workchain_process(
        WannierTB2JWorkChain, inputs={"structure": structure}
    )

    result = process.auto_detect_magnetic_elements()

    assert result == WannierTB2JWorkChain.exit_codes.ERROR_MISSING_MAGNETIC_ELEMENTS


def test_auto_detect_magnetic_elements_found(
    generate_workchain_process, generate_magnetic_structure
):
    """A magnetic structure with a magnetic kind populates `ctx.magnetic_elements`."""
    structure = generate_magnetic_structure()
    process = generate_workchain_process(
        WannierTB2JWorkChain, inputs={"structure": structure}
    )

    result = process.auto_detect_magnetic_elements()

    assert result is None
    assert process.ctx.magnetic_elements.get_list() == ["Fe"]


def test_auto_detect_magnetic_elements_none_found(
    generate_workchain_process, generate_magnetic_structure
):
    """A magnetic structure with no magnetic kinds should fail with its exit code."""
    structure = generate_magnetic_structure(kinds=(("Na", None), ("Cl", None)))
    process = generate_workchain_process(
        WannierTB2JWorkChain, inputs={"structure": structure}
    )

    result = process.auto_detect_magnetic_elements()

    assert result == WannierTB2JWorkChain.exit_codes.ERROR_MISSING_MAGNETIC_ELEMENTS


def test_run_tb2j_wannier_failed(generate_workchain_process, generate_workchain_node):
    """A failed Wannier90BandsWorkChain should abort with `ERROR_WANNIER90_WC`."""
    wannier90_node = generate_workchain_node(exit_status=1)
    process = generate_workchain_process(
        WannierTB2JWorkChain, ctx={"wannier90": wannier90_node}
    )

    result = process.run_tb2j()

    assert result == WannierTB2JWorkChain.exit_codes.ERROR_WANNIER90_WC


def test_run_tb2j_missing_wannier_outputs(
    generate_workchain_process, generate_workchain_node, generate_structure
):
    """Neither 'wannier90' nor the up/down output pair should fail cleanly."""
    wannier90_node = generate_workchain_node(exit_status=0, outputs={})
    process = generate_workchain_process(
        WannierTB2JWorkChain,
        inputs={
            "structure": generate_structure(),
            "magnetic_elements": List(["Fe"]),
            "tb2j": {},
        },
        ctx={"wannier90": wannier90_node},
    )

    result = process.run_tb2j()

    assert result == WannierTB2JWorkChain.exit_codes.ERROR_MISSING_WANNIER_OUTPUTS


def test_run_tb2j_missing_efermi_no_scf(
    generate_workchain_process,
    generate_workchain_node,
    generate_structure,
    generate_folder_data,
):
    """Omitting 'efermi' with no SCF output to fall back on should fail cleanly."""
    retrieved = generate_folder_data(["aiida_tb.dat"])
    wannier90_node = generate_workchain_node(
        exit_status=0, outputs={"wannier90__retrieved": retrieved}
    )
    process = generate_workchain_process(
        WannierTB2JWorkChain,
        inputs={
            "structure": generate_structure(),
            "magnetic_elements": List(["Fe"]),
            "tb2j": {"parameters": Dict({})},
        },
        ctx={"wannier90": wannier90_node},
    )

    result = process.run_tb2j()

    assert result == WannierTB2JWorkChain.exit_codes.ERROR_MISSING_FERMI_ENERGY


def test_run_tb2j_missing_efermi_scf_without_fermi_energy(
    generate_workchain_process,
    generate_workchain_node,
    generate_structure,
    generate_folder_data,
):
    """An SCF output without a 'fermi_energy' key should also fail cleanly."""
    retrieved = generate_folder_data(["aiida_tb.dat"])
    scf_params = Dict({"some_other_key": 1.0})
    wannier90_node = generate_workchain_node(
        exit_status=0,
        outputs={
            "wannier90__retrieved": retrieved,
            "scf__output_parameters": scf_params,
        },
    )
    process = generate_workchain_process(
        WannierTB2JWorkChain,
        inputs={
            "structure": generate_structure(),
            "magnetic_elements": List(["Fe"]),
            "tb2j": {"parameters": Dict({})},
        },
        ctx={"wannier90": wannier90_node},
    )

    result = process.run_tb2j()

    assert result == WannierTB2JWorkChain.exit_codes.ERROR_MISSING_FERMI_ENERGY


def test_run_tb2j_efermi_autofilled_from_scf(
    generate_workchain_process,
    generate_workchain_node,
    generate_structure,
    generate_folder_data,
    wannier_tb2j_code,
):
    """A missing 'efermi' should be auto-filled from the SCF output pre-submission."""
    retrieved = generate_folder_data(["aiida_tb.dat"])
    scf_params = Dict({"fermi_energy": 7.5})
    wannier90_node = generate_workchain_node(
        exit_status=0,
        outputs={
            "wannier90__retrieved": retrieved,
            "scf__output_parameters": scf_params,
        },
    )
    process = generate_workchain_process(
        WannierTB2JWorkChain,
        inputs={
            "structure": generate_structure(),
            "magnetic_elements": List(["Fe"]),
            "tb2j": {"code": wannier_tb2j_code(), "parameters": Dict({})},
        },
        ctx={"wannier90": wannier90_node},
    )

    captured = {}

    def fake_submit(process_class, **kwargs):
        captured["process_class"] = process_class
        captured["inputs"] = kwargs
        return generate_workchain_node()

    process.submit = fake_submit
    result = process.run_tb2j()

    assert "tb2j_step" in result
    assert captured["process_class"].__name__ == "WannierTB2JCalculation"
    assert captured["inputs"]["parameters"].get_dict()["efermi"] == 7.5
    assert captured["inputs"]["wannier_folder"].pk == retrieved.pk


def test_run_tb2j_explicit_efermi_collinear(
    generate_workchain_process,
    generate_workchain_node,
    generate_structure,
    generate_folder_data,
    wannier_tb2j_code,
):
    """An explicit 'efermi' is kept as-is, and the up/down outputs should be used."""
    retrieved_up = generate_folder_data(["aiida_tb.dat"])
    retrieved_down = generate_folder_data(["aiida_tb.dat"])
    wannier90_node = generate_workchain_node(
        exit_status=0,
        outputs={
            "wannier90_up__retrieved": retrieved_up,
            "wannier90_down__retrieved": retrieved_down,
        },
    )
    process = generate_workchain_process(
        WannierTB2JWorkChain,
        inputs={
            "structure": generate_structure(),
            "magnetic_elements": List(["Fe"]),
            "tb2j": {"code": wannier_tb2j_code(), "parameters": Dict({"efermi": 1.23})},
        },
        ctx={"wannier90": wannier90_node},
    )

    captured = {}

    def fake_submit(process_class, **kwargs):
        captured["inputs"] = kwargs
        return generate_workchain_node()

    process.submit = fake_submit
    result = process.run_tb2j()

    assert "tb2j_step" in result
    assert captured["inputs"]["parameters"].get_dict()["efermi"] == 1.23
    assert captured["inputs"]["wannier_folder_up"].pk == retrieved_up.pk
    assert captured["inputs"]["wannier_folder_down"].pk == retrieved_down.pk


def test_collate_results_tb2j_failed(
    generate_workchain_process, generate_calc_job_node, generate_folder_data
):
    """A failed TB2J calculation should abort with `ERROR_TB2J_PLUGIN`."""
    from aiida_cif2j.calculations.wannier_tb2j import WannierTB2JCalculation

    retrieved = generate_folder_data(["TB2J.pickle"])
    tb2j_node = generate_calc_job_node(WannierTB2JCalculation, retrieved, exit_status=1)
    process = generate_workchain_process(
        WannierTB2JWorkChain, ctx={"tb2j_step": tb2j_node}
    )

    result = process.collate_results()

    assert result == WannierTB2JWorkChain.exit_codes.ERROR_TB2J_PLUGIN


def test_collate_results_success(
    generate_workchain_process, generate_calc_job_node, generate_folder_data
):
    """A successful TB2J calculation should produce 'retrieved' and finish ok."""
    from aiida.engine import ExitCode

    from aiida_cif2j.calculations.wannier_tb2j import WannierTB2JCalculation

    retrieved = generate_folder_data(["TB2J.pickle"])
    tb2j_node = generate_calc_job_node(WannierTB2JCalculation, retrieved, exit_status=0)
    process = generate_workchain_process(
        WannierTB2JWorkChain, ctx={"tb2j_step": tb2j_node}
    )

    result = process.collate_results()

    assert result == ExitCode(0)
    assert process._outputs["retrieved"].pk == retrieved.pk
