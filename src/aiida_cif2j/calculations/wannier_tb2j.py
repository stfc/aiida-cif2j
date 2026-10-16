"""Wannier90 Based TB2J Calculations Module."""

from types import UnionType

from aiida.common import CalcInfo, CodeInfo, InputValidationError
from aiida.common.folders import Folder
from aiida.engine import CalcJob, CalcJobProcessSpec
from aiida.orm import Dict, FolderData, List, StructureData
from aiida.orm.nodes.data.structure import validate_symbols_tuple


class WannierTB2JCalculation(CalcJob):
    """AiiDA calculation plugin for wann2J.py TB2J script."""

    _PICKLE_FILE = "TB2J.pickle"

    @classmethod
    def define(cls, spec: CalcJobProcessSpec):
        """
        Define the inputs, outputs and metadata of the calculation.

        Parameters
        ----------
        spec : CalcJobProcessSpec
            The AiiDA Process specification object for the job.
        """
        super().define(spec)

        spec.inputs.validator = cls._validate_inputs

        ## Inputs
        spec.input(
            "wannier_folder",
            valid_type=FolderData,
            required=False,
            help="`retrieved` output of a single non-collinear/spin-orbit "
            "Wannier90Calculation. Mutually exclusive with 'wannier_folder_up'/'"
            "wannier_folder_down'.",
        )
        spec.input(
            "wannier_folder_up",
            valid_type=FolderData,
            required=False,
            help="`retrieved` output of the spin-up Wannier90Calculation, for a "
            "collinear spin-polarised calculation. Requires 'wannier_folder_down' to "
            "also be given.",
        )
        spec.input(
            "wannier_folder_down",
            valid_type=FolderData,
            required=False,
            help="`retrieved` output of the spin-down Wannier90Calculation, for a "
            "collinear spin-polarised calculation. Requires 'wannier_folder_up' to "
            "also be given.",
        )
        spec.input(
            "elements",
            valid_type=List,
            required=True,
            validator=validate_symbols_tuple,
            help="List of magnetic elements.",
        )
        spec.input(
            "parameters",
            valid_type=Dict,
            required=False,
            validator=cls._validate_parameters,
            help="Contains all the optional parameters for the TB2J calculation.",
        )
        spec.input(
            "structure",
            valid_type=StructureData,
            required=True,
            help="Used to write the POSITION file read by wann2J.py, and to set up the "
            "'kmesh' variable based on the unit cell dimensions if not given "
            "explicitly.",
        )

        ## Outputs
        # spec.output(
        #     "TB2J_pickle_file",
        #     valid_type=SinglefileData,
        #     required=True,
        #     help="The TB2J output python pickle file.",
        # )

        ## Metadata
        spec.inputs["metadata"]["options"]["resources"].default = {
            "num_machines": 1,
            "num_mpiprocs_per_machine": 1,
        }
        spec.inputs["metadata"]["options"]["parser_name"].default = "tb2j"

        ## Exit Codes
        spec.exit_code(
            300,
            "ERROR_OUTPUT_PICKLE_MISSING",
            message="The retrieved folder does not contain the 'TB2J.pickle' file.",
        )
        return

    def prepare_for_submission(self, folder: Folder) -> CalcInfo:
        """
        Prepare the TB2J calculation for submission.

        Parameters
        ----------
        folder : Folder
            An `aiida.common.folders.Folder` specifying the temporary working
            directory for the calculation.

        Returns
        -------
        calcInfo : CalcInfo
            An `aiida.common.CalcInfo` instance.
        """
        code_info = CodeInfo()
        code_info.code_uuid = self.inputs.code.uuid
        code_info.cmdline_params = self.build_cmdline_parameters()

        calc_info = CalcInfo()
        calc_info.codes_info = [code_info]
        calc_info.retrieve_list = [WannierTB2JCalculation._PICKLE_FILE]
        if "wannier_folder" in self.inputs:
            calc_info.local_copy_list = self._collect_wannier_files(
                self.inputs.wannier_folder, "wannier90"
            )
        else:
            calc_info.local_copy_list = self._collect_wannier_files(
                self.inputs.wannier_folder_up, "wannier90.up"
            )
            calc_info.local_copy_list += self._collect_wannier_files(
                self.inputs.wannier_folder_down, "wannier90.dn"
            )

        return calc_info

    def apply_default_inputs_tags(self) -> None:
        """Apply default labels to input nodes."""
        return

    def build_cmdline_parameters(self) -> list[str]:
        """Create the command line parameters from the input dictionary."""
        kmesh = [5, 5, 5]
        kmesh_is_present = False
        supercell_size = 20.0

        param_dict = self.inputs.parameters.get_dict()
        try:
            kmesh = param_dict.pop("kmesh")
            kmesh_is_present = True
        except KeyError:
            pass
        try:
            supercell_size = param_dict.pop("supercell_size")
        except KeyError:
            pass

        if not kmesh_is_present:
            from numpy import ceil
            from numpy.linalg import norm

            structure = self.inputs.structure
            lattice_parameters = norm(structure.cell, axis=-1)
            kmesh = ceil(supercell_size / lattice_parameters).astype(int).tolist()
            kmesh = [kmesh[i] if structure.pbc[i] else 1 for i in range(3)]

        if "wannier_folder" in self.inputs:
            cmdline_params = ["--spinor", "--prefix_spinor", "wannier90"]
        else:
            cmdline_params = [
                "--prefix_up",
                "wannier90.up",
                "--prefix_down",
                "wannier90.dn",
            ]

        cmdline_params = [
            "--path",
            ".",
            "--posfile",
            "POSCAR",
            "--output_path",
            ".",
        ] + cmdline_params
        cmdline_params += ["--elements"] + [
            str(element) for element in self.inputs.elements
        ]
        cmdline_params += ["--kmesh"] + [str(i) for i in kmesh]
        cmdline_params += [
            element
            for parameter, value in param_dict.items()
            for element in self._as_cmdline_args(parameter, value)
        ]
        return cmdline_params

    @staticmethod
    def _validate_inputs(value, _) -> None | str:
        has_spinor = "wannier_folder" in value
        has_up = "wannier_folder_up" in value
        has_down = "wannier_folder_down" in value

        if has_spinor and (has_up or has_down):
            return (
                "Specify either 'wannier_folder' or the 'wannier_folder_up'/'"
                "wannier_folder_down' pair, not both."
            )
        if has_up != has_down:
            return (
                "'wannier_folder_up' and 'wannier_folder_down' must be given together."
            )
        if not (has_spinor or has_up):
            return (
                "Either 'wannier_folder' or both 'wannier_folder_up' and "
                "'wannier_folder_down' must be given."
            )
        return None

    @staticmethod
    def _validate_parameters(value: Dict, _) -> str | None:
        """Validate the wann2J.py command line parameters dictionary."""
        params = value.get_dict()
        valid_scaler_parameters = WannierTB2JCalculation._get_valid_scaler_parameters()
        valid_list_parameters = WannierTB2JCalculation._get_valid_list_parameters()
        for k, v in params.items():
            if k == "kmesh":
                try:
                    kmesh = list(v)
                    if len(kmesh) != 3 or not all(isinstance(x, int) for x in kmesh):
                        return "The 'kmesh' option must contain 3 integers."
                except TypeError:
                    return "The 'kmesh' option must be an iterable."
            elif k in valid_list_parameters:
                elem_type = valid_list_parameters[k]
                try:
                    if not all(isinstance(x, elem_type) for x in v):
                        return f"'{k}' option must be a list of '{elem_type}'."
                except TypeError:
                    return f"'{k}' option must be an iterable."
            elif k in valid_scaler_parameters:
                if not isinstance(v, valid_scaler_parameters[k]):
                    return (
                        f"'{k}' option must be a valid '{valid_scaler_parameters[k]}'."
                    )
                if k == "groupby" and v not in ("spin", "orbital"):
                    return "The 'groupby' option must be either 'spin' or 'orbital'."
                if k == "supercell_size" and v < 0.0:  # type: ignore
                    return "'supercell_size' option must be positive."
            else:
                return f"Unrecognized option '{k}'"

        if "efermi" not in params:
            return "The 'efermi' option is required by the wann2J.py CLI."

        return None

    @staticmethod
    def _collect_wannier_files(wannier_folder, target_prefix):
        available = set(wannier_folder.list_object_names())
        local_copy_list = [
            (wannier_folder.uuid, f"aiida{suffix}", f"{target_prefix}{suffix}")
            for suffix in WannierTB2JCalculation._get_hamiltonian_suffixes()
            if f"aiida{suffix}" in available
        ]

        has_positions = any(
            name.endswith(("_tb.dat", "_centres.xyz")) for _, name, _ in local_copy_list
        )
        has_hamiltonian = any(
            name.endswith(("_tb.dat", "_hr.dat")) for _, name, _ in local_copy_list
        )
        if not (has_hamiltonian and has_positions):
            raise InputValidationError(
                f"The FolderData<{wannier_folder.pk}> does not contain the files "
                "wann2J.py needs: either 'aiida_tb.dat' (set write_tb=True in the "
                "Wannier90 parameters), or both 'aiida_hr.dat' and 'aiida_centres.xyz' "
                "(set write_hr=True and write_xyz=True)."
            )

        return local_copy_list

    @staticmethod
    def _as_cmdline_args(parameter, value):
        flag = "--" + parameter
        if isinstance(value, bool):
            return [flag] if value else []
        if isinstance(value, (list | tuple)):
            return [flag] + [str(element) for element in value]
        return [flag, str(value)]

    @staticmethod
    def _get_hamiltonian_suffixes() -> tuple[str, ...]:
        return ("_tb.dat", "_hr.dat", "_centres.xyz")

    @staticmethod
    def _get_valid_scaler_parameters() -> dict[str, type | UnionType]:
        return {
            "rcut": float | int,
            "efermi": float | int,
            "emin": float | int,
            "emax": float | int,
            "cutoff": float | int,
            "supercell_size": float | int,
            "ne": int,
            "nz": int,
            "e_batch_size": int,
            "use_cache": bool,
            "orb_decomposition": bool,
            "group_by_zeta": bool,
            "write_dm": bool,
            "orth": bool,
            "ibz": bool,
            "use_gpu": bool,
            "vectorize_energy": bool,
            "smearing": str,
            "description": str,
            "groupby": str,
        }

    @staticmethod
    def _get_valid_list_parameters() -> dict[str, type | UnionType]:
        return {
            "exclude_orbs": int,
            "index_magnetic_atoms": int,
            "mae_angles": float | int,
        }
