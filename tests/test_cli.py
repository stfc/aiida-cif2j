"""Tests for the `cif2j` command line interface."""

import subprocess
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from aiida_cif2j.cli import cli
from aiida_cif2j.cli.wannier90 import (
    AIIDA_WANNIER90_REQUIREMENT,
    AIIDA_WANNIER90_WORKFLOWS_REQUIREMENT,
)


def test_wannier90_install_success():
    """A successful pip install should report success and exit cleanly."""
    runner = CliRunner()

    with patch("aiida_cif2j.cli.wannier90.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = runner.invoke(cli, ["wannier90", "install"])

    assert result.exit_code == 0, result.output
    assert "Successfully installed" in result.output

    args, kwargs = mock_run.call_args
    cmdline = args[0]
    assert cmdline[-2:] == [
        AIIDA_WANNIER90_REQUIREMENT,
        AIIDA_WANNIER90_WORKFLOWS_REQUIREMENT,
    ]
    assert cmdline[1:3] == ["-m", "pip"]
    assert kwargs["check"] is True


def test_wannier90_install_failure():
    """A failed pip install should exit non-zero with a clear error message."""
    runner = CliRunner()

    with patch("aiida_cif2j.cli.wannier90.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, ["pip"])
        result = runner.invoke(cli, ["wannier90", "install"])

    assert result.exit_code != 0
    assert "Failed to install" in result.output
