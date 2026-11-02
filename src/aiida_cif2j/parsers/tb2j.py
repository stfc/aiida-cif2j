"""The core TB2J output parsers."""

import pathlib

from aiida.engine import ExitCode
from aiida.orm import SinglefileData
from aiida.parsers import Parser

from aiida_cif2j.calculations.wannier_tb2j import WannierTB2JCalculation


class TB2JParser(Parser):
    """The main TB2J AiiDA Parser."""

    def parse(self, **kwargs) -> ExitCode:
        """Parse the output from a TB2J calculation."""
        filename = WannierTB2JCalculation._PICKLE_FILE
        filepath = pathlib.Path(kwargs["retrieved_temporary_folder"]) / filename
        if not filepath.is_file():
            return self.exit_codes.ERROR_OUTPUT_PICKLE_MISSING

        with filepath.open("rb") as handle:
            self.out(
                "TB2J_pickle_file",
                SinglefileData(
                    file=handle,
                    filename=filename,
                    label="TB2J Results File",
                    description="Python pickle file containing results from TB2J.",
                ),
            )

        return ExitCode(0)
