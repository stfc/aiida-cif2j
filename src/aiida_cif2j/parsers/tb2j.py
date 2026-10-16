"""The core TB2J output parsers."""

from aiida.engine import ExitCode
from aiida.parsers import Parser

from aiida_cif2j.calculations.wannier_tb2j import WannierTB2JCalculation


class TB2JParser(Parser):
    """The main TB2J AiiDA Parser."""

    def parse(self, **kwargs) -> ExitCode:
        """Parse the output from a TB2J calculation."""
        if (
            WannierTB2JCalculation._PICKLE_FILE
            not in self.retrieved.list_object_names()
        ):
            return self.exit_codes.ERROR_OUTPUT_PICKLE_MISSING

        return ExitCode(0)
