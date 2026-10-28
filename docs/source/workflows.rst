Workflows
=========

In addition to the low-level ``cif2j.wannier_tb2j`` calculation described in :doc:`inputs`, the plugin
provides a WorkChain that orchestrates a full Wannier90 + TB2J run starting from a structure. Registered
WorkChains can be loaded through the AiiDA :func:`~aiida.plugins.factories.WorkflowFactory` using their entry
point name:

.. list-table::
   :header-rows: 1
   :widths: 30 40 30

   * - Entry point
     - WorkChain
     - Purpose
   * - ``cif2j.wannier_tb2j``
     - :class:`~aiida_cif2j.workflows.wannier.WannierTB2JWorkChain`
     - Runs a ``Wannier90BandsWorkChain`` (Quantum ESPRESSO + Wannier90) followed by a TB2J calculation,
       to compute magnetic exchange interactions directly from a structure.

Wannier90 -> TB2J WorkChain
----------------------------

``cif2j.wannier_tb2j`` (:class:`~aiida_cif2j.workflows.wannier.WannierTB2JWorkChain`) chains together the
`aiida-wannier90-workflows <https://github.com/aiidateam/aiida-wannier90-workflows>`_
``Wannier90BandsWorkChain`` with the ``cif2j.wannier_tb2j`` calculation. It accepts a structure directly as
a CIF/MCIF file, auto-detects magnetic elements and the Fermi energy where possible, and exposes the full
input namespaces of both of its constituent processes.

Inputs
~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 26 48

   * - Input
     - Type
     - Description
   * - ``structure``
     - ``SinglefileData`` | ``StructureData``
     - **Required.** Either an MCIF/CIF file or an existing ``StructureData``/``MagneticStructureData``
       node.
   * - ``magnetic_elements``
     - ``List``
     - Elements for which the exchange interaction is considered. If omitted, auto-detected from the
       per-kind magnetic moments of a resolved ``MagneticStructureData``.
   * - (exposed)
     - namespace
     - All inputs of ``Wannier90BandsWorkChain`` (``scf``, ``nscf``, ``wannier90``, ``pw2wannier90``, ...)
       except ``structure``.
   * - ``tb2j``
     - namespace
     - ``code``, ``parameters`` and ``metadata`` of the ``cif2j.wannier_tb2j`` calculation (see
       :doc:`inputs`). ``tb2j.parameters.efermi`` may be omitted -- it is auto-filled from the SCF Fermi
       energy if not given.

Outputs
~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 22 52

   * - Output
     - Type
     - Description
   * - ``retrieved``
     - ``FolderData``
     - The retrieved folder from the TB2J calculation, containing ``TB2J.pickle``.

Exit codes
~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 12 36 52

   * - Code
     - Label
     - Meaning
   * - ``420``
     - ``ERROR_WANNIER90_WC``
     - The ``Wannier90BandsWorkChain`` step failed.
   * - ``421``
     - ``ERROR_TB2J_PLUGIN``
     - The TB2J calculation step failed.
   * - ``422``
     - ``ERROR_MISSING_WANNIER_OUTPUTS``
     - The ``Wannier90BandsWorkChain`` finished successfully but exposed neither a ``wannier90`` output
       (non-collinear/SOC) nor both ``wannier90_up`` and ``wannier90_down`` outputs (collinear
       spin-polarised).
   * - ``423``
     - ``ERROR_MISSING_FERMI_ENERGY``
     - ``efermi`` was not given in ``tb2j.parameters`` and could not be read from the
       ``Wannier90BandsWorkChain``'s ``scf.output_parameters`` output to fill it in automatically.
   * - ``424``
     - ``ERROR_MISSING_MAGNETIC_ELEMENTS``
     - ``magnetic_elements`` was not given, and could not be auto-detected from the resolved ``structure``.

.. important::

   AiiDA's transport layer cannot copy files directly between two different remote machines. The
   ``wannier90.x`` step reads the ``pw2wannier90.x`` outputs via a remote-folder copy rather than
   re-uploading them, so the ``pw2wannier90`` and ``wannier90`` codes must be configured on the **same**
   AiiDA computer, or the ``Wannier90Calculation`` step will hang and eventually fail.
   :meth:`~aiida_cif2j.workflows.wannier.WannierTB2JWorkChain.get_builder_from_protocol` logs a warning if
   it detects this misconfiguration.

Building inputs with ``get_builder_from_protocol``
----------------------------------------------------

Rather than populating every exposed namespace by hand, use
:meth:`~aiida_cif2j.workflows.wannier.WannierTB2JWorkChain.get_builder_from_protocol` to build a pre-populated
``ProcessBuilder`` from a small set of high level options, forwarding most of its arguments on to
``Wannier90BandsWorkChain.get_builder_from_protocol``.

.. code-block:: python

    from aiida.orm import load_code, SinglefileData
    from aiida.plugins import WorkflowFactory
    from aiida_quantumespresso.common.types import ElectronicType, SpinType
    from aiida import load_profile

    load_profile("user_profile")

    WannierTB2J = WorkflowFactory("cif2j.wannier_tb2j")

    builder = WannierTB2J.get_builder_from_protocol(
        codes={
            "pw": "qe-pw@localhost",
            "pw2wannier90": "qe-pw2wannier90@localhost",
            "wannier90": "wannier90@localhost",
            "tb2j": "tb2j@localhost",
        },
        structure=SinglefileData(file="/absolute/path/to/structure.mcif"),
        pseudo_family="SSSP/1.3/PBE/efficiency",
        spin_type=SpinType.COLLINEAR,
        electronic_type=ElectronicType.METAL,
    )

See the :meth:`API reference
<aiida_cif2j.workflows.wannier.WannierTB2JWorkChain.get_builder_from_protocol>` for the complete list of
accepted arguments, including ``magnetic_elements``, ``tb2j_parameters`` and ``tb2j_options``. For the full
submission script see :doc:`examples`.
