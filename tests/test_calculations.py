"""Tests for the `WannierTB2JCalculation` CalcJob."""

import pytest
from aiida.common import InputValidationError

from aiida_cif2j.calculations.wannier_tb2j import WannierTB2JCalculation


def test_spinor_defaults(generate_calcjob):
    """Test the command line and file lists for a default spinor calculation."""
    _, calc_info = generate_calcjob(WannierTB2JCalculation)

    assert calc_info.retrieve_list == ["TB2J.pickle"]
    assert calc_info.codes_info[0].cmdline_params == [
        "--path",
        ".",
        "--posfile",
        "POSCAR",
        "--output_path",
        ".",
        "--spinor",
        "--prefix_spinor",
        "wannier90",
        "--elements",
        "Fe",
        "--kmesh",
        "7",
        "7",
        "7",
        "--efermi",
        "0.0",
    ]

    wannier_folder_uuid = calc_info.local_copy_list[0][0]
    assert calc_info.local_copy_list == [
        (wannier_folder_uuid, "aiida_tb.dat", "wannier90_tb.dat")
    ]


def test_collinear_defaults(generate_calcjob, generate_inputs):
    """Test the command line and file lists for a collinear up/down calculation."""
    inputs = generate_inputs(spinor=False)
    _, calc_info = generate_calcjob(WannierTB2JCalculation, inputs)

    cmdline_params = calc_info.codes_info[0].cmdline_params
    assert cmdline_params[:10] == [
        "--path",
        ".",
        "--posfile",
        "POSCAR",
        "--output_path",
        ".",
        "--prefix_up",
        "wannier90.up",
        "--prefix_down",
        "wannier90.dn",
    ]

    up_uuid, down_uuid = (
        inputs["wannier_folder_up"].uuid,
        inputs["wannier_folder_down"].uuid,
    )
    assert calc_info.local_copy_list == [
        (up_uuid, "aiida_tb.dat", "wannier90.up_tb.dat"),
        (down_uuid, "aiida_tb.dat", "wannier90.dn_tb.dat"),
    ]


def test_wannier_folder_hr_centres(generate_calcjob, generate_inputs):
    """A folder with `_hr.dat` + `_centres.xyz` is also a valid Hamiltonian source."""
    inputs = generate_inputs(wannier_files=("aiida_hr.dat", "aiida_centres.xyz"))
    _, calc_info = generate_calcjob(WannierTB2JCalculation, inputs)

    wannier_folder_uuid = inputs["wannier_folder"].uuid
    assert calc_info.local_copy_list == [
        (wannier_folder_uuid, "aiida_hr.dat", "wannier90_hr.dat"),
        (wannier_folder_uuid, "aiida_centres.xyz", "wannier90_centres.xyz"),
    ]


def test_wannier_folder_missing_files(generate_calcjob, generate_inputs):
    """An incomplete Wannier90 output folder should raise `InputValidationError`."""
    inputs = generate_inputs(wannier_files=("aiida_hr.dat",))
    with pytest.raises(InputValidationError):
        generate_calcjob(WannierTB2JCalculation, inputs)


def test_wannier_folder_empty(generate_calcjob, generate_inputs):
    """A Wannier90 folder with no recognised files should raise an error."""
    inputs = generate_inputs(wannier_files=())
    with pytest.raises(InputValidationError):
        generate_calcjob(WannierTB2JCalculation, inputs)


@pytest.mark.parametrize(
    "extra_inputs, message",
    [
        ({"wannier_folder_up": True}, "not both"),
        ({}, "Either 'wannier_folder'"),
    ],
)
def test_wannier_folder_mutual_exclusivity(
    generate_calcjob, generate_inputs, generate_folder_data, extra_inputs, message
):
    """Test the mutual exclusivity/required validation of the Wannier folder inputs."""
    inputs = generate_inputs()
    if "wannier_folder_up" in extra_inputs:
        inputs["wannier_folder_up"] = generate_folder_data(["aiida_tb.dat"])
        inputs["wannier_folder_down"] = generate_folder_data(["aiida_tb.dat"])
    else:
        del inputs["wannier_folder"]

    with pytest.raises(ValueError, match=message):
        generate_calcjob(WannierTB2JCalculation, inputs)


def test_wannier_folder_up_without_down(
    generate_calcjob, generate_inputs, generate_folder_data
):
    """Providing only `wannier_folder_up` without `wannier_folder_down` should fail."""
    inputs = generate_inputs()
    del inputs["wannier_folder"]
    inputs["wannier_folder_up"] = generate_folder_data(["aiida_tb.dat"])

    with pytest.raises(ValueError, match="must be given together"):
        generate_calcjob(WannierTB2JCalculation, inputs)


def test_kmesh_default_from_structure(
    generate_calcjob, generate_inputs, generate_structure
):
    """The kmesh should be derived from the structure cell when not given explicitly."""
    structure = generate_structure(
        cell=((2.87, 0.0, 0.0), (0.0, 2.87, 0.0), (0.0, 0.0, 15.0)),
        pbc=(True, True, False),
    )
    inputs = generate_inputs(structure=structure)
    _, calc_info = generate_calcjob(WannierTB2JCalculation, inputs)

    cmdline_params = calc_info.codes_info[0].cmdline_params
    kmesh_index = cmdline_params.index("--kmesh")
    assert cmdline_params[kmesh_index : kmesh_index + 4] == ["--kmesh", "7", "7", "1"]


def test_kmesh_explicit(generate_calcjob, generate_inputs):
    """An explicit `kmesh` parameter should be used verbatim and not duplicated."""
    inputs = generate_inputs(parameters={"efermi": 0.0, "kmesh": [3, 3, 3]})
    _, calc_info = generate_calcjob(WannierTB2JCalculation, inputs)

    cmdline_params = calc_info.codes_info[0].cmdline_params
    assert cmdline_params.count("--kmesh") == 1
    kmesh_index = cmdline_params.index("--kmesh")
    assert cmdline_params[kmesh_index : kmesh_index + 4] == ["--kmesh", "3", "3", "3"]


def test_supercell_size_override(generate_calcjob, generate_inputs):
    """A custom `supercell_size` should set the kmesh and not be forwarded verbatim."""
    inputs = generate_inputs(parameters={"efermi": 0.0, "supercell_size": 10.0})
    _, calc_info = generate_calcjob(WannierTB2JCalculation, inputs)

    cmdline_params = calc_info.codes_info[0].cmdline_params
    assert "--supercell_size" not in cmdline_params
    kmesh_index = cmdline_params.index("--kmesh")
    assert cmdline_params[kmesh_index : kmesh_index + 4] == ["--kmesh", "4", "4", "4"]


@pytest.mark.parametrize(
    "parameter, value, expected_args",
    [
        ("exclude_orbs", [1, 2, 3], ["--exclude_orbs", "1", "2", "3"]),
        ("use_cache", True, ["--use_cache"]),
        ("use_cache", False, []),
        ("groupby", "spin", ["--groupby", "spin"]),
        ("rcut", 5.5, ["--rcut", "5.5"]),
    ],
)
def test_as_cmdline_args(
    generate_calcjob, generate_inputs, parameter, value, expected_args
):
    """Test the translation of various parameter types into command line arguments."""
    inputs = generate_inputs(parameters={"efermi": 0.0, parameter: value})
    _, calc_info = generate_calcjob(WannierTB2JCalculation, inputs)

    cmdline_params = calc_info.codes_info[0].cmdline_params
    trailing = cmdline_params[cmdline_params.index("--efermi") + 2 :]
    assert trailing == expected_args


@pytest.mark.parametrize(
    "parameters, message",
    [
        ({"kmesh": [1, 2]}, "'kmesh' option must contain 3 integers"),
        ({"kmesh": 5}, "'kmesh' option must be an iterable"),
        ({"exclude_orbs": ["a", "b"]}, "'exclude_orbs' option must be a list of"),
        ({"exclude_orbs": 5}, "'exclude_orbs' option must be an iterable"),
        ({"smearing": 5}, "'smearing' option must be a valid"),
        ({"groupby": "invalid"}, "'groupby' option must be either 'spin' or 'orbital'"),
        ({"supercell_size": -5.0}, "'supercell_size' option must be positive"),
        ({"not_a_real_option": "value"}, "Unrecognized option 'not_a_real_option'"),
        ({}, "The 'efermi' option is required"),
    ],
)
def test_validate_parameters_errors(
    generate_calcjob, generate_inputs, parameters, message
):
    """Test that invalid `parameters` dictionaries raise the expected error message."""
    if "efermi" not in parameters and parameters:
        parameters = {**parameters, "efermi": 0.0}
    inputs = generate_inputs(parameters=parameters)

    with pytest.raises(ValueError, match=message):
        generate_calcjob(WannierTB2JCalculation, inputs)
