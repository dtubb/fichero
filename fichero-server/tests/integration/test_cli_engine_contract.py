"""Live CLI<->engine contract test — the CLI mirror of the Swift
AppEngineContractTests.

Runs against the shared live engine (`_cli_live.cli_live_engine`: an ephemeral port, its own HOME,
a disposable library via the shared seeder),
and drives the real cli.FicheroClient against it. Asserts the values the CLI
decodes equal the library's ground truth — proving the CLI's hand-written
request/parse layer faithfully matches the engine, the gap mock tests can't cover.
"""

from __future__ import annotations


import pytest

from fichero_cli import FicheroClient

# #5187: spawns an engine and waits on it -- a gate under heavy load may retry or exclude it.
pytestmark = pytest.mark.load_sensitive

from tests.integration._cli_live import cli_live_engine  # noqa: E402,F401  (fixture)


@pytest.fixture(scope="module")
def cli_against_seed(cli_live_engine):  # noqa: F811
    """The shared live engine (#5187): its HOME is the test's own, its wait follows the engine's
    progress. This file used to spawn its own engine with the maintainer's REAL home -- an engine
    that must never read the maintainer's state; under load (2026-09-28) it burned 30 CPU-seconds
    after "startup complete" without answering /api/health, where the isolated engine is idle at
    ~3.8 -- and it looked for `<repo>/.venv`, so it was skipped outright in a worktree."""
    client = FicheroClient(base_url=cli_live_engine["base_url"],
                           library_path=str(cli_live_engine["library"]), token=None)
    try:
        yield client, cli_live_engine["summary"]
    finally:
        client.close()


def _expected(summary, key):
    return summary["expected"][key]


def test_cli_documents_match_library(cli_against_seed):
    client, summary = cli_against_seed
    assert len(client.list_documents()) == _expected(summary, "documents_total")
    children = client.list_documents(parent_id=summary["keys"]["collection"])
    assert len(children) == _expected(summary, "children_of_collection")


def test_cli_workflows_match_library(cli_against_seed):
    client, summary = cli_against_seed
    assert len(client.list_workflows()) == _expected(summary, "workflows")


def test_cli_entities_match_library(cli_against_seed):
    client, summary = cli_against_seed
    assert len(client.list_entities()) == _expected(summary, "entities")


def test_cli_claims_match_library(cli_against_seed):
    client, summary = cli_against_seed
    assert len(client.list_claims()) == _expected(summary, "claims")


def test_cli_artifacts_match_library(cli_against_seed):
    client, summary = cli_against_seed
    arts = client.list_artifacts(summary["keys"]["doc_letter"], include_descendants=False)
    assert len(arts) == _expected(summary, "artifacts_for_letter")


def test_cli_create_read_delete_round_trip(cli_against_seed):
    client, _ = cli_against_seed
    created = client.create_entity("ITest Entity", entity_type="other")
    fetched = client.get_entity(created.id)
    assert fetched.id == created.id
    assert fetched.canonical_name == "ITest Entity"
    client.delete_entity(created.id)
