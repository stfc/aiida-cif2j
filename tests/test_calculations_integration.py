"""End-to-end integration tests for `WannierTB2JCalculation` against a real TB2J.

Unlike `test_calculations.py` (which only exercises `prepare_for_submission` in
isolation), these tests actually submit the calculation through AiiDA's engine and
run the real `wann2J.py` executable, against a minimal but genuinely valid two-atom
Wannier90 tight-binding dataset. They are skipped unless TB2J is installed and
`wann2J.py` is resolvable on `PATH` (e.g. via `pip install .[tb2j]`).

The `_tb.dat` format used below was verified directly against TB2J 0.9.22's own
reader (`HamiltonIO.wannier.w90_tb_parser.parse_tb_file`) by running `wann2J.py`
against it outside of AiiDA.
"""

import io
import pickle
import shutil

import pytest
from aiida.engine import run_get_node
from aiida.orm import Dict, FolderData, List, StructureData

from aiida_cif2j.calculations.wannier_tb2j import WannierTB2JCalculation

pytestmark = pytest.mark.skipif(
    shutil.which("wann2J.py") is None,
    reason="TB2J is not installed (install the 'tb2j' extra to run this test)",
)

_CELL = ((10.0, 0.0, 0.0), (0.0, 10.0, 0.0), (0.0, 0.0, 10.0))


def _generate_structure() -> StructureData:
    """Two Fe atoms, 5 Angstrom apart, matching the synthetic datasets below."""
    structure = StructureData(cell=_CELL)
    structure.append_atom(position=(0.0, 0.0, 0.0), symbols="Fe")
    structure.append_atom(position=(5.0, 0.0, 0.0), symbols="Fe")
    return structure


def _generate_collinear_tb_dat(
    onsite_0: float, onsite_1: float, hopping: float
) -> bytes:
    """Build a minimal, valid collinear `_tb.dat`: 2 atoms, 1 orbital each."""
    lines = [
        "test tb.dat",
        "10.0 0.0 0.0",
        "0.0 10.0 0.0",
        "0.0 0.0 10.0",
        "2",
        "1",
        "1",
        "",
        "0 0 0",
        f"1 1 {onsite_0} 0.0",
        f"2 1 {hopping} 0.0",
        f"1 2 {hopping} 0.0",
        f"2 2 {onsite_1} 0.0",
        "",
        "0 0 0",
        "1 1 0.0 0.0 0.0 0.0 0.0 0.0",
        "2 1 0.0 0.0 0.0 0.0 0.0 0.0",
        "1 2 0.0 0.0 0.0 0.0 0.0 0.0",
        "2 2 5.0 0.0 0.0 0.0 0.0 0.0",
        "",
    ]
    return ("\n".join(lines) + "\n").encode()


def _generate_spinor_tb_dat() -> bytes:
    """Build a minimal, valid spinor `_tb.dat`: 2 atoms, 1 orbital, 2 spins each.

    Orbital order (`--groupby spin`, the wann2J.py default): [up_0, up_1, down_0,
    down_1]. Up/down blocks are decoupled (no spin-orbit terms) for simplicity.
    """
    # H[m, n], 0-indexed, order = [up0, up1, down0, down1]
    h = [
        [-2.0, 0.5, 0.0, 0.0],
        [0.5, -2.0, 0.0, 0.0],
        [0.0, 0.0, 2.0, 0.5],
        [0.0, 0.0, 0.5, 2.0],
    ]
    # Which atom (0 or 1) each orbital belongs to, for the Wannier centre.
    atom_of = [0, 1, 0, 1]
    centres_cart = [(0.0, 0.0, 0.0), (5.0, 0.0, 0.0)]

    lines = [
        "spinor test tb.dat",
        "10.0 0.0 0.0",
        "0.0 10.0 0.0",
        "0.0 0.0 10.0",
        "4",
        "1",
        "1",
        "",
        "0 0 0",
    ]
    for n in range(4):
        for m in range(4):
            lines.append(f"{m + 1} {n + 1} {h[m][n]} 0.0")
    lines += ["", "0 0 0"]
    for n in range(4):
        for m in range(4):
            if m == n:
                cx, cy, cz = centres_cart[atom_of[m]]
                lines.append(f"{m + 1} {n + 1} {cx} 0.0 {cy} 0.0 {cz} 0.0")
            else:
                lines.append(f"{m + 1} {n + 1} 0.0 0.0 0.0 0.0 0.0 0.0")
    lines.append("")
    return ("\n".join(lines) + "\n").encode()


def _put_tb_dat(content: bytes) -> FolderData:
    folder = FolderData()
    folder.put_object_from_filelike(io.BytesIO(content), "aiida_tb.dat")
    return folder


def _load_exchange_count(results) -> int:
    """Load the `TB2J_pickle_file` output and return the number of exchange pairs."""
    pickle_bytes = results["TB2J_pickle_file"].get_content(mode="rb")
    spin_io_dict = pickle.loads(pickle_bytes)
    return len(spin_io_dict["exchange_Jdict"])


def test_collinear_end_to_end(wannier_tb2j_code):
    """Run a real, collinear `wann2J.py` calculation end-to-end through AiiDA."""
    inputs = {
        "code": wannier_tb2j_code(),
        "elements": List(["Fe"]),
        "parameters": Dict({"efermi": 0.0, "kmesh": [1, 1, 1]}),
        "structure": _generate_structure(),
        "wannier_folder_up": _put_tb_dat(_generate_collinear_tb_dat(-2.0, -2.0, 0.5)),
        "wannier_folder_down": _put_tb_dat(_generate_collinear_tb_dat(2.0, 2.0, 0.5)),
    }

    results, node = run_get_node(WannierTB2JCalculation, **inputs)

    assert node.is_finished_ok, node.exit_message
    assert _load_exchange_count(results) == 2


def test_spinor_end_to_end(wannier_tb2j_code):
    """Run a real, non-collinear/spinor `wann2J.py` calculation end-to-end."""
    inputs = {
        "code": wannier_tb2j_code(),
        "elements": List(["Fe"]),
        "parameters": Dict({"efermi": 0.0, "kmesh": [1, 1, 1]}),
        "structure": _generate_structure(),
        "wannier_folder": _put_tb_dat(_generate_spinor_tb_dat()),
    }

    results, node = run_get_node(WannierTB2JCalculation, **inputs)

    assert node.is_finished_ok, node.exit_message
    assert _load_exchange_count(results) == 2
