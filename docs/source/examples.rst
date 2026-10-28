Example Calculations
====================

The examples below use codes configured as described in :doc:`introduction`. For a full description of
every available input and its parameters, see :doc:`inputs` for the ``cif2j.wannier_tb2j`` calculation and
:doc:`workflows` for the combined WorkChain.

Each script can be run either as a standalone python file or directly within a ``verdi shell`` python
environment. When running inside a ``verdi shell`` the call to :func:`~aiida.manage.configuration.load_profile`
is not required.

TB2J from existing Wannier90 outputs
-------------------------------------

The following script runs a TB2J calculation directly from the ``retrieved`` output of a previously
completed, non-collinear/spin-orbit ``Wannier90Calculation``.

.. code-block:: python

    from aiida.engine import run
    from aiida.orm import load_code, load_node, Dict, List
    from aiida import load_profile

    load_profile("user_profile")  # Not required within a verdi shell environment

    wannier90_calc = load_node(12345)  # a finished Wannier90Calculation

    builder = load_code("tb2j").get_builder()
    builder.structure = wannier90_calc.inputs.structure
    builder.wannier_folder = wannier90_calc.outputs.retrieved
    builder.elements = List(["Fe"])
    builder.parameters = Dict({"efermi": 6.5, "kmesh": [5, 5, 5]})

    results, node = run.get_node(builder)

    print("Exit status = ", node.exit_status)
    print("Retrieved files = ", results["retrieved"].list_object_names())

For a collinear, spin-polarised calculation, supply ``wannier_folder_up`` and ``wannier_folder_down``
instead of ``wannier_folder``, pointing at the ``retrieved`` outputs of the spin-up and spin-down
``Wannier90Calculation`` runs respectively.

Full Wannier90 -> TB2J WorkChain
----------------------------------

The following script runs the complete workflow starting from an MCIF structure file: Quantum ESPRESSO SCF
and Wannierisation (via ``aiida-wannier90-workflows``), followed directly by TB2J. Magnetic elements and the
Fermi energy are auto-detected, so neither needs to be supplied explicitly.

.. code-block:: python

    from aiida.engine import run
    from aiida.orm import SinglefileData
    from aiida.plugins import WorkflowFactory
    from aiida_quantumespresso.common.types import ElectronicType, SpinType
    from aiida import load_profile

    load_profile("user_profile")  # Not required within a verdi shell environment

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

    results, node = run.get_node(builder)

    print("Retrieved files = ", results["retrieved"].list_object_names())

.. note::

   The ``pw2wannier90`` and ``wannier90`` codes passed to ``codes`` must be configured on the same AiiDA
   computer -- see :doc:`workflows` for why.

To fix the magnetic elements, the Fermi energy, or other TB2J options explicitly rather than relying on
auto-detection, pass ``magnetic_elements`` and/or ``tb2j_parameters`` to ``get_builder_from_protocol``:

.. code-block:: python

    builder = WannierTB2J.get_builder_from_protocol(
        codes={...},
        structure=structure,
        magnetic_elements=["Fe"],
        tb2j_parameters={"efermi": 6.5, "kmesh": [5, 5, 5]},
    )
