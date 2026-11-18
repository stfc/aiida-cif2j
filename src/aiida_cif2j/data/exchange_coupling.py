"""AiiDA Data node for TB2J isotropic exchange-coupling parameters."""

from aiida.orm import ArrayData

#: Units for the stored arrays, as reported by TB2J itself.
UNITS = {"J_iso": "meV", "distance": "Ang", "distance_vector": "Ang"}


class ExchangeCouplingData(ArrayData):
    """One row per physical magnetic-site pair, from a TB2J run's `exchange_Jdict`.

    Unlike `DMIVectorData`/`AnisotropicExchangeData` (and unlike TB2J's own
    `exchange.out`, which double-counts every bond once from each site's
    perspective), `TB2JParser` deduplicates `exchange_Jdict`'s mirrored
    `(R, i, j)`/`(-R, j, i)` pairs before building this node - see
    `aiida_cif2j.parsers.tb2j._deduplicate_mirrored_pairs`. This is safe only
    because J_iso is a scalar with `J_ij == J_ji`; DMI/anisotropic exchange
    are antisymmetric/tensor-valued and are kept TB2J-faithful instead.

    Stored arrays (all length `n_pairs`, except `R`/`distance_vector` which
    are `(n_pairs, 3)`):

    - `site_i`, `site_j`: 0-based magnetic-site indices of the pair, in
      whichever of the two mirrored directions TB2J's `exchange_Jdict`
      happened to list first - the other direction's `(R, i, j)` is
      equivalent and not stored separately.
    - `R`: the lattice-translation vector TB2J associates with this coupling.
    - `distance`: scalar distance between the two sites, in Angstrom.
    - `distance_vector`: cartesian vector from site `i` to site `j`, in
      Angstrom.
    - `J_iso`: isotropic exchange coupling, in meV - averaged over both
      mirrored directions' values (see `_deduplicate_mirrored_pairs`).
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
