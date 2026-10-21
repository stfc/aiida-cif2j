"""Tests for the `WannierTB2JWorkChain`."""

from unittest.mock import patch

import pytest
from aiida.orm import Dict, List
from aiida_quantumespresso.common.types import ElectronicType, SpinType
from aiida_wannier90_workflows.data.structure import MagneticStructureData
from aiida_wannier90_workflows.workflows.bands import Wannier90BandsWorkChain

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


def test_get_builder_from_protocol_missing_tb2j_code(generate_structure):
    """A `codes` mapping without a 'tb2j' entry should be rejected up front."""
    with pytest.raises(ValueError, match="tb2j"):
        WannierTB2JWorkChain.get_builder_from_protocol(
            codes={"pw": "x"}, structure=generate_structure(), pseudo_family="x"
        )


def test_get_builder_from_protocol_plain_structure_collinear_raises(
    generate_structure, wannier_tb2j_code
):
    """A plain `StructureData` under the default collinear spin type must be rejected.

    `collinear_magnetic_moments` can't read per-kind moments off a plain
    `StructureData` (it isn't `MagneticStructureData`), so this must raise rather than
    silently build a non-magnetic SCF.
    """
    with pytest.raises(TypeError, match="MagneticStructureData"):
        WannierTB2JWorkChain.get_builder_from_protocol(
            codes={"pw": "x", "tb2j": wannier_tb2j_code()},
            structure=generate_structure(),
            pseudo_family="x",
        )


def test_get_builder_from_protocol_plain_structure_with_explicit_moments(
    generate_wannier_bands_builder, generate_structure, wannier_tb2j_code
):
    """An explicit `initial_magnetic_moments` bypasses the MagneticStructureData need.

    `collinear_magnetic_moments` is simply never called in that case.
    """
    structure = generate_structure()
    fake_builder = generate_wannier_bands_builder(structure)
    custom_moments = {"Fe": 2.2}

    with patch.object(
        Wannier90BandsWorkChain, "get_builder_from_protocol", return_value=fake_builder
    ) as mock:
        WannierTB2JWorkChain.get_builder_from_protocol(
            codes={"pw": "x", "tb2j": wannier_tb2j_code()},
            structure=structure,
            pseudo_family="x",
            initial_magnetic_moments=custom_moments,
        )

    assert mock.call_args.kwargs["initial_magnetic_moments"] == custom_moments


def test_get_builder_from_protocol_parses_file_structure(
    generate_wannier_bands_builder,
    generate_structure,
    get_test_data_file,
    wannier_tb2j_code,
):
    """A `SinglefileData` structure should be parsed before reaching the builder."""
    fake_builder = generate_wannier_bands_builder(generate_structure())

    with patch.object(
        Wannier90BandsWorkChain, "get_builder_from_protocol", return_value=fake_builder
    ) as mock:
        builder = WannierTB2JWorkChain.get_builder_from_protocol(
            codes={"pw": "x", "tb2j": wannier_tb2j_code()},
            structure=get_test_data_file("nacl.cif"),
            pseudo_family="x",
        )

    passed_structure = mock.call_args.kwargs["structure"]
    assert isinstance(passed_structure, MagneticStructureData)
    assert builder.structure.pk == passed_structure.pk


def test_get_builder_from_protocol_structure_passthrough(
    generate_wannier_bands_builder, generate_structure, wannier_tb2j_code
):
    """An already-built structure should be forwarded unchanged, no calcfunction run."""
    structure = generate_structure()
    fake_builder = generate_wannier_bands_builder(structure)

    with patch.object(
        Wannier90BandsWorkChain, "get_builder_from_protocol", return_value=fake_builder
    ) as mock:
        WannierTB2JWorkChain.get_builder_from_protocol(
            codes={"pw": "x", "tb2j": wannier_tb2j_code()},
            structure=structure,
            pseudo_family="x",
            spin_type=SpinType.NONE,
        )

    assert mock.call_args.kwargs["structure"] is structure


def test_get_builder_from_protocol_collinear_moments_autofilled(
    generate_wannier_bands_builder, generate_magnetic_structure, wannier_tb2j_code
):
    """Default `SpinType.COLLINEAR` should auto-fill `initial_magnetic_moments`."""
    structure = generate_magnetic_structure()
    fake_builder = generate_wannier_bands_builder(structure)

    with patch.object(
        Wannier90BandsWorkChain, "get_builder_from_protocol", return_value=fake_builder
    ) as mock:
        WannierTB2JWorkChain.get_builder_from_protocol(
            codes={"pw": "x", "tb2j": wannier_tb2j_code()},
            structure=structure,
            pseudo_family="x",
        )

    assert mock.call_args.kwargs["initial_magnetic_moments"] == {"Fe0": 2.0, "O1": 0.0}


def test_get_builder_from_protocol_explicit_moments_not_overwritten(
    generate_wannier_bands_builder, generate_magnetic_structure, wannier_tb2j_code
):
    """Caller-supplied `initial_magnetic_moments` should be forwarded verbatim."""
    structure = generate_magnetic_structure()
    fake_builder = generate_wannier_bands_builder(structure)
    custom_moments = {"Fe0": 5.0, "O1": 0.0}

    with patch.object(
        Wannier90BandsWorkChain, "get_builder_from_protocol", return_value=fake_builder
    ) as mock:
        WannierTB2JWorkChain.get_builder_from_protocol(
            codes={"pw": "x", "tb2j": wannier_tb2j_code()},
            structure=structure,
            pseudo_family="x",
            initial_magnetic_moments=custom_moments,
        )

    assert mock.call_args.kwargs["initial_magnetic_moments"] == custom_moments


def test_get_builder_from_protocol_merge_and_withmpi(
    generate_wannier_bands_builder, generate_structure, wannier_tb2j_code
):
    """The Wannier90 builder's values survive the merge; withmpi is forced off."""
    structure = generate_structure()
    fake_builder = generate_wannier_bands_builder(structure)
    tb2j_code = wannier_tb2j_code()

    with patch.object(
        Wannier90BandsWorkChain, "get_builder_from_protocol", return_value=fake_builder
    ):
        builder = WannierTB2JWorkChain.get_builder_from_protocol(
            codes={"pw": "x", "tb2j": tb2j_code},
            structure=structure,
            pseudo_family="x",
            spin_type=SpinType.NONE,
        )

    assert builder.tb2j.code.pk == tb2j_code.pk
    assert builder.scf.pw.code.pk == fake_builder.scf.pw.code.pk
    assert (
        builder.wannier90.wannier90.code.pk == fake_builder.wannier90.wannier90.code.pk
    )
    assert builder.wannier90.wannier90.metadata.options.withmpi is False
    assert builder.wannier90.wannier90.metadata.options.resources == {
        "num_machines": 1,
        "num_mpiprocs_per_machine": 1,
    }


def test_get_builder_from_protocol_wannier90_withmpi_true(
    generate_wannier_bands_builder, generate_structure, wannier_tb2j_code
):
    """Explicitly requesting `wannier90_withmpi=True` leaves resources untouched."""
    structure = generate_structure()
    fake_builder = generate_wannier_bands_builder(structure)
    original_resources = dict(
        fake_builder.wannier90.wannier90.metadata.options.resources
    )

    with patch.object(
        Wannier90BandsWorkChain, "get_builder_from_protocol", return_value=fake_builder
    ):
        builder = WannierTB2JWorkChain.get_builder_from_protocol(
            codes={"pw": "x", "tb2j": wannier_tb2j_code()},
            structure=structure,
            pseudo_family="x",
            spin_type=SpinType.NONE,
            wannier90_withmpi=True,
        )

    assert builder.wannier90.wannier90.metadata.options.withmpi is True
    assert builder.wannier90.wannier90.metadata.options.resources == original_resources


def test_get_builder_from_protocol_tot_magnetization(
    generate_wannier_bands_builder, generate_magnetic_structure, wannier_tb2j_code
):
    """Insulator + collinear should inject the net `tot_magnetization` into scf/nscf."""
    structure = generate_magnetic_structure(
        kinds=(("Mn", (0.0, 0.0, 4.6)), ("Mn", (0.0, 0.0, -4.6)))
    )
    fake_builder = generate_wannier_bands_builder(structure)

    with patch.object(
        Wannier90BandsWorkChain, "get_builder_from_protocol", return_value=fake_builder
    ):
        builder = WannierTB2JWorkChain.get_builder_from_protocol(
            codes={"pw": "x", "tb2j": wannier_tb2j_code()},
            structure=structure,
            pseudo_family="x",
            electronic_type=ElectronicType.INSULATOR,
            spin_type=SpinType.COLLINEAR,
        )

    assert builder.scf.pw.parameters.get_dict()["SYSTEM"]["tot_magnetization"] == 0.0
    assert builder.nscf.pw.parameters.get_dict()["SYSTEM"]["tot_magnetization"] == 0.0


def test_get_builder_from_protocol_tot_magnetization_skips_absent_nscf(
    generate_wannier_bands_builder, generate_magnetic_structure, wannier_tb2j_code
):
    """The tot_magnetization fixup must not crash when 'nscf' was never configured."""
    structure = generate_magnetic_structure(
        kinds=(("Mn", (0.0, 0.0, 4.6)), ("Mn", (0.0, 0.0, -4.6)))
    )
    fake_builder = generate_wannier_bands_builder(structure, with_nscf=False)

    with patch.object(
        Wannier90BandsWorkChain, "get_builder_from_protocol", return_value=fake_builder
    ):
        builder = WannierTB2JWorkChain.get_builder_from_protocol(
            codes={"pw": "x", "tb2j": wannier_tb2j_code()},
            structure=structure,
            pseudo_family="x",
            electronic_type=ElectronicType.INSULATOR,
            spin_type=SpinType.COLLINEAR,
        )

    assert builder.scf.pw.parameters.get_dict()["SYSTEM"]["tot_magnetization"] == 0.0
    assert builder.nscf.pw.parameters is None


@pytest.mark.parametrize("spin_type", [SpinType.NONE, SpinType.NON_COLLINEAR])
def test_get_builder_from_protocol_tot_magnetization_not_applied(
    generate_wannier_bands_builder, generate_structure, wannier_tb2j_code, spin_type
):
    """The tot_magnetization fixup must only fire for insulator + collinear."""
    structure = generate_structure()
    fake_builder = generate_wannier_bands_builder(structure)

    with patch.object(
        Wannier90BandsWorkChain, "get_builder_from_protocol", return_value=fake_builder
    ):
        builder = WannierTB2JWorkChain.get_builder_from_protocol(
            codes={"pw": "x", "tb2j": wannier_tb2j_code()},
            structure=structure,
            pseudo_family="x",
            electronic_type=ElectronicType.INSULATOR,
            spin_type=spin_type,
        )

    assert "tot_magnetization" not in builder.scf.pw.parameters.get_dict().get(
        "SYSTEM", {}
    )


def test_get_builder_from_protocol_tb2j_options_and_parameters(
    generate_wannier_bands_builder, generate_structure, wannier_tb2j_code
):
    """`tb2j_parameters`/`tb2j_options`, when given, should be set on the builder."""
    structure = generate_structure()
    fake_builder = generate_wannier_bands_builder(structure)

    with patch.object(
        Wannier90BandsWorkChain, "get_builder_from_protocol", return_value=fake_builder
    ):
        builder = WannierTB2JWorkChain.get_builder_from_protocol(
            codes={"pw": "x", "tb2j": wannier_tb2j_code()},
            structure=structure,
            pseudo_family="x",
            spin_type=SpinType.NONE,
            tb2j_parameters={"efermi": 1.0},
            tb2j_options={"resources": {"num_machines": 2}},
        )

    assert builder.tb2j.parameters.get_dict() == {"efermi": 1.0}
    assert builder.tb2j.metadata.options.resources == {"num_machines": 2}


def test_get_builder_from_protocol_tb2j_options_omitted(
    generate_wannier_bands_builder, generate_structure, wannier_tb2j_code
):
    """Omitting `tb2j_options` leaves `WannierTB2JCalculation`'s own defaults intact."""
    structure = generate_structure()
    fake_builder = generate_wannier_bands_builder(structure)

    with patch.object(
        Wannier90BandsWorkChain, "get_builder_from_protocol", return_value=fake_builder
    ):
        builder = WannierTB2JWorkChain.get_builder_from_protocol(
            codes={"pw": "x", "tb2j": wannier_tb2j_code()},
            structure=structure,
            pseudo_family="x",
            spin_type=SpinType.NONE,
        )

    assert "resources" not in dict(builder.tb2j.metadata.options)
    assert "parser_name" not in dict(builder.tb2j.metadata.options)


def test_get_builder_from_protocol_magnetic_elements(
    generate_wannier_bands_builder, generate_structure, wannier_tb2j_code
):
    """Given `magnetic_elements` should be set on the builder as a `List`."""
    structure = generate_structure()
    fake_builder = generate_wannier_bands_builder(structure)

    with patch.object(
        Wannier90BandsWorkChain, "get_builder_from_protocol", return_value=fake_builder
    ):
        builder = WannierTB2JWorkChain.get_builder_from_protocol(
            codes={"pw": "x", "tb2j": wannier_tb2j_code()},
            structure=structure,
            pseudo_family="x",
            spin_type=SpinType.NONE,
            magnetic_elements=["Fe"],
        )

    assert builder.magnetic_elements.get_list() == ["Fe"]


def test_get_builder_from_protocol_cross_computer_warns(
    generate_wannier_bands_builder,
    generate_structure,
    wannier_tb2j_code,
    aiida_code_installed,
    aiida_computer,
    caplog,
):
    """`pw2wannier90` and `wannier90` on different computers should log a warning.

    AiiDA cannot copy files directly between two different remote machines, so
    `wannier90.x` must run on the same computer as the preceding `pw2wannier90.x`
    step; otherwise the eventual `Wannier90Calculation` hangs and fails at runtime.
    """
    structure = generate_structure()
    fake_builder = generate_wannier_bands_builder(structure)
    remote_computer = aiida_computer(label="remote", hostname="remote.example.com")
    fake_builder.pw2wannier90.pw2wannier90.code = aiida_code_installed(
        default_calc_job_plugin="quantumespresso.pw2wannier90", computer=remote_computer
    )

    with patch.object(
        Wannier90BandsWorkChain, "get_builder_from_protocol", return_value=fake_builder
    ):
        WannierTB2JWorkChain.get_builder_from_protocol(
            codes={"pw": "x", "tb2j": wannier_tb2j_code()},
            structure=structure,
            pseudo_family="x",
            spin_type=SpinType.NONE,
        )

    assert any(
        record.levelname == "WARNING" and "different computers" in record.message
        for record in caplog.records
    )


def test_get_builder_from_protocol_same_computer_no_warning(
    generate_wannier_bands_builder,
    generate_structure,
    wannier_tb2j_code,
    aiida_code_installed,
    caplog,
):
    """`pw2wannier90` and `wannier90` on the same computer should not warn."""
    structure = generate_structure()
    fake_builder = generate_wannier_bands_builder(structure)
    fake_builder.pw2wannier90.pw2wannier90.code = aiida_code_installed(
        default_calc_job_plugin="quantumespresso.pw2wannier90"
    )

    with patch.object(
        Wannier90BandsWorkChain, "get_builder_from_protocol", return_value=fake_builder
    ):
        WannierTB2JWorkChain.get_builder_from_protocol(
            codes={"pw": "x", "tb2j": wannier_tb2j_code()},
            structure=structure,
            pseudo_family="x",
            spin_type=SpinType.NONE,
        )

    assert not any(record.levelname == "WARNING" for record in caplog.records)


def test_get_builder_from_protocol_magnetic_elements_omitted(
    generate_wannier_bands_builder, generate_structure, wannier_tb2j_code
):
    """Omitting `magnetic_elements` preserves the WorkChain's own auto-detection."""
    structure = generate_structure()
    fake_builder = generate_wannier_bands_builder(structure)

    with patch.object(
        Wannier90BandsWorkChain, "get_builder_from_protocol", return_value=fake_builder
    ):
        builder = WannierTB2JWorkChain.get_builder_from_protocol(
            codes={"pw": "x", "tb2j": wannier_tb2j_code()},
            structure=structure,
            pseudo_family="x",
            spin_type=SpinType.NONE,
        )

    assert "magnetic_elements" not in builder._data
