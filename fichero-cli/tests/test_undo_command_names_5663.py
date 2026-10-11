"""Undoing one step reads as `undo` on both surfaces; the set is `undo-set` (#5663).

WHY: the transfer result tells a person to undo its audit row. The single-step undo was generated as
`actions undo-actions-audit-undo` and `fichero_actions_undo_post`, names nobody would find, while `undo`
was the set of several.
"""

import inspect

from typer.main import get_command

from fichero_cli import __main__ as cli_main
from fichero_mcp import openapi_tools_generated as tools


def test_the_cli_undoes_one_step_by_its_audit_id_and_a_set_by_undo_set():
    actions = get_command(cli_main.app).commands["actions"].commands
    one, several = actions["undo"], actions["undo-set"]
    assert "/api/actions/audit/{audit_id}/undo" in one.help
    assert [p.name for p in one.params if p.param_type_name == "argument"] == ["audit_id"]
    assert "/api/actions/audit/undo)" in several.help
    assert "audit_ids" in {p.name for p in several.params if p.param_type_name == "option"}


def test_mcp_names_the_one_step_undo_and_the_set():
    assert list(inspect.signature(tools.fichero_actions_undo).parameters) == ["audit_id"]
    assert "audit_ids" in inspect.signature(tools.fichero_actions_undo_set).parameters
    assert not hasattr(tools, "fichero_actions_undo_post")
