"""AiiDA Data node for TB2J isotropic exchange-coupling parameters."""

from aiida.orm import ArrayData

#: Units for the stored arrays, as reported by TB2J itself.
UNITS = {"J_iso": "meV", "distance": "Ang", "distance_vector": "Ang"}


class ExchangeCouplingData(ArrayData):
    """One row per magnetic-site-pair entry in a TB2J run's `exchange_Jdict`.

    Matches TB2J's own reporting convention: one row per `exchange_Jdict` key,
    with no deduplication of mirrored-direction pairs (TB2J's own
    `exchange.out` output does not deduplicate them either).

    Stored arrays (all length `n_pairs`, except `R`/`distance_vector` which
    are `(n_pairs, 3)`):

    - `site_i`, `site_j`: 0-based magnetic-site indices of the pair.
    - `R`: the lattice-translation vector TB2J associates with this coupling.
    - `distance`: scalar distance between the two sites, in Angstrom.
    - `distance_vector`: cartesian vector from site `i` to site `j`, in
      Angstrom.
    - `J_iso`: isotropic exchange coupling, in meV.
    """
