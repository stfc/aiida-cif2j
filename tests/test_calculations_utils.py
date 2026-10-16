"""Tests for the calcfunctions in `aiida_cif2j.calculations.utils`."""

import pytest
from aiida.orm import List
from aiida_wannier90_workflows.data.structure import MagneticStructureData

from aiida_cif2j.calculations.utils import (
    detect_magnetic_elements,
    parse_magnetic_structure,
)


def test_parse_magnetic_structure(get_test_data_file):
    """Test parsing a plain (non-magnetic) CIF file into a `MagneticStructureData`."""
    structure_file = get_test_data_file("nacl.cif")
    structure = parse_magnetic_structure(structure_file)

    assert isinstance(structure, MagneticStructureData)
    for row, expected in zip(
        structure.cell, [[4.0, 0.0, 0.0], [0.0, 4.0, 0.0], [0.0, 0.0, 4.0]], strict=True
    ):
        assert row == pytest.approx(expected)
    assert structure.pbc == (True, True, True)

    sites = {site.kind_name: site.position for site in structure.sites}
    assert set(sites) == {"Na", "Cl"}
    assert sites["Na"] == pytest.approx((0.0, 0.0, 0.0))
    assert sites["Cl"] == pytest.approx((2.0, 2.0, 2.0))


def test_detect_magnetic_elements(generate_magnetic_structure):
    """Only kinds with a magmom magnitude above the threshold should be detected."""
    structure = generate_magnetic_structure(
        kinds=(("Fe", (0.0, 0.0, 2.0)), ("O", (0.0, 0.0, 0.0)))
    )

    elements = detect_magnetic_elements(structure)

    assert isinstance(elements, List)
    assert elements.get_list() == ["Fe"]


def test_detect_magnetic_elements_sorted(generate_magnetic_structure):
    """Multiple magnetic elements should be returned sorted alphabetically."""
    structure = generate_magnetic_structure(
        kinds=(
            ("Mn", (0.0, 0.0, 3.0)),
            ("Fe", (0.0, 0.0, 2.0)),
            ("O", (0.0, 0.0, 0.0)),
        )
    )

    elements = detect_magnetic_elements(structure)

    assert elements.get_list() == ["Fe", "Mn"]


def test_detect_magnetic_elements_below_threshold(generate_magnetic_structure):
    """A magmom magnitude below the threshold should not count as magnetic."""
    structure = generate_magnetic_structure(kinds=(("Fe", (0.0, 0.0, 0.0005)),))

    elements = detect_magnetic_elements(structure)

    assert elements.get_list() == []


def test_detect_magnetic_elements_without_magmom(generate_magnetic_structure):
    """Kinds with no magmom set at all should be treated as non-magnetic."""
    structure = generate_magnetic_structure(kinds=(("Na", None), ("Cl", None)))

    elements = detect_magnetic_elements(structure)

    assert elements.get_list() == []


def test_detect_magnetic_elements_from_nonmagnetic_cif(get_test_data_file):
    """A structure parsed from a plain CIF should yield no magnetic elements."""
    structure_file = get_test_data_file("nacl.cif")
    structure = parse_magnetic_structure(structure_file)

    elements = detect_magnetic_elements(structure)

    assert elements.get_list() == []


def test_parse_magnetic_structure_from_mcif(get_test_data_file):
    """Test parsing a real mCIF file with explicit magnetic moments."""
    structure_file = get_test_data_file("0.15_MnF2.mcif")
    structure = parse_magnetic_structure(structure_file)

    assert isinstance(structure, MagneticStructureData)
    for row, expected in zip(
        structure.cell,
        [[4.8736, 0.0, 0.0], [0.0, 4.8736, 0.0], [0.0, 0.0, 3.3]],
        strict=True,
    ):
        assert row == pytest.approx(expected, abs=1e-10)

    assert len(structure.sites) == 6

    magmoms = {kind.name: kind.symbol for kind in structure.kinds}
    assert magmoms == {"Mn0": "Mn", "Mn1": "Mn", "F": "F"}

    kind_magmoms = {kind.name: kind.magmom for kind in structure.kinds}
    assert kind_magmoms["Mn0"] == pytest.approx((0.0, 0.0, 4.6))
    assert kind_magmoms["Mn1"] == pytest.approx((0.0, 0.0, -4.6))
    assert kind_magmoms["F"] == pytest.approx((0.0, 0.0, 0.0))


def test_detect_magnetic_elements_from_magnetic_mcif(get_test_data_file):
    """The antiferromagnetic Mn sublattice should be detected, but not the F ions."""
    structure_file = get_test_data_file("0.15_MnF2.mcif")
    structure = parse_magnetic_structure(structure_file)

    elements = detect_magnetic_elements(structure)

    assert elements.get_list() == ["Mn"]
