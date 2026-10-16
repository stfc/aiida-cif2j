"""AiiDA WorkChain for combining Wannier90 and TB2J into a single workflow."""

from aiida.common import AttributeDict
from aiida.engine import ExitCode, ToContext, WorkChain, if_
from aiida.orm import Dict, FolderData, List, SinglefileData, StructureData
from aiida_wannier90_workflows.data.structure import MagneticStructureData
from aiida_wannier90_workflows.workflows.bands import Wannier90BandsWorkChain

from aiida_cif2j.calculations.utils import (
    detect_magnetic_elements,
    parse_magnetic_structure,
)
from aiida_cif2j.calculations.wannier_tb2j import WannierTB2JCalculation
from aiida_cif2j.workflows.utils import validate_chemical_symbols


class WannierTB2JWorkChain(WorkChain):
    """WorkChain linking Wannier90BandsWorkChain and TB2J."""

    @classmethod
    def define(cls, spec):
        """Define the WorkChain's specification."""
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
                "spin-polarized)."
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
        """Parse a input .cif structure file."""
        self.ctx.structure = parse_magnetic_structure(self.inputs.structure)
        return

    def auto_detect_magnetic_elements(self):
        """Auto-detect magnetic elements from input structure."""
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
        """Run the Wannier90BandsWorkChain step of the workflow."""
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
        """Run the TB2J step of the workflow."""
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
        """Bring together the outputs from the full WorkChain."""
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
        return isinstance(self.inputs.structure, SinglefileData)

    def _should_auto_detect_magnetic_elements(self) -> bool:
        return "magnetic_elements" not in self.inputs
