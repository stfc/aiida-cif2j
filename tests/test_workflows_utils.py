"""Tests for `aiida_cif2j.workflows.utils`."""

import pytest
from aiida.orm import List

from aiida_cif2j.workflows.utils import validate_chemical_symbols


def test_validate_chemical_symbols_not_given():
    """A missing (`None`) value is valid, since the input is optional."""
    assert validate_chemical_symbols(None, None) is None


def test_validate_chemical_symbols_valid():
    """A list of valid chemical symbols should pass validation."""
    assert validate_chemical_symbols(List(["Fe", "O"]), None) is None


def test_validate_chemical_symbols_empty():
    """An explicitly empty list should be rejected."""
    message = validate_chemical_symbols(List([]), None)

    assert message == "Element list must not be empty."


def test_validate_chemical_symbols_invalid():
    """A list containing an invalid chemical symbol should be rejected."""
    message = validate_chemical_symbols(List(["Fe", "Zz"]), None)

    assert message is not None
    assert "Zz" in message


@pytest.mark.parametrize("symbols", [["Fe"], ["Fe", "O", "Mn"]])
def test_validate_chemical_symbols_various_valid(symbols):
    """Single- and multi-element lists of valid symbols should both pass."""
    assert validate_chemical_symbols(List(symbols), None) is None
