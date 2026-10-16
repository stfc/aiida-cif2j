"""Calcfunctions used accross the AiiDA CIF2J package."""

from io import StringIO

from aiida.engine import calcfunction
from aiida.orm import List, SinglefileData
from aiida_wannier90_workflows.data.structure import MagneticStructureData
from pymatgen.io.cif import CifParser

_MAGNETIC_MOMENT_THRESHOLD = 1e-3


@calcfunction
def parse_magnetic_structure(
    structure_file: SinglefileData,
) -> MagneticStructureData:
    """Parse a structure file into a MagneticStructureData node."""
    parser = CifParser(StringIO(structure_file.get_content(mode="r")))
    pymatgen_structure = parser.parse_structures(primitive=False)[0]
    structure = MagneticStructureData()
    structure.set_pymatgen_structure(pymatgen_structure)
    return structure


@calcfunction
def detect_magnetic_elements(structure: MagneticStructureData) -> List:
    """Detect which elements carry a non-zero magnetic moment in the structure."""
    elements = set()
    for kind in structure.kinds:
        try:
            magnitude, _a1, _a2 = kind.get_magmom_coord()
        except AttributeError:
            continue
        if abs(magnitude) > _MAGNETIC_MOMENT_THRESHOLD:
            elements.add(kind.symbol)
    return List(sorted(elements))
