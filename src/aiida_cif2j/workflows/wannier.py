"""AiiDA WorkChain for combining Wannier90 and TB2J into a single workflow."""

import logging
from collections.abc import Mapping

from aiida import orm
from aiida.common import AttributeDict
from aiida.engine import ExitCode, ProcessBuilder, ToContext, WorkChain, if_
from aiida.orm import Dict, FolderData, List, SinglefileData, StructureData
from aiida_quantumespresso.common.types import ElectronicType, SpinType
from aiida_wannier90_workflows.common.types import WannierProjectionType
from aiida_wannier90_workflows.data.structure import MagneticStructureData
from aiida_wannier90_workflows.workflows.bands import Wannier90BandsWorkChain

from aiida_cif2j.calculations.utils import (
    detect_magnetic_elements,
    parse_magnetic_structure,
)
from aiida_cif2j.calculations.wannier_tb2j import WannierTB2JCalculation
from aiida_cif2j.workflows.utils import (
    collinear_magnetic_moments,
    total_magnetization,
    validate_chemical_symbols,
)

_LOGGER = logging.getLogger(__name__)


class WannierTB2JWorkChain(WorkChain):
    """WorkChain linking Wannier90BandsWorkChain and TB2J."""

    @classmethod
    def define(cls, spec):
        """
        Define the inputs, outputs and outline of the WorkChain.

        Parameters
        ----------
        spec : WorkChainSpec
            The AiiDA Process specification object for the WorkChain.
        """
        super().define(spec)

        spec.expose_inputs(Wannier90BandsWorkChain, exclude=("structure",))
        spec.expose_inputs(
            WannierTB2JCalculation,
            namespace="tb2j",
            include=("code", "parameters", "metadata"),
            namespace_options={
                "help": "Code and input parameters for the TB2J calculation.",
                "validator": None,
            },
        )
        # 'efermi' is normally required, but this WorkChain can auto-fill it from the
        # Wannier90BandsWorkChain's SCF output, so that check must not run here.
        spec.inputs["tb2j"]["parameters"].validator = None

        spec.input(
            "structure",
            valid_type=(SinglefileData, StructureData),
            required=True,
            help="The input structure either as an 'MCIF' file or an existing AiiDA "
            "StructureData/MagneticStructuredata node.",
        )
        spec.input(
            "magnetic_elements",
            valid_type=List,
            validator=validate_chemical_symbols,
            required=False,
            help="Elements for which the exchange interaction is considered.",
        )

        spec.output("retrieved", valid_type=FolderData, required=True)

        spec.exit_code(
            420, "ERROR_WANNIER90_WC", message="The Wannier90BandsWorkChain failed."
        )
        spec.exit_code(421, "ERROR_TB2J_PLUGIN", message="The TB2J calculation failed.")
        spec.exit_code(
            422,
            "ERROR_MISSING_WANNIER_OUTPUTS",
            message=(
                "The Wannier90BandsWorkChain finished successfully but exposed "
                "neither a 'wannier90' output (non-collinear/SOC) nor both "
                "'wannier90_up' and 'wannier90_down' outputs (collinear "
                "spin-polarised)."
            ),
        )
        spec.exit_code(
            423,
            "ERROR_MISSING_FERMI_ENERGY",
            message=(
                "'efermi' was not given in 'tb2j.parameters' and could not be read "
                "from the Wannier90BandsWorkChain's 'scf.output_parameters' output "
                "to fill it in automatically."
            ),
        )
        spec.exit_code(
            424,
            "ERROR_MISSING_MAGNETIC_ELEMENTS",
            message=(
                "'magnetic_elements' was not given, and could not auto-detect from "
                "the resolved 'structure'."
            ),
        )

        spec.outline(  # type: ignore
            if_(cls._should_parse_structure_from_file)(cls.parse_structure_from_file),
            if_(cls._should_auto_detect_magnetic_elements)(
                cls.auto_detect_magnetic_elements
            ),
            cls.run_wannier90,
            cls.run_tb2j,
            cls.collate_results,
        )
        return

    def parse_structure_from_file(self) -> None:
        """Parse the input CIF/MCIF structure file into `ctx.structure`."""
        self.ctx.structure = parse_magnetic_structure(self.inputs.structure)
        return

    def auto_detect_magnetic_elements(self):
        """
        Auto-detect magnetic elements from the resolved input structure.

        Returns
        -------
        ExitCode or None
            `ERROR_MISSING_MAGNETIC_ELEMENTS` if the resolved structure is not a
            `MagneticStructureData`, or no magnetic elements could be detected on
            it; `None` otherwise.
        """
        structure = (
            self.ctx.structure
            if self._should_parse_structure_from_file()
            else self.inputs.structure
        )
        if not isinstance(structure, MagneticStructureData):
            return self.exit_codes.ERROR_MISSING_MAGNETIC_ELEMENTS

        self.ctx.magnetic_elements = detect_magnetic_elements(structure)

        if not self.ctx.magnetic_elements:
            return self.exit_codes.ERROR_MISSING_MAGNETIC_ELEMENTS
        return None

    def run_wannier90(self):
        """
        Submit the Wannier90BandsWorkChain step of the workflow.

        Returns
        -------
        ToContext
            Stores the submitted process under the `wannier90` context key.
        """
        inputs = AttributeDict(self.exposed_inputs(Wannier90BandsWorkChain))
        inputs["structure"] = (
            self.ctx.structure
            if self._should_parse_structure_from_file()
            else self.inputs.structure
        )
        running = self.submit(Wannier90BandsWorkChain, **inputs)
        self.report(
            f"Launched Wannier90BandsWorkChain<{running.pk}> to perform the "
            "Wannierization."
        )

        return ToContext(wannier90=running)

    def run_tb2j(self):
        """
        Build the TB2J calculation inputs from the Wannier90 outputs and submit.

        Returns
        -------
        ToContext or ExitCode
            Stores the submitted process under the `tb2j_step` context key, or one
            of `ERROR_WANNIER90_WC`, `ERROR_MISSING_WANNIER_OUTPUTS`,
            `ERROR_MISSING_FERMI_ENERGY` if a prerequisite check fails.
        """
        if not self.ctx.wannier90.is_finished_ok:
            return self.exit_codes.ERROR_WANNIER90_WC

        wannier90_outputs = self.ctx.wannier90.outputs
        tb2j_inputs = AttributeDict(
            self.exposed_inputs(WannierTB2JCalculation, namespace="tb2j")
        )
        tb2j_inputs["elements"] = (
            self.inputs.magnetic_elements
            if "magnetic_elements" in self.inputs
            else self.ctx.magnetic_elements
        )
        if "primitive_structure" in wannier90_outputs:
            tb2j_inputs["structure"] = wannier90_outputs.primitive_structure
        else:
            tb2j_inputs["structure"] = (
                self.ctx.structure
                if self._should_parse_structure_from_file()
                else self.inputs.structure
            )

        if "wannier90" in wannier90_outputs:
            tb2j_inputs["wannier_folder"] = wannier90_outputs.wannier90.retrieved
        elif (
            "wannier90_up" in wannier90_outputs
            and "wannier90_down" in wannier90_outputs
        ):
            tb2j_inputs["wannier_folder_up"] = wannier90_outputs.wannier90_up.retrieved
            tb2j_inputs["wannier_folder_down"] = (
                wannier90_outputs.wannier90_down.retrieved
            )
        else:
            return self.exit_codes.ERROR_MISSING_WANNIER_OUTPUTS

        parameters = (
            tb2j_inputs["parameters"].get_dict() if "parameters" in tb2j_inputs else {}
        )
        if "efermi" not in parameters:
            if (
                "scf" not in wannier90_outputs
                or "output_parameters" not in wannier90_outputs.scf
            ):
                return self.exit_codes.ERROR_MISSING_FERMI_ENERGY
            scf_parameters = wannier90_outputs.scf.output_parameters.get_dict()
            if "fermi_energy" not in scf_parameters:
                return self.exit_codes.ERROR_MISSING_FERMI_ENERGY
            parameters["efermi"] = scf_parameters["fermi_energy"]
        tb2j_inputs["parameters"] = Dict(dict=parameters)

        running = self.submit(WannierTB2JCalculation, **tb2j_inputs)
        self.report(f"Launching WannierTB2JCalculation<{running.pk}>")

        return ToContext(tb2j_step=running)

    def collate_results(self):
        """
        Bring together the outputs from the full WorkChain.

        Returns
        -------
        ExitCode
            `ERROR_TB2J_PLUGIN` if the TB2J calculation failed, `ExitCode(0)`
            otherwise.
        """
        if not self.ctx.tb2j_step.is_finished_ok:
            return self.exit_codes.ERROR_TB2J_PLUGIN

        # if "exchange" in self.ctx.tb2j_step.outputs:
        #     self.out("exchange", self.ctx.tb2j_step.outputs.exchange)

        self.out("retrieved", self.ctx.tb2j_step.outputs.retrieved)

        # wannier90_outputs = self.ctx.wannier90.outputs
        # if "scf" in wannier90_outputs and (
        #     "output_parameters" in wannier90_outputs.scf
        # ):
        #     self.out("dft_parameters", wannier90_outputs.scf.output_parameters)

        # self.out_many(
        #     self.exposed_outputs(self.ctx.wannier90, Wannier90BandsWorkChain)
        # )

        self.report("Wannier -> TB2J WorkChain completed successfully.")
        return ExitCode(0)

    def _should_parse_structure_from_file(self) -> bool:
        """Return whether the 'structure' input is a file that needs parsing."""
        return isinstance(self.inputs.structure, SinglefileData)

    def _should_auto_detect_magnetic_elements(self) -> bool:
        """Return whether 'magnetic_elements' is absent and must be auto-detected."""
        return "magnetic_elements" not in self.inputs

    @classmethod
    def get_builder_from_protocol(
        cls,
        codes: Mapping[str, str | int | orm.Code],
        structure: StructureData | MagneticStructureData | SinglefileData,
        pseudo_family: str | None = None,
        *,
        protocol: str | None = None,
        spin_type: SpinType = SpinType.COLLINEAR,
        electronic_type: ElectronicType = ElectronicType.METAL,
        projection_type: WannierProjectionType = WannierProjectionType.ANALYTIC,
        wannier90_withmpi: bool = False,
        magnetic_elements: list[str] | None = None,
        tb2j_parameters: dict | None = None,
        tb2j_options: dict | None = None,
        **kwargs,
    ) -> ProcessBuilder:
        """
        Return a builder prepopulated for a magnetic-exchange Wannier90 + TB2J run.

        `electronic_type` defaults to METAL (not INSULATOR) so QE reports a single
        `fermi_energy`, which `run_tb2j`'s auto-fill requires; `projection_type`
        defaults to ANALYTIC (not SCDM/ATOMIC_PROJECTORS_QE) since some `wannier90.x`
        builds reject the `dis_proj_min`/`dis_proj_max` keywords those need.

        Parameters
        ----------
        codes : Mapping[str, str or int or orm.Code]
            Codes for each step, keyed by `'pw'`, `'pw2wannier90'`, `'wannier90'`,
            `'tb2j'`, and optionally `'projwfc'`/`'open_grid'`. String/int values
            are resolved with `orm.load_code`.
        structure : StructureData or MagneticStructureData or SinglefileData
            The input structure, or a `'CIF'`/`'MCIF'` file to parse into one first.
        pseudo_family : str, optional
            The pseudopotential family to use for the Wannier90/QE steps.
        protocol : str, optional
            The protocol to use, forwarded to
            `Wannier90BandsWorkChain.get_builder_from_protocol`.
        spin_type : SpinType, optional
            The spin treatment for the calculation. Defaults to
            `SpinType.COLLINEAR`.
        electronic_type : ElectronicType, optional
            The electronic treatment for the calculation. Defaults to
            `ElectronicType.METAL`.
        projection_type : WannierProjectionType, optional
            The Wannier90 projection type. Defaults to
            `WannierProjectionType.ANALYTIC`.
        wannier90_withmpi : bool, optional
            Whether to run `wannier90.x` under MPI. Defaults to `False`, which
            also forces single-task resources, to avoid a known file-locking
            crash from an unintentionally-serial binary launched under
            `mpirun -n N`.
        magnetic_elements : list of str, optional
            Elements for which the exchange interaction is considered. If not
            given, the WorkChain auto-detects them at runtime.
        tb2j_parameters : dict, optional
            Parameters for the TB2J calculation (`tb2j.parameters`).
        tb2j_options : dict, optional
            `metadata.options` for the TB2J calculation
            (`tb2j.metadata.options`). If not given, `WannierTB2JCalculation`'s
            own defaults apply.
        **kwargs
            Forwarded to `Wannier90BandsWorkChain.get_builder_from_protocol`.

        Returns
        -------
        ProcessBuilder
            A builder ready to submit, pending any further caller customisation.

        Raises
        ------
        ValueError
            If `codes` does not contain a `'tb2j'` entry.
        TypeError
            If `spin_type` is `SpinType.COLLINEAR`, no `initial_magnetic_moments`
            was given, and `structure` does not resolve to a
            `MagneticStructureData`.
        """
        if "tb2j" not in codes:
            raise ValueError("`codes` does not contain the required key: tb2j")

        codes = dict(codes)  # defensive copy; check_codes mutates its argument in place
        tb2j_code = codes.pop("tb2j")
        if isinstance(tb2j_code, str | int):
            tb2j_code = orm.load_code(tb2j_code)

        # Wannier90BandsWorkChain.get_builder_from_protocol only accepts StructureData;
        # carry out initial parsing of SinglefileData before creating builder.
        structure_node = (
            parse_magnetic_structure(structure)
            if isinstance(structure, SinglefileData)
            else structure
        )

        # Fixup 1: bypass is_collin_mag()'s antiferromagnetic misdetection.
        if spin_type is SpinType.COLLINEAR and "initial_magnetic_moments" not in kwargs:
            if not isinstance(structure_node, MagneticStructureData):
                raise TypeError(
                    "get_builder_from_protocol needs a `MagneticStructureData` "
                    "structure to auto-fill 'initial_magnetic_moments' for a "
                    "collinear calculation (a plain `StructureData` carries no "
                    "per-kind magnetic moments); pass one, or supply "
                    "'initial_magnetic_moments' explicitly."
                )
            kwargs["initial_magnetic_moments"] = collinear_magnetic_moments(
                structure_node
            )

        wannier_builder = Wannier90BandsWorkChain.get_builder_from_protocol(
            codes=codes,
            structure=structure_node,
            pseudo_family=pseudo_family,
            protocol=protocol,
            electronic_type=electronic_type,
            spin_type=spin_type,
            projection_type=projection_type,
            **kwargs,
        )

        # AiiDA's transport layer cannot copy files directly between two different
        # remote machines: `wannier90.x` reads the `pw2wannier90.x` outputs via a
        # remote-folder copy rather than re-uploading them, so the two codes must sit
        # on the same computer or the Wannier90Calculation will hang, retry the
        # transport task a few times, then pause with a `NotImplementedError`.
        pw2wannier90_code = wannier_builder.pw2wannier90.pw2wannier90.code  # type: ignore
        wannier90_code = wannier_builder.wannier90.wannier90.code  # type: ignore
        if (
            pw2wannier90_code is not None
            and wannier90_code is not None
            and pw2wannier90_code.computer.pk != wannier90_code.computer.pk
        ):
            _LOGGER.warning(
                "'pw2wannier90' code '%s' runs on computer '%s' but 'wannier90' code "
                "'%s' runs on computer '%s'; AiiDA cannot copy the pw2wannier90 "
                "outputs directly between two different computers, so the "
                "Wannier90Calculation step will fail. Install/configure 'wannier90.x' "
                "on '%s' and pass that code instead.",
                pw2wannier90_code.label,
                pw2wannier90_code.computer.label,
                wannier90_code.label,
                wannier90_code.computer.label,
                pw2wannier90_code.computer.label,
            )

        # Create builder for this WorkChain from constituents
        builder = cls.get_builder()
        merged_data = dict(builder._data)
        merged_data.update(wannier_builder._data)
        builder._data = merged_data

        builder.structure = structure_node

        # Force serial wannier90.x (avoids a known Fortran file-locking crash
        # from an unintentionally-serial binary launched under `mpirun -n N`).
        w90_options = builder.wannier90.wannier90.metadata.options
        w90_options.withmpi = wannier90_withmpi
        if not wannier90_withmpi:
            w90_options.resources = {"num_machines": 1, "num_mpiprocs_per_machine": 1}

        # QE aborts for insulator + collinear without an explicit net
        # tot_magnetization.
        if (
            electronic_type is ElectronicType.INSULATOR
            and spin_type is SpinType.COLLINEAR
        ):
            net_magnetization = total_magnetization(
                structure_node, kwargs["initial_magnetic_moments"]
            )
            for namespace_name in ("scf", "nscf"):
                if getattr(wannier_builder, namespace_name).pw.code is None:
                    continue
                sub_builder = getattr(builder, namespace_name)
                pw_parameters = sub_builder.pw.parameters.get_dict()
                pw_parameters.setdefault("SYSTEM", {})["tot_magnetization"] = (
                    net_magnetization
                )
                sub_builder.pw.parameters = orm.Dict(dict=pw_parameters)

        builder.tb2j.code = tb2j_code
        if tb2j_parameters is not None:
            builder.tb2j.parameters = orm.Dict(dict=tb2j_parameters)
        if tb2j_options is not None:
            builder.tb2j.metadata.options = tb2j_options

        if magnetic_elements is not None:
            builder.magnetic_elements = orm.List(list(magnetic_elements))

        return builder
