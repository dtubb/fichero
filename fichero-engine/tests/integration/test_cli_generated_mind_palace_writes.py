"""Live generated-CLI write coverage for folder-scoped mind-palace routes."""

from __future__ import annotations

import json
import os
import socket

import pytest
from typer.testing import CliRunner

os.environ.setdefault("FICHERO_FEATURE_TIER", "dev")
os.environ.setdefault("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
os.environ.setdefault("FICHERO_DISABLE_AUTH", "1")

from fichero import __main__ as cli  # noqa: E402

pytest_plugins = ["tests.integration._cli_live"]

runner = CliRunner()


def _cli_mind_palace_writes_ready() -> bool:
    if os.getenv("FICHERO_RUN_CLI_MIND_PALACE_WRITES") != "1":
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
    except OSError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _cli_mind_palace_writes_ready(),
    reason="Generated CLI mind-palace write contracts are opt-in and require loopback socket access",
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


def test_generated_mind_palace_folder_write_contracts_current_main(
    cli_live_engine,
) -> None:
    summary = cli_live_engine["summary"]
    folder_id = summary["keys"]["collection"]

    # audit assertions pending /api/mind-palace folder canvas writes->registry migration (#3023)
    before = _audit_log(cli_live_engine)

    item = _cli_json(
        cli_live_engine,
        "mind-palace",
        "create-canvas-item",
        folder_id,
        "--kind",
        "text",
        "--text",
        "Canvas note",
    )
    item_id = item["id"]
    assert item["folder_id"] == folder_id
    assert item["text"] == "Canvas note"

    listed_items = _cli_json(
        cli_live_engine,
        "mind-palace",
        "list-canvas-items",
        folder_id,
    )
    assert any(row["id"] == item_id for row in listed_items["items"])

    updated_item = _cli_json(
        cli_live_engine,
        "mind-palace",
        "update-canvas-item",
        folder_id,
        item_id,
        "--text",
        "Canvas note updated",
    )
    assert updated_item["text"] == "Canvas note updated"

    saved_layout = _cli_json(
        cli_live_engine,
        "mind-palace",
        "save-canvas-layout",
        folder_id,
        "--items",
        json.dumps(
            [
                {
                    "item_id": summary["keys"]["doc_letter"],
                    "x": 10.0,
                    "y": 20.0,
                    "z": 0.0,
                        "w": 300.0,
                        "h": 180.0,
                        "d": 0.0,
                        "angle": 15.0,
                        "z_index": 4,
                        "style": "card",
                    }
                ]
            ),
    )
    assert saved_layout[0]["item_id"] == summary["keys"]["doc_letter"]
    assert saved_layout[0]["x"] == 10.0

    fetched_layout = _cli_json(
        cli_live_engine,
        "mind-palace",
        "get-canvas-layout",
        folder_id,
    )
    saved_row = next(
        row for row in fetched_layout["items"] if row["item_id"] == summary["keys"]["doc_letter"]
    )
    assert saved_row["x"] == 10.0
    assert saved_row["angle"] == 15.0

    arranged = _cli_json(
        cli_live_engine,
        "mind-palace",
        "arrange-folder-canvas",
        folder_id,
        "--node-ids",
        json.dumps([summary["keys"]["doc_letter"], summary["keys"]["doc_photo"]]),
        "--strategy",
        "row",
        "--spacing",
        "150",
    )
    assert arranged["count"] == 2
    arranged_ids = {row["item_id"] for row in arranged["items"]}
    assert arranged_ids == {summary["keys"]["doc_letter"], summary["keys"]["doc_photo"]}

    deleted_item = _cli_json(
        cli_live_engine,
        "mind-palace",
        "delete-canvas-item",
        folder_id,
        item_id,
        "--yes",
    )
    assert deleted_item["status"] == "deleted"

    after = _audit_log(cli_live_engine)
    assert after["count"] == before["count"]


def test_generated_mind_palace_render_no_500_current_main(cli_live_engine) -> None:
    missing_room = _cli_result(
        cli_live_engine,
        "mind-palace",
        "render-scene",
        "--room-id",
        "missing-room",
    )
    assert missing_room.exit_code == 1
    assert "-> 404:" in missing_room.output
