"""Tests for `aiida_cif2j.workflows.utils`."""

import pytest
from aiida.orm import List
from aiida_wannier90_workflows.data.structure import MagneticStructureData

from aiida_cif2j.workflows.utils import (
    collinear_magnetic_moments,
    total_magnetization,
    validate_chemical_symbols,
)


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


def test_collinear_magnetic_moments_default(generate_magnetic_structure):
    """The magnetic kind keeps its magnitude, the non-magnetic kind is zero."""
    structure = generate_magnetic_structure()

    moments = collinear_magnetic_moments(structure)

    assert moments == {"Fe0": 2.0, "O1": 0.0}


def test_collinear_magnetic_moments_antiferromagnetic(generate_magnetic_structure):
    """Antiparallel, same-axis kinds should keep opposite signs."""
    structure = generate_magnetic_structure(
        kinds=(
            ("Mn", (0.0, 0.0, 4.6)),
            ("Mn", (0.0, 0.0, -4.6)),
            ("F", None),
        )
    )

    moments = collinear_magnetic_moments(structure)

    assert moments == {"Mn0": pytest.approx(4.6), "Mn1": pytest.approx(-4.6), "F2": 0.0}


def test_collinear_magnetic_moments_no_magmom(generate_magnetic_structure):
    """Kinds with no magmom set at all should be treated as zero, not raise."""
    structure = generate_magnetic_structure(kinds=(("Na", None), ("Cl", None)))

    moments = collinear_magnetic_moments(structure)

    assert moments == {"Na0": 0.0, "Cl1": 0.0}


def test_collinear_magnetic_moments_single_kind(generate_magnetic_structure):
    """A single magnetic kind has no reference-axis ambiguity and stays positive."""
    structure = generate_magnetic_structure(kinds=(("Fe", (0.0, 0.0, 3.0)),))

    moments = collinear_magnetic_moments(structure)

    assert moments == {"Fe0": pytest.approx(3.0)}


def test_total_magnetization_sums_per_site():
    """Multiple sites sharing a kind should each contribute to the total."""
    structure = MagneticStructureData(
        cell=((4.0, 0.0, 0.0), (0.0, 4.0, 0.0), (0.0, 0.0, 4.0)), pbc=(True, True, True)
    )
    structure.append_atom(
        position=(0.0, 0.0, 0.0), symbols="Fe", name="Fe", magmom=(0.0, 0.0, 2.0)
    )
    structure.append_atom(
        position=(1.0, 0.0, 0.0), symbols="Fe", name="Fe", magmom=(0.0, 0.0, 2.0)
    )
    structure.append_atom(
        position=(2.0, 0.0, 0.0), symbols="O", name="O", magmom=(0.0, 0.0, 0.0)
    )

    total = total_magnetization(structure, {"Fe": 2.0, "O": 0.0})

    assert total == pytest.approx(4.0)
