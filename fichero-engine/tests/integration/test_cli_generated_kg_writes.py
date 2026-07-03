"""Live generated-CLI write coverage for the current KG surface."""

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
from tests.integration._cli_live import cli_live_engine as _cli_live_engine  # noqa: E402,F401

runner = CliRunner()


def _cli_kg_writes_ready() -> bool:
    if os.getenv("FICHERO_RUN_CLI_KG_WRITES") != "1":
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
    except OSError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _cli_kg_writes_ready(),
    reason="Generated CLI KG write contracts are opt-in and require loopback socket access",
)


def _cli_json(cli_live_engine, *args: str) -> dict:
    result = runner.invoke(
        cli.app,
        [
            "--json",
            "--base-url",
            cli_live_engine["base_url"],
            "--library",
            str(cli_live_engine["library"]),
            *args,
        ],
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _cli_result(cli_live_engine, *args: str):
    return runner.invoke(
        cli.app,
        [
            "--base-url",
            cli_live_engine["base_url"],
            "--library",
            str(cli_live_engine["library"]),
            *args,
        ],
    )


def _get_json(cli_live_engine, path: str) -> dict:
    response = httpx.get(
        f"{cli_live_engine['base_url']}{path}",
        headers={"X-Fichero-Library-Path": str(cli_live_engine["library"])},
        timeout=5,
    )
    response.raise_for_status()
    return response.json()


def test_generated_kg_write_commands_round_trip_current_main(_cli_live_engine) -> None:
    # audit assertions pending KG->registry migration (#3003)
    summary = _cli_live_engine["summary"]

    updated = _cli_json(
        _cli_live_engine,
        "kg",
        "batch-set-claim-curation-state",
        "--claim-ids",
        json.dumps([summary["ids"]["claims"][0]]),
        "--curation-state",
        "curated",
    )
    assert updated == {"claim_ids": [summary["ids"]["claims"][0]], "updated": 1}
    claim = _get_json(_cli_live_engine, f"/api/claims/{summary['ids']['claims'][0]}")
    assert claim["curation_state"] == "curated"

    claim_rule = _cli_json(
        _cli_live_engine,
        "kg",
        "create-claim-rule",
        "--action",
        "disable",
        "--reason",
        "contract test",
        "--match-subject-name",
        "Eugenio Córdoba",
    )
    claim_rules = _cli_json(_cli_live_engine, "kg", "list-claim-rules")
    assert any(item["id"] == claim_rule["id"] for item in claim_rules["items"])
    deleted_claim_rule = _cli_json(
        _cli_live_engine,
        "kg",
        "delete-claim-rule",
        "--rule-id",
        claim_rule["id"],
    )
    assert deleted_claim_rule == {"deleted_rule_id": claim_rule["id"]}

    entity_rule = _cli_json(
        _cli_live_engine,
        "kg",
        "create-entity-rule",
        "--rule-type",
        "alias",
        "--match-canonical-name",
        "Eugenio Córdoba",
        "--target-canonical-name",
        "Eugenio Córdoba",
        "--reason",
        "contract test",
    )
    entity_rules = _cli_json(_cli_live_engine, "kg", "list-entity-rules")
    assert any(item["id"] == entity_rule["id"] for item in entity_rules["items"])
    deleted_entity_rule = _cli_json(
        _cli_live_engine,
        "kg",
        "delete-entity-rule",
        "--rule-id",
        entity_rule["id"],
    )
    assert deleted_entity_rule == {"deleted_rule_id": entity_rule["id"]}

    merged_claims = _cli_json(
        _cli_live_engine,
        "kg",
        "merge-duplicate-claims-into-a-surviving-claim",
        "--absorbed-claim-ids",
        json.dumps([summary["ids"]["claims"][1]]),
        "--surviving-claim-id",
        summary["ids"]["claims"][0],
    )
    merged_claim = _get_json(_cli_live_engine, f"/api/claims/{summary['ids']['claims'][1]}")
    assert merged_claim["merged_into_id"] == summary["ids"]["claims"][0]
    undone_claims = _cli_json(
        _cli_live_engine,
        "kg",
        "reverse-a-recorded-claim-merge",
        "--audit-id",
        merged_claims["id"],
    )
    assert undone_claims["operation_type"] == "unmerge"
    restored_claim = _get_json(_cli_live_engine, f"/api/claims/{summary['ids']['claims'][1]}")
    assert restored_claim["merged_into_id"] is None

    queued_pair = _cli_json(
        _cli_live_engine,
        "kg",
        "manually-queue-an-entity-pair-for-review",
        "--candidate-entity-id",
        "test-ent-org",
        "--survivor-entity-id",
        "test-ent-person",
        "--reason",
        "contract test",
    )
    rejected_pair = _cli_json(
        _cli_live_engine,
        "kg",
        "keep-distinct-labels-this-pair-as-definitely-different",
        queued_pair["id"],
    )
    assert rejected_pair["state"] == "rejected"

    merged_entities = _cli_json(
        _cli_live_engine,
        "kg",
        "merge-entities",
        "--absorbed-entity-ids",
        json.dumps(["test-ent-place"]),
        "--absorbing-entity-id",
        "test-ent-person",
    )
    merged_entity = _get_json(_cli_live_engine, "/api/entities/test-ent-place")
    assert merged_entity["merged_into_id"] == "test-ent-person"
    undone_entity = _cli_json(
        _cli_live_engine,
        "kg",
        "undo-entity-operation",
        merged_entities["id"],
    )
    assert undone_entity["operation_type"] == "undo_merge"
    restored_entity = _get_json(_cli_live_engine, "/api/entities/test-ent-place")
    assert restored_entity["merged_into_id"] is None

    accepted_pair = _cli_json(
        _cli_live_engine,
        "kg",
        "manually-queue-an-entity-pair-for-review",
        "--candidate-entity-id",
        "test-ent-org",
        "--survivor-entity-id",
        "test-ent-person",
    )
    accepted_merge = _cli_json(
        _cli_live_engine,
        "kg",
        "merge-candidate-into-survivor-accept-the-suggested-match",
        accepted_pair["id"],
    )
    assert accepted_merge["survivor_entity_id"] == "test-ent-person"
    assert accepted_merge["absorbed_entity_id"] == "test-ent-org"
    review_merged_entity = _get_json(_cli_live_engine, "/api/entities/test-ent-org")
    assert review_merged_entity["merged_into_id"] == "test-ent-person"


def test_generated_kg_contract_validation_and_no_500_bar(_cli_live_engine) -> None:
    bad_curation = _cli_result(
        _cli_live_engine,
        "kg",
        "batch-set-claim-curation-state",
        "--claim-ids",
        json.dumps(["test-claim-1"]),
        "--curation-state",
        "nope",
    )
    assert bad_curation.exit_code == 1
    assert "-> 422:" in bad_curation.output

    for args in (
        (
            "kg",
            "run-a-sparql-query-against-the-library-s-rdf-graph",
            "--query",
            "SELECT * WHERE { ?s ?p ?o } LIMIT 1",
        ),
        ("kg", "list-prediction-runs"),
        ("kg", "list-example-queries"),
        ("kg", "list-all-pykeen-training-jobs"),
    ):
        result = _cli_result(_cli_live_engine, *args)
        assert "-> 500:" not in result.output, result.output
