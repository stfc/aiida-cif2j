"""Tests for the `TB2JParser`."""

from aiida_cif2j.calculations.wannier_tb2j import WannierTB2JCalculation
from aiida_cif2j.parsers.tb2j import TB2JParser


def test_parse_success(generate_calc_job_node, generate_folder_data, tmp_path):
    """A temporary retrieval folder with `TB2J.pickle` should parse with no exit code.

    `TB2J.pickle` is only ever retrieved into the transient parsing folder (see
    `WannierTB2JCalculation.prepare_for_submission`), never into the permanent
    `retrieved` folder, so its content isn't duplicated between `retrieved` and the
    dedicated `TB2J_pickle_file` output.
    """
    retrieved = generate_folder_data([])
    node = generate_calc_job_node(WannierTB2JCalculation, retrieved)
    (tmp_path / "TB2J.pickle").write_bytes(b"pickled-data")

    results, calcfunction = TB2JParser.parse_from_node(
        node, store_provenance=False, retrieved_temporary_folder=str(tmp_path)
    )

    assert calcfunction.is_finished_ok, calcfunction.exit_message
    assert results["TB2J_pickle_file"].get_content(mode="rb") == b"pickled-data"
    assert results["TB2J_pickle_file"].filename == "TB2J.pickle"


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
