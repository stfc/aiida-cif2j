Agent Skill
===========

`aiida-cif2j` ships an `Agent Skill <https://www.anthropic.com/news/skills>`_ — a
``SKILL.md`` file describing how to set up, submit and troubleshoot TB2J magnetic
exchange calculations with this plugin, for AI assistants (such as Claude Code) that
support the format. It covers configuring a TB2J code (and the optional Wannier90
third-party plugins), the three submission paths (a plain AiiDA script, the ``cif2j
wannier90`` CLI, or the :doc:`mcp` tools), building the TB2J ``parameters`` dict, the
calcjob's and ``WannierTB2JWorkChain``'s outputs and exit codes, and the cross-computer
constraint on the ``pw2wannier90``/``wannier90`` codes.

It is installed alongside the package at
``aiida_cif2j/skills/aiida-cif2j/SKILL.md``. The ``cif2j`` command installs it into your
assistant's skills directory:

.. code-block:: bash

   cif2j skills install

This copies the skill into ``~/.claude/skills/`` by default. Pass a directory to install
somewhere else, e.g. a project-local ``.claude/skills/``:

.. code-block:: bash

   cif2j skills install .claude/skills
