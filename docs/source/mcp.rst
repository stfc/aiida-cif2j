MCP integration
================

`aiida-mcp <https://github.com/stfc/aiida-mcp>`_ is a
`Model Context Protocol <https://modelcontextprotocol.io>`_ server that lets an MCP
client, such as an AI assistant, inspect an AiiDA database and submit calculations.
``aiida-cif2j`` ships its own integration module, ``aiida_cif2j.mcp``, which exposes
two pairs of tools.

Installing the optional ``mcp`` extra:

.. code-block:: bash

   pip install "aiida-cif2j[mcp]"

pulls in aiida-mcp and registers ``aiida_cif2j.mcp`` under its ``aiida_mcp.plugins``
entry point group. Any aiida-mcp server running in the same environment then
automatically exposes ``describe_cif2j_calcjob`` and ``submit_cif2j_job``. The second
pair, ``describe_wannier_tb2j_workflow`` and ``submit_wannier_tb2j_workflow``, are only
registered if ``aiida-wannier90-workflows`` and ``aiida-quantumespresso`` are also
installed (see :ref:`optional-wannier90-workflows`) — these are not published on PyPI,
so having the ``mcp`` extra installed does not by itself guarantee those two tools are
present; call ``rescan_plugins`` on the aiida-mcp server after installing them if the
server was already running.

``submit_cif2j_job``
----------------------

The low-level TB2J step. It reads an existing Wannier90 calculation's retrieved output
folder directly, so it is only useful once that Wannier90 calculation has already run.
For the full pipeline from a structure file, use ``submit_wannier_tb2j_workflow``
instead.

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Argument
     - Meaning
   * - ``code``
     - Label (e.g. ``tb2j@localhost``) or PK of the TB2J code.
   * - ``elements``
     - Magnetic elements for which the exchange interaction is considered.
   * - ``parameters``
     - TB2J command-line parameters as a dict of parameters (must include ``efermi``),
       or the path/text/PK of an existing ``Dict`` node.
   * - ``structure``
     - The structure, as a path, text, or PK of a ``StructureData`` or
       ``SinglefileData`` node. Required unless ``use_wannier_structure`` is true and
       ``kmesh`` is given explicitly in ``parameters``.
   * - ``use_wannier_structure``
     - If true, read atomic positions from the Wannier90 ``.win`` file instead of
       writing a POSCAR/posfile from ``structure``. Default false.
   * - ``wannier_folder``
     - PK of the ``retrieved`` ``FolderData`` of a single non-collinear/spin-orbit
       Wannier90 calculation. Mutually exclusive with ``wannier_folder_up``/
       ``wannier_folder_down``.
   * - ``wannier_folder_up``
     - PK of the ``retrieved`` ``FolderData`` of the spin-up Wannier90 calculation.
       Requires ``wannier_folder_down`` to also be given.
   * - ``wannier_folder_down``
     - PK of the ``retrieved`` ``FolderData`` of the spin-down Wannier90 calculation.
       Requires ``wannier_folder_up`` to also be given.
   * - ``num_machines``
     - Machines to run on. Default 1.
   * - ``num_mpiprocs_per_machine``
     - MPI processes per machine. Default 1.
   * - ``label``
     - Optional label to set on the calcjob node.
   * - ``description``
     - Optional description to set on the calcjob node.

Example arguments:

.. code-block:: json

   {
     "code": "tb2j@localhost",
     "elements": ["Fe"],
     "parameters": {"parameters": {"efermi": 0.0}},
     "structure": {"pk": 123},
     "wannier_folder": 456
   }

The inputs are checked against the calcjob definition before anything is stored — a bad
input returns an error and creates no nodes. On success the tool returns the process PK
and the PKs of the input nodes; follow the job with aiida-mcp's ``get_process`` and
``get_process_report`` tools.

.. _optional-wannier90-workflows:

``submit_wannier_tb2j_workflow``
-----------------------------------

The full pipeline: Quantum ESPRESSO SCF/NSCF, Wannierisation, and TB2J in one go,
starting from a structure file. Wraps
``WannierTB2JWorkChain.get_builder_from_protocol`` — see :doc:`introduction` for
installing its optional ``aiida-wannier90``/``aiida-wannier90-workflows``
dependencies.

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Argument
     - Meaning
   * - ``codes``
     - Code label or PK for each step, keyed by ``pw``, ``pw2wannier90``,
       ``wannier90``, ``tb2j``, and optionally ``projwfc``/``open_grid``. A ``tb2j``
       entry is required.
   * - ``structure``
     - The input structure, as a path, text, or PK of a ``StructureData``,
       ``MagneticStructureData``, or ``SinglefileData`` node (an ``MCIF`` file,
       parsed automatically).
   * - ``pseudo_family``
     - The pseudopotential family to use for the Wannier90/QE steps.
   * - ``protocol``
     - The protocol to use for the underlying Wannier90BandsWorkChain.
   * - ``spin_type``
     - One of ``none``, ``collinear``, ``non_collinear``, ``spin_orbit``. Default
       ``collinear``, which requires a ``MagneticStructureData`` structure.
   * - ``electronic_type``
     - One of ``metal``, ``insulator``, ``automatic``. Default ``metal``.
   * - ``projection_type``
     - One of ``analytic``, ``random``, ``scdm``, ``atomic_projectors_qe``. Default
       ``analytic``.
   * - ``wannier90_withmpi``
     - Whether to run ``wannier90.x`` under MPI. Default false, which also forces
       single-task resources for that step.
   * - ``magnetic_elements``
     - Elements for which the exchange interaction is considered. If not given,
       auto-detected from the resolved structure at runtime.
   * - ``tb2j_parameters``
     - TB2J command-line parameters (the ``tb2j.parameters`` input). ``efermi`` is
       auto-filled from the Wannier90 SCF output if omitted.
   * - ``tb2j_options``
     - ``metadata.options`` for the TB2J calculation step.
   * - ``label``
     - Optional label to set on the workflow node.
   * - ``description``
     - Optional description to set on the workflow node.

Example arguments:

.. code-block:: json

   {
     "codes": {
       "pw": "qe-pw@localhost",
       "pw2wannier90": "qe-pw2wannier90@localhost",
       "wannier90": "wannier90@localhost",
       "tb2j": "tb2j@localhost"
     },
     "structure": {"path": "/data/structure.mcif"},
     "pseudo_family": "SSSP/1.3/PBE/efficiency"
   }

Magnetic elements and the Fermi energy are auto-detected unless given explicitly. The
tool returns the process PK, the structure node's PK, and daemon state; follow the job
with ``get_process`` and ``get_process_report``.
