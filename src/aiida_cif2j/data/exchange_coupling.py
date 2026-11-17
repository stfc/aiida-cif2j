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


#: Units for `DMIVectorData`'s stored arrays.
DMI_UNITS = {"dmi_vector": "meV", "distance": "Ang", "distance_vector": "Ang"}

#: Units for `AnisotropicExchangeData`'s stored arrays.
ANISOTROPIC_EXCHANGE_UNITS = {
    "J_tensor": "meV",
    "distance": "Ang",
    "distance_vector": "Ang",
}


class DMIVectorData(ArrayData):
    """One row per magnetic-site-pair entry in a TB2J run's `dmi_ddict`.

    Only produced when TB2J computed Dzyaloshinskii-Moriya interactions for
    the run (`dmi_ddict is not None`); `dmi_ddict` may cover a different set
    of pairs than `exchange_Jdict`, so this is built from its own keys, not
    `ExchangeCouplingData`'s.

    Stored arrays (all length `n_pairs`, except `R`/`distance_vector`/
    `dmi_vector` which are `(n_pairs, 3)`):

    - `site_i`, `site_j`: 0-based magnetic-site indices of the pair.
    - `R`: the lattice-translation vector TB2J associates with this coupling.
    - `distance`: scalar distance between the two sites, in Angstrom.
    - `distance_vector`: cartesian vector from site `i` to site `j`, in
      Angstrom.
    - `dmi_vector`: the DMI vector `(Dx, Dy, Dz)`, in meV.
    """


class AnisotropicExchangeData(ArrayData):
    """One row per magnetic-site-pair entry in a TB2J run's `Jani_dict`.

    Only produced when TB2J computed anisotropic exchange for the run
    (`Jani_dict is not None`); `Jani_dict` may cover a different set of pairs
    than `exchange_Jdict`, so this is built from its own keys, not
    `ExchangeCouplingData`'s.

    Stored arrays (all length `n_pairs`, except `R`/`distance_vector` which
    are `(n_pairs, 3)`, and `J_tensor` which is `(n_pairs, 3, 3)`):

    - `site_i`, `site_j`: 0-based magnetic-site indices of the pair.
    - `R`: the lattice-translation vector TB2J associates with this coupling.
    - `distance`: scalar distance between the two sites, in Angstrom.
    - `distance_vector`: cartesian vector from site `i` to site `j`, in
      Angstrom.
    - `J_tensor`: the anisotropic exchange tensor, in meV.
    """
