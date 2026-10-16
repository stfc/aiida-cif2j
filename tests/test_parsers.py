"""Tests for the `TB2JParser`."""

from aiida_cif2j.calculations.wannier_tb2j import WannierTB2JCalculation
from aiida_cif2j.parsers.tb2j import TB2JParser


def test_parse_success(generate_calc_job_node, generate_folder_data):
    """A retrieved folder containing `TB2J.pickle` should parse without an exit code."""
    retrieved = generate_folder_data(["TB2J.pickle"])
    node = generate_calc_job_node(WannierTB2JCalculation, retrieved)

    _, calcfunction = TB2JParser.parse_from_node(node, store_provenance=False)

    assert calcfunction.is_finished_ok, calcfunction.exit_message


def test_parse_missing_pickle(generate_calc_job_node, generate_folder_data):
    """A retrieved folder without `TB2J.pickle` returns the missing-pickle exit code."""
    retrieved = generate_folder_data(["some_other_file.txt"])
    node = generate_calc_job_node(WannierTB2JCalculation, retrieved)

    _, calcfunction = TB2JParser.parse_from_node(node, store_provenance=False)

    assert (
        calcfunction.exit_status
        == WannierTB2JCalculation.exit_codes.ERROR_OUTPUT_PICKLE_MISSING.status
    )
