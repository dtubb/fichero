"""A check run is started, read and stopped from the CLI (spec source.check.run-is-a-job, #5404)."""

from typer.main import get_command

from fichero_cli import __main__ as cli_main


def test_the_cli_starts_reads_and_stops_a_check_run():
    check = get_command(cli_main.app).commands["check"].commands
    assert "/api/check/runs)" in check["start-run"].help
    assert "/api/check/runs/{job_id}/cancel" in check["cancel-run"].help
    assert "/api/check/runs/{job_id}" in check["run-status"].help
    assert {"layer", "model", "provider", "scope_ids"} <= {p.name for p in check["start-run"].params}
