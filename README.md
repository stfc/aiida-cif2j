# AiiDA CIF2J

[![Release](https://img.shields.io/github/v/release/stfc/aiida-cif2j)](https://github.com/stfc/aiida-cif2j/releases)
[![PyPI](https://img.shields.io/pypi/v/aiida-cif2j)](https://pypi.org/project/aiida-cif2j/)

[![Docs status](https://github.com/stfc/aiida-cif2j/actions/workflows/ci-docs.yml/badge.svg?branch=main)](https://stfc.github.io/aiida-cif2j/)
[![Pipeline Status](https://github.com/stfc/aiida-cif2j/actions/workflows/ci-testing.yml/badge.svg?branch=main)](https://github.com/stfc/aiida-cif2j/actions)
[![Coverage Status]( https://coveralls.io/repos/github/stfc/aiida-cif2j/badge.svg?branch=main)](https://coveralls.io/github/stfc/aiida-cif2j?branch=main)

[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.18392782-blue.svg)](https://doi.org/10.5281/zenodo.18392782)


An [AiiDA](https://www.aiida.net) plugin for calculating magnetic exchange interactions.

## Installation

This plugin is available through PyPI and should be installed using [`pip`](https://pip.pypa.io/en/stable/) python package manager.

``` bash
pip install aiida-cif2j
```

## Requirements

To use this plugin a configured AiiDA profile and computer configuration are required, see the
[AiiDa documentation](https://aiida.readthedocs.io/projects/aiida-core/en/latest/intro/get_started.html)
for instructions on how to install and configure AiiDA.

### Optional: Wannier90 Workflows

This project exposes a WorkChain which will carry out the full process of calculating
Wannier functions for a structure which are then directly fed into TB2J.  This requires 
a third party package called aiida-wannier90-workflows. At present
the underlying aiida-wannier90-workflows package is not release on PyPI and must be installed
from the git repo as follows:

``` bash
pip install git+https://github.com/aiidateam/aiida-wannier90-workflows.git@v3.1.0
```
