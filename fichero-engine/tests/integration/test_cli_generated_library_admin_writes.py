"""Live generated-CLI coverage for library-admin write paths."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest
from typer.testing import CliRunner

os.environ.setdefault("FICHERO_FEATURE_TIER", "dev")
os.environ.setdefault("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
os.environ.setdefault("FICHERO_DISABLE_AUTH", "1")

from fichero import __main__ as cli  # noqa: E402

pytest_plugins = ["tests.integration._cli_live"]

runner = CliRunner()


def _cli_library_admin_ready() -> bool:
    if os.getenv("FICHERO_RUN_CLI_LIBRARY_ADMIN_WRITES") != "1":
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
    except OSError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _cli_library_admin_ready(),
    reason="Generated CLI library-admin contracts are opt-in and require loopback socket access",
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
            "--json",
            "--base-url",
            live_engine["base_url"],
            "--library",
            str(live_engine["library"]),
            *args,
        ],
    )


def test_generated_library_admin_write_contracts_current_main(
    cli_live_engine, tmp_path: Path
) -> None:
    summary = cli_live_engine["summary"]

    # Current main only exposes folder CRUD for workflow/search/conversation.
    created_folder = _cli_json(
        cli_live_engine,
        "folders",
        "create",
        "search",
        "--folder-path",
        "/CLI Folder",
    )
    assert created_folder["path"] == "/CLI Folder"
    renamed_folder = _cli_json(
        cli_live_engine,
        "folders",
        "rename",
        "search",
        "--old-path",
        "/CLI Folder",
        "--new-path",
        "/CLI Folder Renamed",
    )
    assert renamed_folder["new_path"] == "/CLI Folder Renamed"
    deleted_folder = _cli_json(
        cli_live_engine,
        "folders",
        "delete",
        "search",
        "--folder-path",
        "/CLI Folder Renamed",
    )
    assert deleted_folder["parent_path"] == "/"

    project = _cli_json(
        cli_live_engine,
        "projects",
        "create",
        "--name",
        "CLI Project",
        "--description",
        "contract project",
        "--status",
        "active",
    )
    project_id = project["id"]
    fetched_project = _cli_json(cli_live_engine, "projects", "get", project_id)
    assert fetched_project["name"] == "CLI Project"
    patched_project = _cli_json(
        cli_live_engine,
        "projects",
        "patch",
        project_id,
        "--description",
        "updated contract project",
    )
    assert patched_project["description"] == "updated contract project"
    inclusion = _cli_json(
        cli_live_engine,
        "projects",
        "add-a-kg-item-document-entity-claim-note-interpretation-annotation-to-a",
        project_id,
        "--target-id",
        summary["keys"]["doc_letter"],
        "--target-type",
        "document",
    )
    listed_inclusions = _cli_json(
        cli_live_engine,
        "projects",
        "list-every-item-included-in-a-optionally-filtered-by-type",
        project_id,
    )
    assert any(item["id"] == inclusion["id"] for item in listed_inclusions["items"])
    removed_inclusion = _cli_json(
        cli_live_engine,
        "projects",
        "remove-inclusion",
        project_id,
        inclusion["id"],
    )
    assert removed_inclusion is None
    deleted_project = _cli_json(cli_live_engine, "projects", "delete", project_id)
    assert deleted_project is None

    updated_defaults = _cli_json(
        cli_live_engine,
        "settings",
        "set-ai-defaults",
        "--text-provider",
        "openai",
        "--text-model",
        "gpt-4o-mini",
    )
    assert updated_defaults["status"] == "ok"
    fetched_defaults = _cli_json(cli_live_engine, "settings", "get-ai-defaults")
    assert fetched_defaults["text_provider"] == "openai"
    assert fetched_defaults["text_model"] == "gpt-4o-mini"

    migrations = _cli_json(cli_live_engine, "migrations", "list")
    assert any(item["name"] == "repair_kg_svo_repr_leak" for item in migrations["migrations"])
    validation = _cli_json(
        cli_live_engine,
        "migrations",
        "validate",
        "--command",
        "repair_kg_svo_repr_leak",
    )
    assert validation["can_run"] is True
    migration_run = _cli_json(
        cli_live_engine,
        "migrations",
        "run",
        "--command",
        "repair_kg_svo_repr_leak",
    )
    assert migration_run["migration_name"] == "repair_kg_svo_repr_leak"
    assert migration_run["status"] == "completed"
    integrity = _cli_json(cli_live_engine, "migrations", "data-integrity-check")
    assert integrity["checks_passed"] is True

    export_dir = tmp_path / "eleventy-site"
    exported_site = _cli_json(
        cli_live_engine,
        "export",
        "eleventy-site-route",
        "--output-path",
        str(export_dir),
        "--overwrite",
        "--site-title",
        "CLI Site",
    )
    assert exported_site["output_path"] == str(export_dir)
    assert export_dir.joinpath("package.json").exists()
    assert any(item["kind"] == "page" for item in exported_site["files"])

    upload_path = tmp_path / "upload.txt"
    upload_path.write_text("hello from cli upload")
    imported_document = _cli_json(
        cli_live_engine,
        "docs",
        "import-file",
        "--upload",
        f"file={upload_path}",
    )
    assert imported_document["name"] == "upload.txt"
    assert imported_document["metadata"]["ingest_mode"] == "copy"
    fetched_import = _cli_json(cli_live_engine, "docs", "get", imported_document["id"])
    assert fetched_import["page_content"] == "hello from cli upload"


def test_generated_library_admin_validation_and_current_reality(
    cli_live_engine,
) -> None:
    unsupported_folder_type = _cli_result(
        cli_live_engine,
        "folders",
        "create",
        "document",
        "--folder-path",
        "/Not Supported",
    )
    assert unsupported_folder_type.exit_code == 1
    assert "-> 422:" in unsupported_folder_type.output

    missing_project = _cli_result(
        cli_live_engine,
        "projects",
        "get",
        "missing-project",
    )
    assert missing_project.exit_code == 1
    assert "-> 404:" in missing_project.output

    migration_run = _cli_json(
        cli_live_engine,
        "migrations",
        "run",
        "--command",
        "repair_kg_svo_repr_leak",
        "--dry-run",
    )
    run_id = migration_run["details"]["run_id"]
    missing_status = _cli_result(
        cli_live_engine,
        "migrations",
        "get-status",
        run_id,
    )
    assert missing_status.exit_code == 1
    assert "-> 404:" in missing_status.output

    for args in (
        (
            "export",
            "eleventy-site-route",
            "--output-path",
            str(cli_live_engine["library"]),
        ),
        (
            "docs",
            "import-file",
            "--upload",
            "file=/definitely/missing.txt",
        ),
    ):
        result = _cli_result(cli_live_engine, *args)
        assert "-> 500:" not in result.output, result.output
