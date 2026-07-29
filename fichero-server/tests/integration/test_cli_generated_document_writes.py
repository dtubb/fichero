"""Live generated-CLI write coverage for documents/images/storage/artifacts."""

from __future__ import annotations

import base64
import json
import os
import socket
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

os.environ.setdefault("FICHERO_FEATURE_TIER", "dev")
os.environ.setdefault("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
os.environ.setdefault("FICHERO_DISABLE_AUTH", "1")

from fichero_server import __main__ as cli  # noqa: E402

pytest_plugins = ["tests.integration._cli_live"]

runner = CliRunner()
_ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j5tQAAAAASUVORK5CYII="
)


def _cli_document_writes_ready() -> bool:
    if os.getenv("FICHERO_RUN_CLI_DOCUMENT_WRITES") != "1":
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
    except OSError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _cli_document_writes_ready(),
    reason="Generated CLI document write contracts are opt-in and require loopback socket access",
)


def _cli_json(live_engine, *args: str, input: str | None = None):
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
        input=input,
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _cli_result(live_engine, *args: str, input: str | None = None):
    return runner.invoke(
        cli.app,
        [
            "--base-url",
            live_engine["base_url"],
            "--library",
            str(live_engine["library"]),
            *args,
        ],
        input=input,
    )


def _audit_log(live_engine) -> dict:
    return _cli_json(live_engine, "actions", "list-audit-log")


def _get(live_engine, path: str) -> httpx.Response:
    return httpx.get(
        f"{live_engine['base_url']}{path}",
        headers={"X-Fichero-Library-Path": str(live_engine["library"])},
        timeout=5,
    )


def test_generated_document_and_image_write_contracts_current_main(
    cli_live_engine, tmp_path: Path
) -> None:
    upload = tmp_path / "tiny.png"
    upload.write_bytes(_ONE_PIXEL_PNG)

    # audit assertions pending remaining documents->registry migration (#3005)
    imported = _cli_json(
        cli_live_engine,
        "docs",
        "import-file",
        "--parent-id",
        cli_live_engine["summary"]["keys"]["collection"],
        "--upload",
        f"file={upload}",
    )
    imported_id = imported["id"]
    assert imported["file_type"] == "image"
    assert imported["parent_id"] == cli_live_engine["summary"]["keys"]["collection"]

    source = _get(cli_live_engine, f"/api/storage/source/{imported_id}")
    display = _get(cli_live_engine, f"/api/storage/display/{imported_id}")
    thumbnail = _get(cli_live_engine, f"/api/storage/thumbnail/{imported_id}")
    preview = _get(cli_live_engine, f"/api/images/{imported_id}/preview")
    assert source.status_code == 200 and source.headers["content-type"].startswith("image/png")
    assert display.status_code == 200 and display.headers["content-type"].startswith("image/jpeg")
    assert thumbnail.status_code == 200 and thumbnail.headers["content-type"].startswith("image/jpeg")
    assert preview.status_code == 200 and preview.headers["content-type"].startswith("image/jpeg")

    # audit assertions pending /api/images->registry migration (#3006)
    rotated = _cli_json(
        cli_live_engine,
        "images",
        "rotate",
        imported_id,
        "--angle",
        "90",
    )
    assert rotated["document_id"] == imported_id
    assert rotated["operations"][-1]["op"] == "rotate"
    edit_chain = _cli_json(cli_live_engine, "images", "get-edit-chain", imported_id)
    assert edit_chain["operations"][-1]["params"]["angle"] == 90.0

    # audit assertions pending /api/artifacts->registry migration (#3004)
    artifact = _cli_json(
        cli_live_engine,
        "artifacts",
        "create",
        "--document-id",
        imported_id,
        "--artifact-type",
        "note",
        "--content",
        "hello",
    )
    fetched_artifact = _cli_json(cli_live_engine, "artifacts", "get", artifact["id"])
    assert fetched_artifact["content"] == "hello"
    updated_artifact = _cli_json(
        cli_live_engine,
        "artifacts",
        "update",
        artifact["id"],
        "--content",
        "updated",
        "--reviewed",
    )
    assert updated_artifact["content"] == "updated"
    listed_artifacts = _cli_json(cli_live_engine, "artifacts", "list-document", imported_id)
    assert any(item["id"] == artifact["id"] for item in listed_artifacts["items"])
    deleted_artifact = _cli_json(
        cli_live_engine,
        "artifacts",
        "delete",
        artifact["id"],
        "--yes",
    )
    assert deleted_artifact is None

    before_audits = _audit_log(cli_live_engine)
    moved = _cli_json(
        cli_live_engine,
        "docs",
        "move",
        imported_id,
        "--parent-id",
        cli_live_engine["summary"]["keys"]["collection"],
    )
    assert moved["id"] == imported_id
    after_move = _audit_log(cli_live_engine)
    assert after_move["count"] == before_audits["count"] + 1
    assert after_move["items"][0]["action_name"] == "document.move"

    deleted_doc = _cli_json(cli_live_engine, "docs", "delete", imported_id, "--yes")
    assert deleted_doc is None
    after_delete = _audit_log(cli_live_engine)
    assert after_delete["count"] == after_move["count"] + 1
    assert after_delete["items"][0]["action_name"] == "document.delete"

    # audit assertions pending remaining documents->registry migration (#3005)
    restored_doc = _cli_json(cli_live_engine, "docs", "restore", imported_id)
    assert restored_doc is None
    restored = _get(cli_live_engine, f"/api/documents/{imported_id}")
    assert restored.status_code == 200


def test_generated_document_domain_validation_and_snapshot_round_trip_current_main(
    cli_live_engine,
) -> None:
    bad_image_request = _cli_result(
        cli_live_engine,
        "images",
        "enhance",
        cli_live_engine["summary"]["keys"]["doc_photo"],
        "--brightness",
        "1.0",
        "--page",
        "0",
    )
    assert bad_image_request.exit_code == 1
    assert "-> 422:" in bad_image_request.output

    snapshot = _cli_json(
        cli_live_engine,
        "storage",
        "create-snapshot",
        "--library-path",
        str(cli_live_engine["library"]),
        "--reason",
        "contract test",
    )
    snapshot_id = snapshot["id"]

    # audit assertions pending /api/storage->registry migration (#3007)
    pinned = _cli_json(cli_live_engine, "storage", "pin-snapshot", snapshot_id, "--pinned")
    assert pinned["is_pinned"] is True
    fetched_snapshot = _cli_json(cli_live_engine, "storage", "get-snapshot", snapshot_id)
    assert fetched_snapshot["id"] == snapshot_id

    # audit assertions pending /api/artifacts->registry migration (#3004)
    artifact = _cli_json(
        cli_live_engine,
        "artifacts",
        "create",
        "--document-id",
        cli_live_engine["summary"]["keys"]["doc_photo"],
        "--artifact-type",
        "note",
        "--content",
        "after snapshot",
    )
    listed_after_create = _cli_json(
        cli_live_engine,
        "artifacts",
        "list-document",
        cli_live_engine["summary"]["keys"]["doc_photo"],
    )
    assert any(item["id"] == artifact["id"] for item in listed_after_create["items"])

    restored_snapshot = _cli_json(
        cli_live_engine,
        "storage",
        "restore-library-snapshot",
        snapshot_id,
    )
    assert restored_snapshot["snapshot_id"] == snapshot_id
    listed_after_restore = _cli_json(
        cli_live_engine,
        "artifacts",
        "list-document",
        cli_live_engine["summary"]["keys"]["doc_photo"],
    )
    assert all(item["id"] != artifact["id"] for item in listed_after_restore["items"])

    deleted_snapshot = _cli_json(
        cli_live_engine, "storage", "remove-snapshot", snapshot_id, "--yes"
    )
    assert deleted_snapshot == {"deleted": True, "snapshot_id": snapshot_id}
