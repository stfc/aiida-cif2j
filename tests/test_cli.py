"""Tests for the `cif2j` command line interface."""

import json
import subprocess
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from aiida_cif2j.cli import cli
from aiida_cif2j.cli.wannier90 import (
    AIIDA_WANNIER90_REQUIREMENT,
    AIIDA_WANNIER90_WORKFLOWS_REQUIREMENT,
)

SUBMIT_REQUIRED_ARGS = [
    "--pw-code",
    "pw@localhost",
    "--pw2wannier90-code",
    "pw2wannier90@localhost",
    "--wannier90-code",
    "wannier90@localhost",
    "--tb2j-code",
    "tb2j@localhost",
    "--pseudo-family",
    "SSSP/1.3/PBE/efficiency",
]


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


def test_wannier90_submit_dry_run(tmp_path):
    """A '--dry-run' submission should build the inputs but not call 'submit'."""
    mcif_file = tmp_path / "structure.mcif"
    mcif_file.write_text("data_test\n")

    runner = CliRunner()
    builder = MagicMock()

    with (
        patch("aiida.load_profile") as mock_load_profile,
        patch("aiida.orm.SinglefileData") as mock_singlefile,
        patch("aiida.engine.submit") as mock_submit,
        patch(
            "aiida_cif2j.workflows.wannier.WannierTB2JWorkChain."
            "get_builder_from_protocol",
            return_value=builder,
        ) as mock_get_builder,
    ):
        result = runner.invoke(
            cli,
            [
                "wannier90",
                "submit",
                str(mcif_file),
                *SUBMIT_REQUIRED_ARGS,
                "--magnetic-element",
                "Fe",
                "--magnetic-element",
                "Mn",
                "--dry-run",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Would submit WannierTB2JWorkChain" in result.output

    mock_load_profile.assert_called_once_with(None)
    mock_singlefile.assert_called_once_with(file=str(mcif_file.resolve()))
    mock_submit.assert_not_called()

    mock_get_builder.assert_called_once()
    _, kwargs = mock_get_builder.call_args
    assert kwargs["codes"] == {
        "pw": "pw@localhost",
        "pw2wannier90": "pw2wannier90@localhost",
        "wannier90": "wannier90@localhost",
        "tb2j": "tb2j@localhost",
    }
    assert kwargs["pseudo_family"] == "SSSP/1.3/PBE/efficiency"
    assert kwargs["magnetic_elements"] == ["Fe", "Mn"]


def test_wannier90_submit_submits_and_adds_to_group(tmp_path):
    """A real (non-dry-run) submission should submit the builder and add to a group."""
    mcif_file = tmp_path / "structure.mcif"
    mcif_file.write_text("data_test\n")

    runner = CliRunner()
    builder = MagicMock()
    submitted_node = MagicMock(pk=42)
    group = MagicMock()

    with (
        patch("aiida.load_profile"),
        patch("aiida.orm.SinglefileData"),
        patch("aiida.orm.Group") as mock_group_cls,
        patch("aiida.engine.submit", return_value=submitted_node) as mock_submit,
        patch(
            "aiida_cif2j.workflows.wannier.WannierTB2JWorkChain."
            "get_builder_from_protocol",
            return_value=builder,
        ),
    ):
        mock_group_cls.collection.get_or_create.return_value = (group, True)
        result = runner.invoke(
            cli,
            [
                "wannier90",
                "submit",
                str(mcif_file),
                *SUBMIT_REQUIRED_ARGS,
                "--label",
                "my-label",
                "--group",
                "my-group",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Submitted WannierTB2JWorkChain<42>" in result.output
    assert "Added WannierTB2JWorkChain<42> to group 'my-group'" in result.output

    mock_submit.assert_called_once_with(builder)
    assert builder.metadata.label == "my-label"
    group.add_nodes.assert_called_once_with([submitted_node])


def test_wannier90_submit_run_open_grid_requires_code(tmp_path):
    """'--run-open-grid' without '--open-grid-code' should fail with a usage error."""
    mcif_file = tmp_path / "structure.mcif"
    mcif_file.write_text("data_test\n")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "wannier90",
            "submit",
            str(mcif_file),
            *SUBMIT_REQUIRED_ARGS,
            "--run-open-grid",
        ],
    )

    assert result.exit_code != 0
    assert "--run-open-grid" in result.output
    assert "--open-grid-code" in result.output


def test_wannier90_submit_tb2j_parameters_json_file(tmp_path):
    """'--tb2j-parameters @file.json' should read and parse the given JSON file."""
    mcif_file = tmp_path / "structure.mcif"
    mcif_file.write_text("data_test\n")

    parameters_file = tmp_path / "parameters.json"
    parameters_file.write_text(json.dumps({"kmesh": [5, 5, 5]}))

    runner = CliRunner()
    builder = MagicMock()

    with (
        patch("aiida.load_profile"),
        patch("aiida.orm.SinglefileData"),
        patch("aiida.engine.submit"),
        patch(
            "aiida_cif2j.workflows.wannier.WannierTB2JWorkChain."
            "get_builder_from_protocol",
            return_value=builder,
        ) as mock_get_builder,
    ):
        result = runner.invoke(
            cli,
            [
                "wannier90",
                "submit",
                str(mcif_file),
                *SUBMIT_REQUIRED_ARGS,
                "--tb2j-parameters",
                f"@{parameters_file}",
                "--dry-run",
            ],
        )

    assert result.exit_code == 0, result.output
    _, kwargs = mock_get_builder.call_args
    assert kwargs["tb2j_parameters"] == {"kmesh": [5, 5, 5]}


def test_wannier90_submit_tb2j_parameters_invalid_json(tmp_path):
    """Invalid inline JSON for '--tb2j-parameters' should fail with a clear error."""
    mcif_file = tmp_path / "structure.mcif"
    mcif_file.write_text("data_test\n")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "wannier90",
            "submit",
            str(mcif_file),
            *SUBMIT_REQUIRED_ARGS,
            "--tb2j-parameters",
            "{not json}",
        ],
    )

    assert result.exit_code != 0
    assert "invalid JSON" in result.output
