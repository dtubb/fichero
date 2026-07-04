"""Live generated-CLI contract coverage for search, citations, bibliography, references, and sources."""

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


def _cli_search_contracts_ready() -> bool:
    if os.getenv("FICHERO_RUN_CLI_SEARCH_CONTRACTS") != "1":
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
    except OSError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _cli_search_contracts_ready(),
    reason="Generated CLI search/citation contracts are opt-in and require loopback socket access",
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


def _latest_audit(live_engine, action_name: str, target_id: str) -> dict:
    audit = _cli_json(live_engine, "actions", "list-audit-log", "--limit", "20")
    for item in audit["items"]:
        if item["action_name"] == action_name and target_id in item["target_ids"]:
            return item
    raise AssertionError(f"missing audit row for {action_name} {target_id}")


def test_generated_search_citation_bibliography_and_source_contracts_current_main(
    cli_live_engine,
) -> None:
    summary = cli_live_engine["summary"]
    doc_id = summary["keys"]["doc_letter"]
    target_doc_id = summary["keys"]["doc_photo"]

    explanation = _cli_json(
        cli_live_engine,
        "search-api",
        "explain-a-query",
        "--query",
        "letter",
        "--search-type",
        "hybrid",
    )
    assert explanation["query"] == "letter"
    assert explanation["search_type"] == "hybrid"

    explained_by_path = _cli_json(
        cli_live_engine,
        "search-api",
        "explain-by-path",
        "letter",
    )
    assert explained_by_path["query"] == "letter"

    keyword_cloud = _cli_json(
        cli_live_engine,
        "search-api",
        "keyword-cloud",
        "--limit",
        "5",
    )
    assert "count" in keyword_cloud
    assert "items" in keyword_cloud

    citation = _cli_json(
        cli_live_engine,
        "citations",
        "record-a-from-one-document-to-another",
        "--source-document-id",
        doc_id,
        "--target-document-id",
        target_doc_id,
        "--target-citation-text",
        "Photo archive citation",
        "--page-label",
        "12",
    )
    created_audit = _latest_audit(cli_live_engine, "citation.create", citation["id"])
    assert created_audit["undoable"] is True
    outbound = _cli_json(
        cli_live_engine,
        "citations",
        "from-this-document-what-it-cites",
        doc_id,
    )
    assert any(item["id"] == citation["id"] for item in outbound["items"])
    inbound = _cli_json(
        cli_live_engine,
        "citations",
        "to-this-document-what-cites-it",
        target_doc_id,
    )
    assert any(item["id"] == citation["id"] for item in inbound["items"])
    patched_citation = _cli_json(
        cli_live_engine,
        "citations",
        "patch",
        citation["id"],
        "--target-citation-text",
        "Updated archive citation",
        "--confidence",
        "0.8",
    )
    assert patched_citation["target_citation_text"] == "Updated archive citation"
    assert patched_citation["confidence"] == 0.8
    patched_audit = _latest_audit(cli_live_engine, "citation.patch", citation["id"])
    assert patched_audit["undoable"] is True
    deleted_citation = _cli_json(
        cli_live_engine,
        "citations",
        "delete",
        citation["id"],
    )
    assert deleted_citation is None
    deleted_audit = _latest_audit(cli_live_engine, "citation.delete", citation["id"])
    assert deleted_audit["undoable"] is True

    # audit assertions pending /api/bibliography->registry migration (#3045)
    attached = _cli_json(
        cli_live_engine,
        "bibliography",
        "attach-a-bibtex-ris-csl-json-record-to-a-document",
        doc_id,
        "--format",
        "csl_json",
        "--text",
        json.dumps(
            {
                "title": "Seed Title",
                "author": [{"family": "Tubb", "given": "Daniel"}],
                "type": "book",
            }
        ),
    )
    assert attached["document_id"] == doc_id
    assert attached["metadata"]["title"] == "Seed Title"
    metadata = _cli_json(
        cli_live_engine,
        "bibliography",
        "get-a-document-s-bibliographic-metadata",
        doc_id,
    )
    assert metadata["metadata"]["title"] == "Seed Title"
    patched_metadata = _cli_json(
        cli_live_engine,
        "bibliography",
        "set-or-update-a-document-s-bibliographic-metadata",
        doc_id,
        "--metadata",
        json.dumps({"title": "Patched Title", "author": "Codex"}),
    )
    assert patched_metadata["metadata"]["title"] == "Patched Title"
    parsed_bib = _cli_json(
        cli_live_engine,
        "bibliography",
        "parse-bibtex-ris-csl-json-into-sourcemetadata-dicts-909",
        "--format",
        "csl_json",
        "--text",
        json.dumps(
            {
                "title": "Parsed Title",
                "author": [{"family": "Codex", "given": "Worker"}],
                "type": "book",
            }
        ),
    )
    assert parsed_bib["count"] == 1
    exported_bib = _cli_result(
        cli_live_engine,
        "bibliography",
        "bulk-export-multiple-documents-as-bibtex",
        "--document-ids",
        json.dumps([doc_id]),
    )
    assert exported_bib.exit_code == 0
    assert "@" in exported_bib.output

    source = _cli_json(
        cli_live_engine,
        "sources",
        "upsert",
        "--title",
        "CLI Source",
        "--file-path",
        "/tmp/cli-source.txt",
        "--metadata",
        json.dumps({"kind": "external"}),
    )
    created_source_audit = _latest_audit(cli_live_engine, "source.upsert", source["id"])
    assert created_source_audit["undoable"] is True
    fetched_source = _cli_json(cli_live_engine, "sources", "get", source["id"])
    assert fetched_source["title"] == "CLI Source"
    updated_source = _cli_json(
        cli_live_engine,
        "sources",
        "update",
        source["id"],
        "--title",
        "CLI Source Updated",
        "--file-path",
        "/tmp/cli-source-updated.txt",
    )
    assert updated_source["title"] == "CLI Source Updated"
    updated_source_audit = _latest_audit(cli_live_engine, "source.update", source["id"])
    assert updated_source_audit["undoable"] is True
    listed_sources = _cli_json(cli_live_engine, "sources", "list")
    assert any(item["id"] == source["id"] for item in listed_sources["items"])
    deleted_source = _cli_json(
        cli_live_engine,
        "sources",
        "delete",
        source["id"],
    )
    assert deleted_source is None
    deleted_source_audit = _latest_audit(cli_live_engine, "source.delete", source["id"])
    assert deleted_source_audit["undoable"] is True

    # audit assertions pending /api/references->registry migration (#3046)
    listed_references = _cli_json(cli_live_engine, "references", "list")
    assert listed_references["count"] == 0


def test_generated_search_reference_and_bibliography_validation_no_500_current_main(
    cli_live_engine,
) -> None:
    empty_query = _cli_result(
        cli_live_engine,
        "search-api",
        "explain-a-query",
        "--query",
        "",
    )
    assert empty_query.exit_code == 1
    assert "-> 422:" in empty_query.output

    bad_source = _cli_result(
        cli_live_engine,
        "sources",
        "upsert",
        "--title",
        "Bad Source",
        "--file-path",
        "/tmp/bad-source.txt",
        "--document-type",
        "note",
    )
    assert bad_source.exit_code == 1
    assert "-> 400:" in bad_source.output

    missing_reference = _cli_result(
        cli_live_engine,
        "references",
        "get",
        "missing-reference",
    )
    assert missing_reference.exit_code == 1
    assert "-> 404:" in missing_reference.output

    for args in (
        (
            "bibliography",
            "resolve-a-doi-or-isbn-via-crossref-open-library-910",
            "--doi",
            "10.0000/does-not-exist",
        ),
        (
            "citations",
            "bulk-export-bibtex-for-a-list-of-documents",
            "--document-ids",
            json.dumps([cli_live_engine["summary"]["keys"]["doc_letter"]]),
        ),
    ):
        result = _cli_result(cli_live_engine, *args)
        assert "-> 500:" not in result.output, result.output
