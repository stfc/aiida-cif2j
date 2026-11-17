"""Tests for the `TB2JParser`."""

import pickle

from aiida_cif2j.calculations.wannier_tb2j import WannierTB2JCalculation
from aiida_cif2j.parsers.tb2j import TB2JParser


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
