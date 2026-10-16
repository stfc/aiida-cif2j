"""Utility functions for AiiDA CIF2J workflows."""

import numpy as np
from aiida.orm import List
from aiida.orm.nodes.data.structure import is_valid_symbol
from aiida_wannier90_workflows.data.structure import MagneticStructureData

_MAGNETIC_MOMENT_THRESHOLD = 1e-3  # matches calculations/utils.py's own threshold


def validate_chemical_symbols(value: List | None, _) -> str | None:
    """Validate a list of elements."""
    if value is not None:
        if len(value) < 1:
            return "Element list must not be empty."
        if all(is_valid_symbol(symbol) for symbol in value):
            return None
        return f"Invalid element in list: {list(value)}."
    return None


def collinear_magnetic_moments(structure: MagneticStructureData) -> dict[str, float]:
    """
    Build a signed, scalar initial-magnetic-moment dict, keyed by kind name.

    Works around `MagneticStructureData.is_collin_mag()` (upstream) misclassifying
    antiparallel, same-axis (antiferromagnetic) structures as non-collinear: supplying
    this dict explicitly as `initial_magnetic_moments` bypasses that detection
    entirely.

    For each kind, take `kind.magmom` (a cartesian 3-tuple; `AttributeError` if unset
    is treated as the zero vector, matching the defensive pattern already used by
    `detect_magnetic_elements`). The first non-zero moment encountered fixes a
    reference axis (its unit vector); every subsequent kind's signed value is
    `+magnitude` if its moment has non-negative dot product with that axis,
    `-magnitude` otherwise.

    Only ever called when the caller has already committed to `SpinType.COLLINEAR`;
    it never raises or warns on apparently non-collinear input (multiple unrelated
    axes) -- it reports the sign relative to the first-encountered axis regardless.
    Re-validating genuine collinearity here would mean re-implementing a corrected
    `is_collin_mag()`, which is out of scope for a narrow workaround.

    Parameters
    ----------
    structure : MagneticStructureData
        The structure to read per-kind magnetic moments from.

    Returns
    -------
    dict[str, float]
        A signed scalar moment, in Bohr magnetons, for each kind name in
        `structure`. Suitable for passing as `initial_magnetic_moments` to
        `*.get_builder_from_protocol`.
    """
    reference_axis: np.ndarray | None = None
    moments: dict[str, float] = {}

    for kind in structure.kinds:
        try:
            vector = np.asarray(kind.magmom, dtype=float)
        except AttributeError:
            moments[kind.name] = 0.0
            continue

        magnitude = float(np.linalg.norm(vector))
        if magnitude < _MAGNETIC_MOMENT_THRESHOLD:
            moments[kind.name] = 0.0
            continue

        if reference_axis is None:
            reference_axis = vector / magnitude
            moments[kind.name] = magnitude
            continue

        sign = 1.0 if np.dot(vector, reference_axis) >= 0.0 else -1.0
        moments[kind.name] = sign * magnitude

    return moments


def total_magnetization(
    structure: MagneticStructureData, moments: dict[str, float]
) -> float:
    """
    Compute QE's SYSTEM `tot_magnetization` (net) from a signed per-kind `moments`.

    Sums `moments[site.kind_name]` over every site (not every kind), so a kind
    occupied by several sites is automatically weighted by its atom count.

    Parameters
    ----------
    structure : MagneticStructureData
        The structure whose sites are summed over.
    moments : dict[str, float]
        A signed scalar moment for each kind name in `structure`, as returned by
        `collinear_magnetic_moments` (or an equivalent caller-supplied dict).

    Returns
    -------
    float
        The net total magnetic moment of `structure`.
    """
    return sum(moments[site.kind_name] for site in structure.sites)
