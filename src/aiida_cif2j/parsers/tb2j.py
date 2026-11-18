"""The core TB2J output parsers."""

import pathlib
import pickle

import numpy
from aiida.engine import ExitCode
from aiida.orm import ArrayData, SinglefileData
from aiida.parsers import Parser

from aiida_cif2j.calculations.wannier_tb2j import WannierTB2JCalculation
from aiida_cif2j.data.exchange_coupling import (
    ANISOTROPIC_EXCHANGE_UNITS,
    DMI_UNITS,
    UNITS,
    AnisotropicExchangeData,
    DMIVectorData,
    ExchangeCouplingData,
)


def _parse_spin_io_dict(pickle_bytes: bytes) -> dict:
    """Unpickle a TB2J output file into its raw `dict` of results.

    Parameters
    ----------
    pickle_bytes : bytes
        The raw content of a TB2J `TB2J.pickle` output file.

    Returns
    -------
    dict
        The unpickled TB2J results dictionary (keys include `exchange_Jdict`,
        `distance_dict`, `dmi_ddict`, `Jani_dict`, `spinat`, etc.).

    Raises
    ------
    ValueError
        If the content cannot be unpickled, or does not unpickle to the
        expected `dict` shape.
    """
    try:
        spin_io = pickle.loads(pickle_bytes)
    except (pickle.UnpicklingError, EOFError, AttributeError, ImportError) as exc:
        raise ValueError("Could not unpickle 'TB2J.pickle'.") from exc
    if not isinstance(spin_io, dict) or "exchange_Jdict" not in spin_io:
        raise ValueError("'TB2J.pickle' did not contain the expected TB2J results.")
    return spin_io


def _deduplicate_mirrored_pairs(pair_dict: dict) -> dict:
    """Collapse each `(R, i, j)`/`(-R, j, i)` mirrored pair into one entry.

    TB2J's own convention double-counts every bond, once from each site's
    perspective (see `tb2j_pickle_schema_findings` project memory). For an
    isotropic (scalar) quantity like `exchange_Jdict`'s J_iso, `J_ij == J_ji`
    exactly in theory, so this is pure duplication rather than independent
    information - unlike `dmi_ddict`'s DMI vector (antisymmetric,
    `D_ij == -D_ji`) or `Jani_dict`'s tensor (transposes under the swap),
    where "drop one direction" needs a sign/transpose convention decided
    first, so this is intentionally only called for `exchange_Jdict`.

    Picks a deterministic representative per bond (whichever direction's key
    is encountered first) and averages the two directions' values rather
    than discarding one outright, to absorb the tiny numerical asymmetry
    TB2J's Green's-function evaluation can introduce between directions -
    matching how `pyspinw.tb2j.TB2J_Input.to_hamiltonian()` treats the same
    mirrored pairs (see `pyspinw_tb2j_integration` project memory). A pair
    with no mirror present in `pair_dict` (e.g. right at a cutoff-radius
    boundary) is kept as-is rather than dropped.

    Parameters
    ----------
    pair_dict : dict
        A TB2J `{(R, i, j): value}` dictionary of scalar values.

    Returns
    -------
    dict
        A new `{(R, i, j): value}` dictionary with one entry per physical
        bond.
    """
    deduplicated = {}
    seen_mirrors = set()
    for key, value in pair_dict.items():
        if key in seen_mirrors:
            continue
        r_vector, i, j = key
        mirror_key = (tuple(-r for r in r_vector), j, i)
        mirror_value = pair_dict.get(mirror_key)
        if mirror_value is None:
            deduplicated[key] = value
        else:
            deduplicated[key] = (value + mirror_value) / 2.0
        seen_mirrors.add(mirror_key)
    return deduplicated


def _build_pair_data(
    data_cls: type[ArrayData],
    pair_dict: dict,
    distance_dict: dict,
    value_name: str,
    units: dict,
) -> ArrayData:
    """Build a `(site_i, site_j, R, distance, distance_vector, <value>)` node.

    One row is written per `pair_dict` key, as given - this function itself
    does no deduplication of TB2J's mirrored-direction pairs. Shared by
    `ExchangeCouplingData`, `DMIVectorData` and `AnisotropicExchangeData`,
    which all key their respective TB2J dict (`exchange_Jdict`, `dmi_ddict`,
    `Jani_dict`) by the same `(R, i, j)` tuples; `_build_exchange_coupling_data`
    pre-deduplicates `exchange_Jdict` via `_deduplicate_mirrored_pairs` before
    calling this, but `dmi_ddict`/`Jani_dict` are passed through unmodified
    (see that function's docstring for why).

    Parameters
    ----------
    data_cls : type[ArrayData]
        The `ArrayData` subclass to instantiate.
    pair_dict : dict
        A TB2J `{(R, i, j): value}` dictionary (e.g. `exchange_Jdict`).
    distance_dict : dict
        TB2J's `{(R, i, j): (distance_vector, distance)}` dictionary.
    value_name : str
        The array name under which to store `pair_dict`'s values.
    units : dict
        Passed through to the node's `units` attribute.

    Returns
    -------
    ArrayData
        The resulting node, not yet stored.
    """
    site_i = []
    site_j = []
    r_vectors = []
    distances = []
    distance_vectors = []
    values = []
    for (r_vector, i, j), value in pair_dict.items():
        distance_vector, distance = distance_dict[(r_vector, i, j)]
        site_i.append(i)
        site_j.append(j)
        r_vectors.append(r_vector)
        distances.append(distance)
        distance_vectors.append(distance_vector)
        values.append(value)

    data = data_cls()
    data.set_array("site_i", numpy.array(site_i, dtype=int))
    data.set_array("site_j", numpy.array(site_j, dtype=int))
    data.set_array("R", numpy.array(r_vectors, dtype=int))
    data.set_array("distance", numpy.array(distances, dtype=float))
    data.set_array("distance_vector", numpy.array(distance_vectors, dtype=float))
    data.set_array(value_name, numpy.array(values, dtype=float))
    data.base.attributes.set("units", units)
    return data


def _build_exchange_coupling_data(spin_io: dict) -> ExchangeCouplingData:
    """Build an `ExchangeCouplingData` node from a TB2J results dictionary.

    One row per physical bond, not per `exchange_Jdict` key - see
    `_deduplicate_mirrored_pairs`. To go back to TB2J's own raw, undeduplicated
    convention, drop the `_deduplicate_mirrored_pairs(...)` call below and pass
    `spin_io["exchange_Jdict"]` straight through, as `_build_dmi_vector_data`/
    `_build_anisotropic_exchange_data` still do.

    Parameters
    ----------
    spin_io : dict
        A TB2J results dictionary, as returned by `_parse_spin_io_dict`.

    Returns
    -------
    ExchangeCouplingData
        The resulting node, not yet stored.
    """
    return _build_pair_data(
        ExchangeCouplingData,
        _deduplicate_mirrored_pairs(spin_io["exchange_Jdict"]),
        spin_io["distance_dict"],
        "J_iso",
        UNITS,
    )


def _build_dmi_vector_data(spin_io: dict) -> DMIVectorData | None:
    """Build a `DMIVectorData` node from a TB2J results dictionary, if present.

    Parameters
    ----------
    spin_io : dict
        A TB2J results dictionary, as returned by `_parse_spin_io_dict`.

    Returns
    -------
    DMIVectorData or None
        The resulting node, not yet stored, or `None` if TB2J did not
        compute DMI (`dmi_ddict is None`) for this run.
    """
    dmi_ddict = spin_io.get("dmi_ddict")
    if dmi_ddict is None:
        return None
    return _build_pair_data(
        DMIVectorData, dmi_ddict, spin_io["distance_dict"], "dmi_vector", DMI_UNITS
    )


def _build_anisotropic_exchange_data(spin_io: dict) -> AnisotropicExchangeData | None:
    """Build an `AnisotropicExchangeData` node, if present in the pickle.

    Parameters
    ----------
    spin_io : dict
        A TB2J results dictionary, as returned by `_parse_spin_io_dict`.

    Returns
    -------
    AnisotropicExchangeData or None
        The resulting node, not yet stored, or `None` if TB2J did not
        compute anisotropic exchange (`Jani_dict is None`) for this run.
    """
    jani_dict = spin_io.get("Jani_dict")
    if jani_dict is None:
        return None
    return _build_pair_data(
        AnisotropicExchangeData,
        jani_dict,
        spin_io["distance_dict"],
        "J_tensor",
        ANISOTROPIC_EXCHANGE_UNITS,
    )


def _build_magnetic_moments(spin_io: dict) -> ArrayData | None:
    """Build an `ArrayData` of per-atom magnetic moment vectors, if present.

    Parameters
    ----------
    spin_io : dict
        A TB2J results dictionary, as returned by `_parse_spin_io_dict`.

    Returns
    -------
    ArrayData or None
        A node with `site_index`/`moments` arrays, or `None` if TB2J did not
        report per-atom moments (`spinat`) for this run.
    """
    spinat = spin_io.get("spinat")
    if spinat is None:
        return None

    data = ArrayData()
    data.set_array("site_index", numpy.arange(len(spinat)))
    data.set_array("moments", numpy.asarray(spinat, dtype=float))
    return data


class TB2JParser(Parser):
    """The main TB2J AiiDA Parser."""

    def parse(self, **kwargs) -> ExitCode:
        """Parse the output from a TB2J calculation."""
        filename = WannierTB2JCalculation._PICKLE_FILE
        filepath = pathlib.Path(kwargs["retrieved_temporary_folder"]) / filename
        if not filepath.is_file():
            return self.exit_codes.ERROR_OUTPUT_PICKLE_MISSING

        pickle_bytes = filepath.read_bytes()

        with filepath.open("rb") as handle:
            self.out(
                "TB2J_pickle_file",
                SinglefileData(
                    file=handle,
                    filename=filename,
                    label="TB2J Results File",
                    description="Python pickle file containing results from TB2J.",
                ),
            )

        try:
            spin_io = _parse_spin_io_dict(pickle_bytes)
        except ValueError:
            return self.exit_codes.ERROR_OUTPUT_PICKLE_CORRUPT

        self.out("exchange_couplings", _build_exchange_coupling_data(spin_io))

        magnetic_moments = _build_magnetic_moments(spin_io)
        if magnetic_moments is not None:
            self.out("magnetic_moments", magnetic_moments)

        dmi_vectors = _build_dmi_vector_data(spin_io)
        if dmi_vectors is not None:
            self.out("dmi_vectors", dmi_vectors)

        anisotropic_exchange = _build_anisotropic_exchange_data(spin_io)
        if anisotropic_exchange is not None:
            self.out("anisotropic_exchange", anisotropic_exchange)

        return ExitCode(0)
