# AiiDA CIF2J

[![Release](https://img.shields.io/github/v/release/stfc/aiida-cif2j)](https://github.com/stfc/aiida-cif2j/releases)
[![PyPI](https://img.shields.io/pypi/v/aiida-cif2j)](https://pypi.org/project/aiida-cif2j/)

[![Docs status](https://github.com/stfc/aiida-cif2j/actions/workflows/ci-docs.yml/badge.svg?branch=main)](https://stfc.github.io/aiida-cif2j/)
[![Pipeline Status](https://github.com/stfc/aiida-cif2j/actions/workflows/ci-testing.yml/badge.svg?branch=main)](https://github.com/stfc/aiida-cif2j/actions)
[![Coverage Status](https://coveralls.io/repos/github/stfc/aiida-cif2j/badge.svg?branch=main)](https://coveralls.io/github/stfc/aiida-cif2j?branch=main)

<!-- [![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.18392782-blue.svg)](https://doi.org/10.5281/zenodo.18392782) -->

An [AiiDA](https://www.aiida.net) plugin for calculating magnetic exchange interactions.

## Installation

This plugin is available through PyPI and should be installed using [`pip`](https://pip.pypa.io/en/stable/) python package manager.

``` bash
pip install aiida-cif2j
```

### Optional: Wannier90 Workflows

This project exposes a WorkChain which will carry out the full process of calculating
Wannier functions for a structure which are then directly fed into TB2J. This requires
two third party packages, `aiida-wannier90` and `aiida-wannier90-workflows`. Neither is
currently released on PyPI, so they must be installed from their git repositories. This
plugin ships a CLI command to do this for you:

``` bash
cif2j wannier90 install
```

## Requirements

To use this plugin a configured AiiDA profile and computer are required, as well as a compiled
[`wann2J.py`](https://github.com/mailhexu/TB2J) executable (from TB2J). For more information on how to set
up AiiDA refer to the
[AiiDA documentation](https://aiida.readthedocs.io/projects/aiida-core/en/latest/intro/get_started.html).

### Setup

To configure the TB2J plugin you will need to create a new AiiDA code object. The following is an example
of a basic YAML configuration file for a TB2J code:

``` yaml
label: tb2j
description: Wannier90 -> TB2J
computer: localhost
filepath_executable: wann2J.py
default_calc_job_plugin: cif2j.wannier_tb2j
use_double_quotes: false
with_mpi: false
prepend_text: ""
append_text: ""
```

Write this to a file named `tb2j.yml` ensuring the value for `computer` matches the label of your computer
configured in the previous step. The code can then be configured by running:

``` bash
verdi code create core.code.installed --config tb2j.yml -n
```

If successful, this will create a new AiiDA code with the label `tb2j` which can then be used to run TB2J
calculations within the AiiDA framework.

> **NOTE**:
> The full Wannier90 -> TB2J workflow requires a `pw2wannier90.x` code and a `wannier90.x` code to be
> configured on the *same* AiiDA computer. AiiDA cannot copy the intermediate files that `wannier90.x` reads
> directly between two different remote machines, so running these two codes on different computers will
> cause the workflow to fail.

See the [documentation](https://stfc.github.io/aiida-cif2j/) for the full list of calculation inputs,
parameters and outputs, the higher level WorkChains, and complete runnable examples.

## Examples

The following submits the full Wannier90 -> TB2J workflow starting from an MCIF structure file: Quantum
ESPRESSO SCF and Wannierisation (via `aiida-wannier90-workflows`), followed directly by TB2J. This can be
run either from the command line:

``` bash
cif2j wannier90 submit structure.mcif \
    --pw-code qe-pw@localhost \
    --pw2wannier90-code qe-pw2wannier90@localhost \
    --wannier90-code wannier90@localhost \
    --tb2j-code tb2j@localhost \
    --pseudo-family SSSP/1.3/PBE/efficiency
```

or from a Python script / `verdi shell`:

``` python
from aiida.engine import run
from aiida.orm import SinglefileData
from aiida.plugins import WorkflowFactory

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
)

results, node = run.get_node(builder)
```

Magnetic elements and the Fermi energy are auto-detected in both cases, so neither needs to be supplied
explicitly. See the [examples documentation](https://stfc.github.io/aiida-cif2j/examples.html) for more,
including running TB2J directly from existing Wannier90 outputs and fixing magnetic elements/TB2J
parameters explicitly.


## License

[BSD 3-Clause License](LICENSE)

## Funding

Contributors to this project were funded by;

<div align="center">
    <a href="https://adalovelacecentre.ac.uk/">
        <img src="images/alc.svg" alt="ALC Logo" style="width: 30%">
    </a>
</div>