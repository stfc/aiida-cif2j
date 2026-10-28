Introduction
============

Welcome to the `AiiDA <https://www.aiida.net>`_ CIF2J plugin documentation. This plugin provides an AiiDA
workflow plugin for calculating magnetic exchange interactions with
`TB2J <https://github.com/mailhexu/TB2J>`_, starting from Wannier functions produced by
`Wannier90 <http://www.wannier.org/>`_.

Quick Start
-----------

This plugin should be installed alongside the ``aiida-core`` package, typically using the
`pip <https://pip.pypa.io/en/stable/>`_ python package manager. The latest release is available from PyPI:

.. code-block:: bash

    pip install aiida-cif2j

Alternatively, to install the current development version from a local checkout of the source:

.. code-block:: bash

    cd aiida-cif2j
    pip install .

Optional: Wannier90 Workflows
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This project exposes :class:`~aiida_cif2j.workflows.wannier.WannierTB2JWorkChain`, a WorkChain which
carries out the full process of calculating Wannier functions for a structure which are then directly fed
into TB2J. This requires a third party package called ``aiida-wannier90-workflows``. At present the
underlying package is not released on PyPI and must be installed from the git repository as follows:

.. code-block:: bash

    pip install git+https://github.com/aiidateam/aiida-wannier90-workflows.git@v3.1.0

Requirements
~~~~~~~~~~~~~

To use this plugin a configured AiiDA profile and computer are required, as well as a compiled
`wann2J.py <https://github.com/mailhexu/TB2J>`_ executable (from TB2J). For more information on how to set
up AiiDA refer to the
`AiiDA documentation <https://aiida.readthedocs.io/projects/aiida-core/en/latest/intro/get_started.html>`_.

Setup
~~~~~

To configure the TB2J plugin you will need to create a new AiiDA code object. The following is an example
of a basic YAML configuration file for a TB2J code:

.. code-block:: yaml

    label: tb2j
    description: Wannier90 -> TB2J
    computer: localhost
    filepath_executable: wann2J.py
    default_calc_job_plugin: cif2j.wannier_tb2j
    use_double_quotes: false
    with_mpi: false
    prepend_text: ""
    append_text: ""

Write this to a file named ``tb2j.yml`` ensuring the value for ``computer`` matches the label of your
computer configured in the previous step. The code can then be configured by running:

.. code-block:: bash

    verdi code create core.code.installed --config tb2j.yml -n

If successful, this will create a new AiiDA code with the label ``tb2j`` which can then be used to run TB2J
calculations within the AiiDA framework.

.. important::

   The full Wannier90 -> TB2J workflow requires a ``pw2wannier90.x`` code and a ``wannier90.x`` code to be
   configured on the *same* AiiDA computer. AiiDA cannot copy the intermediate files that ``wannier90.x``
   reads directly between two different remote machines, so running these two codes on different computers
   will cause the workflow to fail. See :doc:`workflows` for more details.

See :doc:`inputs` for the full list of calculation inputs, parameters and outputs, :doc:`workflows` for the
higher level WorkChains, and :doc:`examples` for complete runnable scripts.
