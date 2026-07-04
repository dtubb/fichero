"""Live generated-CLI write coverage for canonical knowledge routes."""

from __future__ import annotations

import json
import os
import socket

import httpx
import pytest
from typer.testing import CliRunner

os.environ.setdefault("FICHERO_FEATURE_TIER", "dev")
os.environ.setdefault("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
os.environ.setdefault("FICHERO_DISABLE_AUTH", "1")

from fichero import __main__ as cli  # noqa: E402

pytest_plugins = ["tests.integration._cli_live"]

runner = CliRunner()


def _cli_knowledge_writes_ready() -> bool:
    if os.getenv("FICHERO_RUN_CLI_KNOWLEDGE_WRITES") != "1":
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
    except OSError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _cli_knowledge_writes_ready(),
    reason="Generated CLI knowledge write contracts are opt-in and require loopback socket access",
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


def test_generated_knowledge_write_contracts_current_main(cli_live_engine) -> None:
    summary = cli_live_engine["summary"]

    before_entity_create = _audit_log(cli_live_engine)
    entity = _cli_json(
        cli_live_engine,
        "entity",
        "create",
        "CLI Contract Entity",
        "--type",
        "person",
        "--alias",
        "C. Contract",
    )
    entity_id = entity["id"]
    after_entity_create = _audit_log(cli_live_engine)
    assert after_entity_create["count"] == before_entity_create["count"] + 1
    assert after_entity_create["items"][0]["action_name"] == "entity.create"
    assert entity["aliases"] == ["C. Contract"]

    patched_entity = _cli_json(
        cli_live_engine,
        "entity",
        "update",
        entity_id,
        "--name",
        "CLI Contract Entity Updated",
        "--description",
        "round trip",
    )
    assert patched_entity["canonical_name"] == "CLI Contract Entity Updated"
    after_entity_patch = _audit_log(cli_live_engine)
    assert after_entity_patch["count"] == after_entity_create["count"] + 1
    assert after_entity_patch["items"][0]["action_name"] == "entity.update"

    claim = _cli_json(
        cli_live_engine,
        "claim",
        "create",
        "CLI contract claim",
        "--doc-id",
        summary["keys"]["doc_letter"],
        "--entity",
        entity_id,
        "--confidence",
        "0.8",
    )
    claim_id = claim["id"]
    after_claim_create = _audit_log(cli_live_engine)
    assert after_claim_create["count"] == after_entity_patch["count"] + 1
    assert after_claim_create["items"][0]["action_name"] == "claim.create"

    patched_claim = _cli_json(
        cli_live_engine,
        "claim",
        "update",
        claim_id,
        "--curation-state",
        "curated",
        "--confidence",
        "0.9",
    )
    assert patched_claim["curation_state"] == "curated"
    fetched_claim = _cli_json(cli_live_engine, "claim", "get", claim_id)
    assert fetched_claim["curation_state"] == "curated"
    after_claim_patch = _audit_log(cli_live_engine)
    assert after_claim_patch["count"] == after_claim_create["count"] + 1
    assert after_claim_patch["items"][0]["action_name"] == "claim.patch"

    # audit assertions pending /api/claim-links->registry migration (#3020)
    before_link = _audit_log(cli_live_engine)
    link = _cli_json(
        cli_live_engine,
        "claim",
        "create-link",
        claim_id,
        "--related-claim-id",
        summary["ids"]["claims"][0],
        "--relation-type",
        "supports",
        "--evidence",
        "contract test",
    )
    link_id = link["id"]
    listed_links = _cli_json(cli_live_engine, "claim", "list-links", claim_id)
    assert any(item["id"] == link_id for item in listed_links["items"])
    related_claims = _cli_json(cli_live_engine, "claim", "get-related", claim_id)
    assert any(item["id"] == summary["ids"]["claims"][0] for item in related_claims["items"])
    updated_link = _cli_json(
        cli_live_engine,
        "claim-links",
        "update",
        link_id,
        "--relation-type",
        "corroborates",
        "--link-quality",
        "0.95",
    )
    assert updated_link["relation_type"] == "corroborates"
    deleted_link = _cli_json(cli_live_engine, "claim-links", "delete", link_id, "--yes")
    assert deleted_link["operation"] == "deleted"
    after_link = _audit_log(cli_live_engine)
    assert after_link["count"] == before_link["count"]

    # audit assertions pending /api/annotations->registry migration (#3021)
    before_annotation = _audit_log(cli_live_engine)
    annotation = _cli_json(
        cli_live_engine,
        "annotations",
        "create-an",
        "--document-id",
        summary["keys"]["doc_letter"],
        "--kind",
        "highlight",
        "--char-start",
        "0",
        "--char-end",
        "5",
        "--text",
        "Hello",
        "--tags",
        json.dumps(["primary"]),
        "--linked-claim-ids",
        json.dumps([summary["ids"]["claims"][0]]),
    )
    annotation_id = annotation["id"]
    assert annotation["char_start"] == 0
    assert annotation["char_end"] == 5
    crop = _get(cli_live_engine, f"/api/annotations/{annotation_id}/crop")
    assert crop.status_code == 200
    assert crop.text == "A let"
    patched_annotation = _cli_json(
        cli_live_engine,
        "annotations",
        "patch",
        annotation_id,
        "--text",
        "Hello world",
        "--tags",
        json.dumps(["primary", "w3c"]),
    )
    assert patched_annotation["text"] == "Hello world"
    assert patched_annotation["tags"] == ["primary", "w3c"]
    fetched_annotation = _cli_json(cli_live_engine, "annotations", "get", annotation_id)
    assert fetched_annotation["text"] == "Hello world"
    deleted_annotation = _cli_result(
        cli_live_engine, "annotations", "delete", annotation_id, "--yes"
    )
    assert deleted_annotation.exit_code == 0, deleted_annotation.output
    after_annotation = _audit_log(cli_live_engine)
    assert after_annotation["count"] == before_annotation["count"]

    # audit assertions pending /api/classifications->registry migration (#3022)
    before_classification = _audit_log(cli_live_engine)
    value = _cli_json(
        cli_live_engine,
        "classifications",
        "add-a-custom-value",
        "--dimension",
        "node_class",
        "--key",
        "cli-contract",
        "--label",
        "CLI Contract",
        "--color",
        "#abcdef",
    )
    value_id = value["id"]
    listed_values = _cli_json(
        cli_live_engine,
        "classifications",
        "list-values-filter-by-dimension",
        "--dimension",
        "node_class",
    )
    assert any(item["id"] == value_id for item in listed_values["items"])
    patched_value = _cli_json(
        cli_live_engine,
        "classifications",
        "edit-a-value-s-label-color-order",
        value_id,
        "--label",
        "CLI Contract Updated",
        "--sort-order",
        "5",
    )
    assert patched_value["label"] == "CLI Contract Updated"
    deleted_value = _cli_result(
        cli_live_engine,
        "classifications",
        "delete-value",
        value_id,
        "--yes",
    )
    assert deleted_value.exit_code == 0, deleted_value.output
    after_classification = _audit_log(cli_live_engine)
    assert after_classification["count"] == before_classification["count"]

    deleted_claim = _cli_result(cli_live_engine, "claim", "delete", claim_id, "--yes")
    assert deleted_claim.exit_code == 0, deleted_claim.output
    after_claim_delete = _audit_log(cli_live_engine)
    assert after_claim_delete["count"] == after_classification["count"] + 1
    assert after_claim_delete["items"][0]["action_name"] == "claim.delete"

    deleted_entity = _cli_result(cli_live_engine, "entity", "delete", entity_id, "--yes")
    assert deleted_entity.exit_code == 0, deleted_entity.output
    after_entity_delete = _audit_log(cli_live_engine)
    assert after_entity_delete["count"] == after_claim_delete["count"] + 1
    assert after_entity_delete["items"][0]["action_name"] == "entity.delete"


def test_generated_knowledge_write_validation_current_main(cli_live_engine) -> None:
    bad_entity = _cli_result(
        cli_live_engine,
        "entity",
        "create",
        "1234",
    )
    assert bad_entity.exit_code == 1
    assert "-> 422:" in bad_entity.output
