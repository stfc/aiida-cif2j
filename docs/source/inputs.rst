Inputs, Parameters and Outputs
===============================

This page is the reference for the ``cif2j.wannier_tb2j`` calculation
(:class:`~aiida_cif2j.calculations.wannier_tb2j.WannierTB2JCalculation`). It wraps the ``wann2J.py`` script
from `TB2J <https://github.com/mailhexu/TB2J>`_, which computes magnetic exchange parameters from a
Wannier90 tight-binding Hamiltonian. It describes every input port, the valid keys accepted by the
``parameters`` dictionary input, the outputs produced, and the exit codes that may be returned. For complete
runnable scripts see :doc:`examples`, and for the higher level WorkChain that drives Wannier90 and TB2J
together see :doc:`workflows`.

Spinor vs. collinear inputs
----------------------------

``wann2J.py`` can be run in two mutually exclusive modes, selected by which Wannier90 output folder(s) are
given:

* **Non-collinear / spin-orbit** — provide a single ``wannier_folder``, the ``retrieved`` output of a
  non-collinear or spin-orbit ``Wannier90Calculation``.
* **Collinear, spin-polarised** — provide both ``wannier_folder_up`` and ``wannier_folder_down``, the
  ``retrieved`` outputs of the spin-up and spin-down ``Wannier90Calculation`` runs respectively.

Exactly one of these two forms must be supplied; mixing them, or supplying only one of
``wannier_folder_up``/``wannier_folder_down``, is rejected at submission time.

Each Wannier90 folder must contain either the ``aiida_tb.dat`` tight-binding file (``write_tb=True`` in the
Wannier90 parameters), or both ``aiida_hr.dat`` and ``aiida_centres.xyz`` (``write_hr=True`` and
``write_xyz=True``).

Supplying atomic positions
----------------------------

``wann2J.py`` needs an atomic-structure/position source. There are three ways to give it one via
``structure``/``use_wannier_structure``:

* **Default** — give ``structure`` as a ``StructureData``. It is converted and written out as a ``POSCAR``
  file, and also used to auto-derive ``kmesh`` from the unit cell dimensions when ``kmesh`` is not given
  explicitly in ``parameters``.
* **Direct posfile** — give ``structure`` as a ``SinglefileData`` containing any ASE-readable structure
  file. It is staged under its own filename and passed through to ``wann2J.py`` almost verbatim as the
  posfile. Since the cell is not parsed out of the file, ``kmesh`` **must** be given explicitly in
  ``parameters`` in this case.
* **Wannier90 ``.win`` fallback** — set ``use_wannier_structure=True``. No posfile is written at all;
  instead the Wannier90 ``.win`` file is copied out of the given ``wannier_folder``/``wannier_folder_up``,
  and ``wann2J.py`` falls back to reading atomic positions from it directly (an officially supported TB2J
  behaviour since v0.6.2, triggered whenever no readable file exists at the posfile path). This requires the
  upstream ``Wannier90Calculation``'s retrieve settings to include the ``.win`` input file, e.g.
  ``settings["additional_retrieve_list"] = ["*.win"]``. A ``StructureData`` may still be given alongside
  ``use_wannier_structure=True`` purely to auto-derive ``kmesh``; a ``SinglefileData`` ``structure`` may not
  be combined with ``use_wannier_structure=True``, and ``kmesh`` must be given explicitly whenever
  ``structure`` is absent or is not a ``StructureData``.

Input ports
-----------

.. list-table::
   :header-rows: 1
   :widths: 22 24 12 42

   * - Port
     - Type
     - Required
     - Description
   * - ``structure``
     - ``StructureData`` | ``SinglefileData``
     - no
     - Either a ``StructureData`` (default; written out as ``POSCAR``) or a ``SinglefileData`` containing a
       direct, ASE-readable posfile. Required unless ``use_wannier_structure=True`` (with ``kmesh`` given
       explicitly). See `Supplying atomic positions`_.
   * - ``use_wannier_structure``
     - ``bool``
     - no (default ``False``)
     - If ``True``, no posfile is written; instead the Wannier90 ``.win`` file is copied from the given
       ``wannier_folder``/``wannier_folder_up`` so ``wann2J.py`` reads positions from it directly. See
       `Supplying atomic positions`_.
   * - ``elements``
     - ``List``
     - yes
     - List of magnetic elements (chemical symbols) to consider.
   * - ``wannier_folder``
     - ``FolderData``
     - no
     - ``retrieved`` output of a single non-collinear/spin-orbit ``Wannier90Calculation``. Mutually
       exclusive with ``wannier_folder_up``/``wannier_folder_down``.
   * - ``wannier_folder_up``
     - ``FolderData``
     - no
     - ``retrieved`` output of the spin-up ``Wannier90Calculation``, for a collinear spin-polarised
       calculation. Requires ``wannier_folder_down`` to also be given.
   * - ``wannier_folder_down``
     - ``FolderData``
     - no
     - ``retrieved`` output of the spin-down ``Wannier90Calculation``, for a collinear spin-polarised
       calculation. Requires ``wannier_folder_up`` to also be given.
   * - ``parameters``
     - ``Dict``
     - no
     - Optional parameters for the TB2J calculation, passed through as ``wann2J.py`` command line flags.
       See `parameters`_.

Metadata / resources
~~~~~~~~~~~~~~~~~~~~~

The number of MPI processes is derived from ``metadata.options.resources``, which defaults to:

.. code-block:: python

    builder.metadata.options.resources = {
        "num_machines": 1,
        "num_mpiprocs_per_machine": 1,
    }

.. _parameters:

``parameters``
---------------

Optional keys that are translated into ``wann2J.py`` command line flags. ``efermi`` is **required** -- the
Fermi energy must always be supplied, either directly or (when using
:class:`~aiida_cif2j.workflows.wannier.WannierTB2JWorkChain`) auto-filled from the preceding SCF calculation.

.. list-table::
   :header-rows: 1
   :widths: 24 16 60

   * - Key
     - Type
     - Description
   * - ``efermi``
     - ``float`` | ``int``
     - **Required.** The Fermi energy.
   * - ``kmesh``
     - ``list[int]`` (3 values)
     - The k-point mesh used for the Green's function integration. If omitted, it is derived from
       ``supercell_size`` and the ``structure`` cell dimensions.
   * - ``supercell_size``
     - ``float`` | ``int``
     - Target real-space supercell size (in Angstrom) used to derive ``kmesh`` when it is not given
       explicitly. Defaults to ``20.0``. Must be positive.
   * - ``rcut``
     - ``float`` | ``int``
     - Real-space cutoff radius for the exchange calculation.
   * - ``emin``
     - ``float`` | ``int``
     - Lower energy bound for the contour integration.
   * - ``emax``
     - ``float`` | ``int``
     - Upper energy bound for the contour integration.
   * - ``cutoff``
     - ``float`` | ``int``
     - Cutoff used when truncating small exchange values.
   * - ``ne``
     - ``int``
     - Number of energy points along the contour.
   * - ``nz``
     - ``int``
     - Number of points for the complex energy contour.
   * - ``e_batch_size``
     - ``int``
     - Batch size for energy-point processing.
   * - ``use_cache``
     - ``bool``
     - Cache intermediate Green's function results to disk.
   * - ``orb_decomposition``
     - ``bool``
     - Decompose the exchange parameters by orbital.
   * - ``group_by_zeta``
     - ``bool``
     - Group orbitals by their :math:`\zeta` quantum number.
   * - ``write_dm``
     - ``bool``
     - Write the density matrix.
   * - ``orth``
     - ``bool``
     - Use Lowdin-orthogonalised orbitals.
   * - ``ibz``
     - ``bool``
     - Restrict the k-mesh to the irreducible Brillouin zone.
   * - ``use_gpu``
     - ``bool``
     - Enable GPU acceleration, if supported by the ``wann2J.py`` build.
   * - ``vectorize_energy``
     - ``bool``
     - Vectorise the energy-point loop.
   * - ``smearing``
     - ``str``
     - Smearing scheme used for the contour integration.
   * - ``description``
     - ``str``
     - Free-text description stored alongside the TB2J results.
   * - ``groupby``
     - ``str``
     - How exchange parameters are grouped; one of ``spin`` or ``orbital``.
   * - ``exclude_orbs``
     - ``list[int]``
     - Orbital indices to exclude from the calculation.
   * - ``index_magnetic_atoms``
     - ``list[int]``
     - Atom indices to treat as magnetic, overriding automatic detection from ``elements``.
   * - ``mae_angles``
     - ``list[float]`` | ``list[int]``
     - Angles used for a magnetic anisotropy energy (MAE) scan.

Any key not listed above is rejected as an unrecognised option.

Outputs
-------

.. list-table::
   :header-rows: 1
   :widths: 24 22 54

   * - Output
     - Type
     - Description
   * - ``TB2J_pickle_file``
     - ``SinglefileData``
     - The ``TB2J.pickle`` results file produced by ``wann2J.py``.

Exit codes
----------

.. list-table::
   :header-rows: 1
   :widths: 12 40 48

   * - Code
     - Label
     - Meaning
   * - ``300``
     - ``ERROR_OUTPUT_PICKLE_MISSING``
     - The retrieved folder does not contain the ``TB2J.pickle`` file.
