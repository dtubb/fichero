"""Live generated-CLI write coverage for research, notes, hermeneutics, and agent memory."""

from __future__ import annotations

import json
import os
import socket

import pytest
from typer.testing import CliRunner

os.environ.setdefault("FICHERO_FEATURE_TIER", "dev")
os.environ.setdefault("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
os.environ.setdefault("FICHERO_DISABLE_AUTH", "1")

from fichero_cli import __main__ as cli  # noqa: E402

pytest_plugins = ["tests.integration._cli_live"]

runner = CliRunner()


def _cli_research_writes_ready() -> bool:
    if os.getenv("FICHERO_RUN_CLI_RESEARCH_WRITES") != "1":
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
    except OSError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _cli_research_writes_ready(),
    reason="Generated CLI research write contracts are opt-in and require loopback socket access",
)


def _cli_json(live_engine, *args: str):
    result = runner.invoke(
        cli.app,
        [
            "--json",
            "--base-url",
            live_engine["base_url"],
            "--library",
            str(live_engine["library"]),
            *args,
        ],
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _cli_result(live_engine, *args: str):
    return runner.invoke(
        cli.app,
        [
            "--base-url",
            live_engine["base_url"],
            "--library",
            str(live_engine["library"]),
            *args,
        ],
    )


def _audit_log(live_engine) -> dict:
    return _cli_json(live_engine, "actions", "list-audit-log")


def test_generated_research_note_agent_memory_and_hermeneutics_write_contracts_current_main(
    cli_live_engine,
) -> None:
    summary = cli_live_engine["summary"]

    audit_before = _audit_log(cli_live_engine)

    note = _cli_json(
        cli_live_engine,
        "notes",
        "create",
        "seeded from contract",
        "--title",
        "CLI note",
        "--folder",
        summary["keys"]["collection"],
        "--tag",
        "cli",
    )
    fetched_note = _cli_json(cli_live_engine, "notes", "get", note["id"])
    assert fetched_note["title"] == "CLI note"
    updated_note = _cli_json(
        cli_live_engine,
        "notes",
        "patch",
        note["id"],
        "--body",
        "updated body",
    )
    assert updated_note["body"] == "updated body"
    deleted_note = _cli_json(cli_live_engine, "notes", "delete", note["id"], "--yes")
    assert deleted_note is None

    note_audit = _audit_log(cli_live_engine)
    assert note_audit["count"] == audit_before["count"] + 3
    assert [item["action_name"] for item in note_audit["items"][:3]] == [
        "note.delete",
        "note.update",
        "note.create",
    ]

    agent_note = _cli_json(
        cli_live_engine,
        "agent-memory",
        "create-note",
        "--actor",
        json.dumps({"actor_id": "codex", "model_name": "gpt-5", "run_id": "contract"}),
        "--body",
        "Agent scratchpad",
        "--kind",
        "observation",
        "--source-anchor",
        json.dumps(
            {
                "document_id": summary["keys"]["doc_letter"],
                "page_id": summary["keys"]["page"],
                "page_label": "1",
            }
        ),
        "--tags",
        json.dumps(["agent"]),
    )
    fetched_agent_note = _cli_json(
        cli_live_engine, "agent-memory", "get-note", agent_note["id"]
    )
    assert fetched_agent_note["body"] == "Agent scratchpad"
    updated_agent_note = _cli_json(
        cli_live_engine,
        "agent-memory",
        "patch-note",
        agent_note["id"],
        "--body",
        "Agent scratchpad updated",
    )
    assert updated_agent_note["body"] == "Agent scratchpad updated"
    deleted_agent_note = _cli_json(
        cli_live_engine, "agent-memory", "delete-note", agent_note["id"], "--yes"
    )
    assert deleted_agent_note is None

    agent_audit = _audit_log(cli_live_engine)
    assert agent_audit["count"] == note_audit["count"] + 3
    assert [item["action_name"] for item in agent_audit["items"][:3]] == [
        "agent_memory.delete",
        "agent_memory.update",
        "agent_memory.create",
    ]

    # audit assertions pending /api/research->registry migration (#3024)
    project = _cli_json(
        cli_live_engine,
        "research",
        "create-project",
        "--name",
        "CLI research project",
        "--description",
        "research contract",
    )
    fetched_project = _cli_json(cli_live_engine, "research", "get-project", project["id"])
    assert fetched_project["name"] == "CLI research project"
    updated_project = _cli_json(
        cli_live_engine,
        "research",
        "update-project",
        project["id"],
        "--status",
        "completed",
    )
    assert updated_project["status"] == "completed"

    plan = _cli_json(
        cli_live_engine,
        "research",
        "create-plan",
        "--project-id",
        project["id"],
        "--name",
        "CLI plan",
    )
    fetched_plan = _cli_json(cli_live_engine, "research", "get-plan", plan["id"])
    assert fetched_plan["name"] == "CLI plan"

    task = _cli_json(
        cli_live_engine,
        "research",
        "create-task",
        "--plan-id",
        plan["id"],
        "--name",
        "CLI task",
    )
    updated_task = _cli_json(
        cli_live_engine,
        "research",
        "update-task",
        task["id"],
        "--status",
        "completed",
    )
    assert updated_task["status"] == "completed"

    research_note = _cli_json(
        cli_live_engine,
        "research",
        "create-note",
        "--project-id",
        project["id"],
        "--content",
        "Research finding",
    )
    fetched_research_note = _cli_json(
        cli_live_engine, "research", "get-note", research_note["id"]
    )
    assert fetched_research_note["content"] == "Research finding"
    updated_research_note = _cli_json(
        cli_live_engine,
        "research",
        "update-note",
        research_note["id"],
        "--content",
        "Research finding updated",
    )
    assert updated_research_note["content"] == "Research finding updated"
    listed_research_notes = _cli_json(
        cli_live_engine, "research", "list-notes", project["id"]
    )
    assert any(item["id"] == research_note["id"] for item in listed_research_notes["items"])

    checklist = _cli_json(
        cli_live_engine,
        "research",
        "create-checklist",
        "--project-id",
        project["id"],
        "--title",
        "CLI checklist",
        "--items",
        json.dumps([{"label": "First pass"}]),
    )
    toggled_checklist = _cli_json(
        cli_live_engine,
        "research",
        "toggle-checklist-item",
        checklist["id"],
        checklist["items"][0]["id"],
        "--checked",
        "--notes",
        "done",
    )
    assert toggled_checklist["items"][0]["checked"] is True

    hermeneutics_audit_before = _audit_log(cli_live_engine)
    framework = _cli_json(
        cli_live_engine,
        "interpretation",
        "create-framework",
        "--name",
        "CLI framework",
        "--framework-type",
        "historical",
        "--description",
        "Frame the text historically",
        "--core-questions",
        json.dumps(["Who wrote this?"]),
        "--key-concepts",
        json.dumps(["context"]),
    )
    fetched_framework = _cli_json(
        cli_live_engine, "interpretation", "get-framework", framework["id"]
    )
    assert fetched_framework["name"] == "CLI framework"
    updated_framework = _cli_json(
        cli_live_engine,
        "interpretation",
        "update-framework",
        framework["id"],
        "--description",
        "Frame the text in context",
    )
    assert updated_framework["description"] == "Frame the text in context"

    interpretation = _cli_json(
        cli_live_engine,
        "interpretation",
        "create-interpretation",
        "--framework-id",
        framework["id"],
        "--act",
        "contextualizing",
        "--claim-id",
        summary["ids"]["claims"][0],
        "--interpretation-text",
        "Placed in its historical situation.",
    )
    updated_interpretation = _cli_json(
        cli_live_engine,
        "interpretation",
        "update-interpretation",
        interpretation["id"],
        "--interpretation-text",
        "Placed in its broader historical situation.",
    )
    assert "broader historical" in updated_interpretation["interpretation_text"]

    pattern = _cli_json(
        cli_live_engine,
        "interpretation",
        "create-pattern",
        "--name",
        "CLI pattern",
        "--pattern-type",
        "motif",
        "--description",
        "A repeated idea",
        "--claim-ids",
        json.dumps([summary["ids"]["claims"][0]]),
    )
    updated_pattern = _cli_json(
        cli_live_engine,
        "interpretation",
        "update-pattern",
        pattern["id"],
        "--description",
        "A repeated idea across sources",
    )
    assert "across sources" in updated_pattern["description"]
    claimed_pattern = _cli_json(
        cli_live_engine,
        "interpretation",
        "add-claim-to-pattern",
        pattern["id"],
        summary["ids"]["claims"][1],
    )
    assert summary["ids"]["claims"][1] in claimed_pattern["claim_ids"]

    circle_state = _cli_json(
        cli_live_engine,
        "interpretation",
        "create-circle-state",
        "--claim-id",
        summary["ids"]["claims"][0],
        "--current-focus",
        "claim",
        "--direction",
        "part_to_whole",
        "--focus-id",
        summary["ids"]["claims"][0],
        "--focus-label",
        "Seed claim",
    )
    fetched_circle_state = _cli_json(
        cli_live_engine,
        "interpretation",
        "get-circle-state",
        circle_state["id"],
    )
    assert fetched_circle_state["claim_id"] == summary["ids"]["claims"][0]
    navigated_circle = _cli_json(
        cli_live_engine,
        "interpretation",
        "navigate-circle",
        circle_state["id"],
        "--direction",
        "whole_to_part",
        "--focus-id",
        summary["keys"]["doc_letter"],
        "--focus-label",
        "Letter",
    )
    assert navigated_circle["focus_id"] == summary["keys"]["doc_letter"]
    backtracked_circle = _cli_json(
        cli_live_engine,
        "interpretation",
        "backtrack-circle",
        circle_state["id"],
    )
    assert backtracked_circle["focus_id"] == summary["keys"]["doc_letter"]
    assert backtracked_circle["circle_level"] == 0
    hermeneutics_audit_after = _audit_log(cli_live_engine)
    assert hermeneutics_audit_after["count"] == hermeneutics_audit_before["count"] + 10
    assert hermeneutics_audit_after["items"][0]["action_name"] == "circle_state.backtrack"


def test_generated_research_validation_and_ai_no_500_bar_current_main(
    cli_live_engine,
) -> None:
    bad_research_task = _cli_result(
        cli_live_engine,
        "research",
        "update-task",
        "missing-task",
        "--status",
        "not-a-status",
    )
    assert bad_research_task.exit_code == 1
    assert "-> 422:" in bad_research_task.output

    ai_route = _cli_result(
        cli_live_engine,
        "interpretation",
        "suggest-interpretations",
        "--claim-ids",
        json.dumps([cli_live_engine["summary"]["ids"]["claims"][0]]),
        "--framework-ids",
        json.dumps(["missing-framework"]),
    )
    assert ai_route.exit_code == 1
    assert "-> 400:" in ai_route.output
    assert "-> 500:" not in ai_route.output
