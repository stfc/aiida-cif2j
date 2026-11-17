"""The core TB2J output parsers."""

import pathlib
import pickle

import numpy
from aiida.engine import ExitCode
from aiida.orm import ArrayData, SinglefileData
from aiida.parsers import Parser

from aiida_cif2j.calculations.wannier_tb2j import WannierTB2JCalculation
from aiida_cif2j.data.exchange_coupling import UNITS, ExchangeCouplingData


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


def _build_exchange_coupling_data(spin_io: dict) -> ExchangeCouplingData:
    """Build an `ExchangeCouplingData` node from a TB2J results dictionary.

    One row is written per `exchange_Jdict` key, matching TB2J's own
    `exchange.out` reporting convention (no deduplication of
    mirrored-direction pairs).

    Parameters
    ----------
    spin_io : dict
        A TB2J results dictionary, as returned by `_parse_spin_io_dict`.

    Returns
    -------
    ExchangeCouplingData
        The resulting node, not yet stored.
    """
    exchange_jdict = spin_io["exchange_Jdict"]
    distance_dict = spin_io["distance_dict"]

    site_i = []
    site_j = []
    r_vectors = []
    distances = []
    distance_vectors = []
    j_iso = []
    for (r_vector, i, j), j_value in exchange_jdict.items():
        distance_vector, distance = distance_dict[(r_vector, i, j)]
        site_i.append(i)
        site_j.append(j)
        r_vectors.append(r_vector)
        distances.append(distance)
        distance_vectors.append(distance_vector)
        j_iso.append(j_value)

    data = ExchangeCouplingData()
    data.set_array("site_i", numpy.array(site_i, dtype=int))
    data.set_array("site_j", numpy.array(site_j, dtype=int))
    data.set_array("R", numpy.array(r_vectors, dtype=int))
    data.set_array("distance", numpy.array(distances, dtype=float))
    data.set_array("distance_vector", numpy.array(distance_vectors, dtype=float))
    data.set_array("J_iso", numpy.array(j_iso, dtype=float))
    data.base.attributes.set("units", UNITS)
    return data


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

        return ExitCode(0)
