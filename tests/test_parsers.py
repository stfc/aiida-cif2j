"""Tests for the `TB2JParser`."""

import pickle

import numpy

from aiida_cif2j.calculations.wannier_tb2j import WannierTB2JCalculation
from aiida_cif2j.parsers.tb2j import (
    TB2JParser,
    _build_anisotropic_exchange_data,
    _build_dmi_vector_data,
)


def test_parse_success(
    generate_calc_job_node, generate_folder_data, get_data_filepath, tmp_path
):
    """A temporary retrieval folder with `TB2J.pickle` should parse with no exit code.

    `TB2J.pickle` is only ever retrieved into the transient parsing folder (see
    `WannierTB2JCalculation.prepare_for_submission`), never into the permanent
    `retrieved` folder, so its content isn't duplicated between `retrieved` and the
    dedicated `TB2J_pickle_file` output.
    """
    pickle_bytes = (get_data_filepath / "TB2J.pickle").read_bytes()
    spin_io = pickle.loads(pickle_bytes)

    retrieved = generate_folder_data([])
    node = generate_calc_job_node(WannierTB2JCalculation, retrieved)
    (tmp_path / "TB2J.pickle").write_bytes(pickle_bytes)

    results, calcfunction = TB2JParser.parse_from_node(
        node, store_provenance=False, retrieved_temporary_folder=str(tmp_path)
    )

    assert calcfunction.is_finished_ok, calcfunction.exit_message
    assert results["TB2J_pickle_file"].get_content(mode="rb") == pickle_bytes
    assert results["TB2J_pickle_file"].filename == "TB2J.pickle"

    n_pairs = len(spin_io["exchange_Jdict"])
    exchange_couplings = results["exchange_couplings"]
    assert len(exchange_couplings.get_array("J_iso")) == n_pairs
    assert exchange_couplings.get_array("site_i").shape == (n_pairs,)
    assert exchange_couplings.get_array("distance_vector").shape == (n_pairs, 3)
    assert exchange_couplings.base.attributes.get("units")["J_iso"] == "meV"

    magnetic_moments = results["magnetic_moments"]
    assert magnetic_moments.get_array("moments").shape == (len(spin_io["spinat"]), 3)

    # The fixture system has no spin-orbit coupling, so TB2J computed neither DMI
    # nor anisotropic exchange for it; both optional outputs must be absent.
    assert "dmi_vectors" not in results
    assert "anisotropic_exchange" not in results


def test_parse_missing_pickle(generate_calc_job_node, generate_folder_data, tmp_path):
    """A temporary folder without `TB2J.pickle` returns the missing-pickle exit code."""
    retrieved = generate_folder_data([])
    node = generate_calc_job_node(WannierTB2JCalculation, retrieved)
    (tmp_path / "some_other_file.txt").write_bytes(b"")

    _, calcfunction = TB2JParser.parse_from_node(
        node, store_provenance=False, retrieved_temporary_folder=str(tmp_path)
    )

    assert (
        calcfunction.exit_status
        == WannierTB2JCalculation.exit_codes.ERROR_OUTPUT_PICKLE_MISSING.status
    )


def test_parse_corrupt_pickle(generate_calc_job_node, generate_folder_data, tmp_path):
    """A `TB2J.pickle` that isn't a valid TB2J results pickle should fail cleanly."""
    retrieved = generate_folder_data([])
    node = generate_calc_job_node(WannierTB2JCalculation, retrieved)
    (tmp_path / "TB2J.pickle").write_bytes(b"not-a-pickle")

    _, calcfunction = TB2JParser.parse_from_node(
        node, store_provenance=False, retrieved_temporary_folder=str(tmp_path)
    )

    assert (
        calcfunction.exit_status
        == WannierTB2JCalculation.exit_codes.ERROR_OUTPUT_PICKLE_CORRUPT.status
    )


def _minimal_spin_io(dmi_ddict=None, jani_dict=None) -> dict:
    """Build a hand-built, minimal 2-pair `spin_io`-shaped dict for unit-testing."""
    key_01 = ((0, 0, 0), 0, 1)
    key_10 = ((0, 0, 0), 1, 0)
    return {
        "exchange_Jdict": {key_01: -0.1, key_10: -0.1},
        "distance_dict": {
            key_01: (numpy.array([5.0, 0.0, 0.0]), 5.0),
            key_10: (numpy.array([-5.0, 0.0, 0.0]), 5.0),
        },
        "dmi_ddict": dmi_ddict,
        "Jani_dict": jani_dict,
    }


def test_build_dmi_vector_data_absent():
    """`dmi_ddict is None` (no DMI computed) must return `None`, not an empty node."""
    assert _build_dmi_vector_data(_minimal_spin_io()) is None


def test_build_dmi_vector_data_present():
    """A populated `dmi_ddict` should build one row per its own keys."""
    key_01 = ((0, 0, 0), 0, 1)
    dmi_ddict = {key_01: numpy.array([0.0, 0.0, 0.01])}
    spin_io = _minimal_spin_io(dmi_ddict=dmi_ddict)

    data = _build_dmi_vector_data(spin_io)

    assert data is not None
    assert data.get_array("dmi_vector").shape == (1, 3)
    assert data.get_array("site_i").tolist() == [0]
    assert data.get_array("site_j").tolist() == [1]
    assert data.base.attributes.get("units")["dmi_vector"] == "meV"


def test_build_anisotropic_exchange_data_absent():
    """`Jani_dict is None` (no anisotropic exchange computed) must return `None`."""
    assert _build_anisotropic_exchange_data(_minimal_spin_io()) is None


def test_build_anisotropic_exchange_data_present():
    """A populated `Jani_dict` should build one row per its own keys."""
    key_01 = ((0, 0, 0), 0, 1)
    jani_dict = {key_01: numpy.eye(3) * 0.01}
    spin_io = _minimal_spin_io(jani_dict=jani_dict)

    data = _build_anisotropic_exchange_data(spin_io)

    assert data is not None
    assert data.get_array("J_tensor").shape == (1, 3, 3)
    assert data.base.attributes.get("units")["J_tensor"] == "meV"
