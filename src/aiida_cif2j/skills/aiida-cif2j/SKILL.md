---
name: aiida-cif2j
description: >-
  Set up, submit, and troubleshoot magnetic exchange interaction calculations with TB2J
  through AiiDA using the aiida-cif2j plugin. Use when the user wants to run a TB2J
  calculation from existing Wannier90 outputs, run the full structure-to-exchange-couplings
  pipeline (Quantum ESPRESSO + Wannier90 + TB2J) via `WannierTB2JWorkChain`
  (`cif2j.wannier_tb2j`), build the `cif2j.wannier_tb2j` calcjob's `parameters` input,
  interpret its outputs (`ExchangeCouplingData`, `DMIVectorData`,
  `AnisotropicExchangeData`, magnetic moments) or exit codes, use the `cif2j wannier90`
  CLI commands, or asks about the aiida_cif2j.mcp tools (describe_cif2j_calcjob,
  submit_cif2j_job, describe_wannier_tb2j_workflow, submit_wannier_tb2j_workflow).
---

# aiida-cif2j

`aiida-cif2j` wraps [TB2J](https://github.com/mailhexu/TB2J)'s `wann2J.py` as an AiiDA
`CalcJob` (entry point `cif2j.wannier_tb2j`), computing magnetic exchange parameters from
a Wannier90 tight-binding Hamiltonian, so TB2J runs get full AiiDA data provenance. A
higher-level WorkChain (same entry point name, `cif2j.wannier_tb2j`) additionally
orchestrates Quantum ESPRESSO + Wannier90 ahead of it, so the whole pipeline can be run
from just a structure.

## Prerequisites

An AiiDA profile, a configured `Computer`, and a `Code` with
`default_calc_job_plugin: cif2j.wannier_tb2j` pointing at a compiled `wann2J.py`
executable (from TB2J) are required before anything can be submitted. If none exists
yet, configure one with a YAML file and `verdi code create core.code.installed`:

```yaml
label: tb2j
description: Wannier90 -> TB2J
computer: localhost
filepath_executable: wann2J.py
default_calc_job_plugin: cif2j.wannier_tb2j
use_double_quotes: false
with_mpi: false
prepend_text: ''
append_text: ''
```

```bash
verdi code create core.code.installed --config tb2j.yml -n
```

For the full Wannier90 -> TB2J workflow, `pw.x`/`pw2wannier90.x`/`wannier90.x` codes
(Quantum ESPRESSO + Wannier90) must also be configured, and the optional
`aiida-wannier90`/`aiida-wannier90-workflows` third-party packages installed — neither is
on PyPI, so install the pinned versions this plugin is developed against with:

```bash
cif2j wannier90 install
```

**Cross-computer constraint:** AiiDA cannot copy the intermediate files `wannier90.x`
reads directly between two different remote machines, so the `pw2wannier90` and
`wannier90` codes must be configured on the *same* AiiDA computer, or the
`Wannier90Calculation` step will hang and eventually fail.
`WannierTB2JWorkChain.get_builder_from_protocol` logs a warning if it detects this
misconfiguration, but does not refuse to build the inputs.

## Three ways to submit a job

**Prefer the MCP tools if connected to an `aiida-mcp` server.** There are two
describe/submit pairs — pick the one that fits the task:

| Task | Tools |
|---|---|
| TB2J step only, from an existing Wannier90 calculation's retrieved output | `describe_cif2j_calcjob` / `submit_cif2j_job` |
| Full pipeline from a structure file (QE SCF/NSCF + Wannier90 + TB2J) | `describe_wannier_tb2j_workflow` / `submit_wannier_tb2j_workflow` |

The workflow tool pair is only registered if `aiida-wannier90-workflows` and
`aiida-quantumespresso` are also installed (see `cif2j wannier90 install` above) — call
`rescan_plugins` on the aiida-mcp server after installing them if it was already
running. Call the matching `describe_*` tool first to confirm current inputs/outputs/exit
codes, then the matching `submit_*` tool, then follow up with aiida-mcp's own
`get_process` / `get_process_report` to poll status and see output.

`submit_cif2j_job`'s `parameters` and `structure` each take exactly one of `path` (file
on the server's machine), `text` (raw file contents), or `pk` (existing node).
`submit_wannier_tb2j_workflow`'s `structure` takes the same shape; its `codes` is a dict
keyed by `pw`, `pw2wannier90`, `wannier90`, `tb2j`, and optionally `projwfc`/`open_grid`
(code label or PK), with `tb2j` required.

**Or use the `cif2j wannier90` CLI**, which drives the full workflow the same way the
`submit_wannier_tb2j_workflow` MCP tool does, without writing a script:

```bash
cif2j wannier90 submit structure.mcif \
    --pw-code qe-pw@localhost \
    --pw2wannier90-code qe-pw2wannier90@localhost \
    --wannier90-code wannier90@localhost \
    --tb2j-code tb2j@localhost \
    --pseudo-family SSSP/1.3/PBE/efficiency
```

Useful options: `--spin-type` (`none`/`collinear`/`non_collinear`/`spin_orbit`, default
`collinear`), `--electronic-type` (`metal`/`insulator`, default `metal`),
`--projection-type` (default `atomic_projectors_qe`), `--magnetic-element` (repeatable),
`--tb2j-parameters`/`--tb2j-options` (inline JSON or `@path/to/file.json`), `--dry-run`
(build and print inputs without submitting), `--group` (add the submitted node to an
AiiDA group). Run `cif2j wannier90 submit --help` for the full list.

**Otherwise, write an AiiDA script** using the builder API. TB2J from an existing
non-collinear/spin-orbit Wannier90 calculation:

```python
from aiida import load_profile
from aiida.engine import run
from aiida.orm import Dict, List, load_code, load_node

load_profile("username")

wannier90_calc = load_node(12345)  # a finished Wannier90Calculation

builder = load_code("tb2j").get_builder()
builder.structure = wannier90_calc.inputs.structure
builder.wannier_folder = wannier90_calc.outputs.retrieved
builder.elements = List(["Fe"])
builder.parameters = Dict({"efermi": 6.5, "kmesh": [5, 5, 5]})

results, node = run.get_node(builder)
```

For a collinear, spin-polarised calculation, supply `wannier_folder_up` and
`wannier_folder_down` instead of `wannier_folder`. The full pipeline from a structure:

```python
from aiida import load_profile
from aiida.orm import SinglefileData
from aiida.plugins import WorkflowFactory
from aiida.engine import run
from aiida_quantumespresso.common.types import ElectronicType, SpinType

load_profile("username")

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
```

`magnetic_elements` and `tb2j_parameters.efermi` are auto-detected/auto-filled when not
given explicitly — pass them to `get_builder_from_protocol` (or the equivalent MCP/CLI
arguments) to fix them.

## Calcjob inputs

- `structure`: either a `StructureData` (written out as `POSCAR`, and used to
  auto-derive `kmesh` from the cell) or a `SinglefileData` containing a direct,
  ASE-readable posfile (in which case `kmesh` must be given explicitly). Required unless
  `use_wannier_structure=True` with `kmesh` given explicitly.
- `use_wannier_structure` (`bool`, default `False`): if `True`, read atomic positions
  from the Wannier90 `.win` file (copied out of `wannier_folder`/`wannier_folder_up`)
  instead of writing a posfile. Requires the upstream `Wannier90Calculation` to have
  retrieved its `.win` file (`settings["additional_retrieve_list"] = ["*.win"]`).
- `elements` (`List`, required): magnetic elements (chemical symbols) to consider.
- `wannier_folder`: `retrieved` output of a single non-collinear/spin-orbit
  `Wannier90Calculation`. Mutually exclusive with `wannier_folder_up`/
  `wannier_folder_down` (exactly one of the two forms is required).
- `wannier_folder_up` / `wannier_folder_down`: `retrieved` outputs of the spin-up/
  spin-down `Wannier90Calculation` runs, for a collinear spin-polarised calculation.
  Required together.
- `parameters` (`Dict`): TB2J command-line parameters — see below.

Each Wannier90 folder must contain either `aiida_tb.dat` (`write_tb=True` in the
Wannier90 parameters), or both `aiida_hr.dat` and `aiida_centres.xyz` (`write_hr=True`
and `write_xyz=True`).

## Building the `parameters` dict

`efermi` (`float`) is **required** — always supply it directly, or (via
`WannierTB2JWorkChain`) it is auto-filled from the preceding SCF calculation. Other
accepted keys: `kmesh` (`list[int]`, length 3 — derived from `supercell_size` and the
structure cell if omitted), `supercell_size` (`float`, default `20.0`, Angstrom), `rcut`,
`emin`, `emax`, `cutoff`, `ne` (`int`), `nz` (`int`), `e_batch_size` (`int`), `use_cache`
(`bool`), `orb_decomposition` (`bool`), `group_by_zeta` (`bool`), `write_dm` (`bool`),
`orth` (`bool`), `ibz` (`bool`), `use_gpu` (`bool`), `vectorize_energy` (`bool`),
`smearing` (`str`), `description` (`str`), `groupby` (`str`, one of `spin`/`orbital`),
`exclude_orbs` (`list[int]`), `index_magnetic_atoms` (`list[int]`), `mae_angles`
(`list[float]`). Any other key is rejected as unrecognised.

## Outputs

Always produced:

- `TB2J_pickle_file` (`SinglefileData`) — the raw `TB2J.pickle` results file.
- `exchange_couplings` (`ExchangeCouplingData`, an `ArrayData` subclass) — one row per
  physical magnetic-site pair, from TB2J's `exchange_Jdict`. Arrays: `site_i`, `site_j`
  (0-based site indices), `R` (lattice-translation vector, `(n_pairs, 3)`), `distance`
  (Angstrom), `distance_vector` (`(n_pairs, 3)`, Angstrom), `J_iso` (meV). Unlike TB2J's
  own `exchange.out` (which double-counts every bond from each site's perspective), this
  node deduplicates mirrored `(R, i, j)`/`(-R, j, i)` pairs, averaging the two
  directions' values — safe because `J_iso` is scalar with `J_ij == J_ji`.

Conditionally produced, only if TB2J computed them for the run:

- `magnetic_moments` (`ArrayData`, keys `site_index`/`moments`) — if TB2J reported
  per-atom moments (`spinat`).
- `dmi_vectors` (`DMIVectorData`) — if TB2J computed Dzyaloshinskii-Moriya interactions
  (`dmi_ddict`). Same row layout as `ExchangeCouplingData` plus `dmi_vector`
  (`(n_pairs, 3)`, meV) instead of `J_iso`. Built from TB2J's own `dmi_ddict` keys
  un-deduplicated (DMI is antisymmetric, `D_ij == -D_ji`, so mirrored pairs are not
  equivalent and both are kept).
- `anisotropic_exchange` (`AnisotropicExchangeData`) — if TB2J computed anisotropic
  exchange (`Jani_dict`). Same row layout plus `J_tensor` (`(n_pairs, 3, 3)`, meV)
  instead of `J_iso`, also kept un-deduplicated.

`dmi_ddict`/`Jani_dict` may cover a different set of pairs than `exchange_Jdict`, so
`dmi_vectors`/`anisotropic_exchange` are built from their own keys, not
`exchange_couplings`'s.

## Exit codes

Calcjob (`cif2j.wannier_tb2j`):

| Code | Name | Meaning |
|---|---|---|
| 300 | `ERROR_OUTPUT_PICKLE_MISSING` | The retrieved folder does not contain `TB2J.pickle` — check the job actually ran. |
| 301 | `ERROR_OUTPUT_PICKLE_CORRUPT` | `TB2J.pickle` could not be unpickled into the expected TB2J results dict. |

`WannierTB2JWorkChain` (same entry point, workflow-level failures):

| Code | Name | Meaning |
|---|---|---|
| 420 | `ERROR_WANNIER90_WC` | The `Wannier90BandsWorkChain` step failed. |
| 421 | `ERROR_TB2J_PLUGIN` | The TB2J calculation step failed (see the calcjob exit codes above on that step's own node). |
| 422 | `ERROR_MISSING_WANNIER_OUTPUTS` | `Wannier90BandsWorkChain` finished but exposed neither a `wannier90` output (non-collinear/SOC) nor both `wannier90_up`/`wannier90_down` (collinear spin-polarised). |
| 423 | `ERROR_MISSING_FERMI_ENERGY` | `tb2j.parameters.efermi` was not given and could not be auto-filled from `scf.output_parameters`. |
| 424 | `ERROR_MISSING_MAGNETIC_ELEMENTS` | `magnetic_elements` was not given and could not be auto-detected from the resolved structure. |

When a job fails, load the relevant node and inspect it (`verdi calcjob outputcat <pk>`,
`verdi process report <pk>`) before guessing further; call `describe_cif2j_calcjob` /
`describe_wannier_tb2j_workflow` for the current exit code list rather than assuming the
numbers above still apply.
