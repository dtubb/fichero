"""Live generated-CLI write coverage for settings, providers, MCP servers, and integrations."""

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


def _cli_provider_writes_ready() -> bool:
    if os.getenv("FICHERO_RUN_CLI_PROVIDER_WRITES") != "1":
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
    except OSError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _cli_provider_writes_ready(),
    reason="Generated CLI provider write contracts are opt-in and require loopback socket access",
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


def test_generated_provider_settings_and_mcp_write_contracts_current_main(
    cli_live_engine,
) -> None:
    defaults = _cli_json(
        cli_live_engine,
        "settings",
        "get-ai-defaults",
    )
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
    fetched_defaults = _cli_json(
        cli_live_engine,
        "settings",
        "get-ai-defaults",
    )
    assert fetched_defaults["text_provider"] == "openai"
    assert fetched_defaults["text_model"] == "gpt-4o-mini"

    profile = _cli_json(
        cli_live_engine,
        "settings",
        "create-model-profile",
        "--name",
        "CLI profile",
        "--provider",
        "openai",
        "--model",
        "gpt-4o-mini",
        "--role",
        "general",
    )
    fetched_profile = _cli_json(
        cli_live_engine,
        "settings",
        "get-model-profile",
        profile["id"],
    )
    assert fetched_profile["name"] == "CLI profile"
    updated_profile = _cli_json(
        cli_live_engine,
        "settings",
        "update-model-profile",
        profile["id"],
        "--model",
        "gpt-4o",
    )
    assert updated_profile["model"] == "gpt-4o"
    deleted_profile = _cli_json(
        cli_live_engine,
        "settings",
        "delete-model-profile",
        profile["id"],
        "--yes",
    )
    assert deleted_profile["status"] == "ok"

    provider = _cli_json(
        cli_live_engine,
        "providers",
        "create",
        "--provider-type",
        "apple",
        "--name",
        "CLI provider",
        "--api-base",
        "http://localhost:11434",
    )
    fetched_provider = _cli_json(cli_live_engine, "providers", "get", provider["id"])
    assert fetched_provider["name"] == "CLI provider"
    disabled_provider = _cli_json(
        cli_live_engine,
        "providers",
        "update",
        provider["id"],
        "--no-enabled",
    )
    assert disabled_provider["enabled"] is False
    enabled_provider = _cli_json(
        cli_live_engine,
        "providers",
        "update",
        provider["id"],
        "--enabled",
    )
    assert enabled_provider["enabled"] is True

    model = _cli_json(
        cli_live_engine,
        "providers",
        "add-model-to",
        provider["id"],
        "--provider-id",
        provider["id"],
        "--model-id",
        "gpt-4o-mini",
        "--name",
        "GPT 4o mini",
        "--is-default",
    )
    assert model["model_id"] == "gpt-4o-mini"
    listed_models = _cli_json(cli_live_engine, "providers", "list-models", provider["id"])
    assert any(item["id"] == model["id"] for item in listed_models["items"])
    removed_model = _cli_json(
        cli_live_engine,
        "providers",
        "remove-model-from",
        provider["id"],
        model["id"],
        "--yes",
    )
    assert removed_model["status"] == "deleted"
    deleted_provider = _cli_json(
        cli_live_engine,
        "providers",
        "delete",
        "--yes",
        provider["id"],
    )
    assert deleted_provider is None

    server = _cli_json(
        cli_live_engine,
        "mcp-servers",
        "create",
        "--name",
        "CLI MCP",
        "--transport",
        "stdio",
        "--command",
        "echo",
        "--args",
        json.dumps(["hi"]),
        "--description",
        "contract server",
    )
    fetched_server = _cli_json(cli_live_engine, "mcp-servers", "get", server["id"])
    assert fetched_server["name"] == "CLI MCP"
    updated_server = _cli_json(
        cli_live_engine,
        "mcp-servers",
        "update",
        server["id"],
        "--description",
        "updated contract server",
        "--no-enabled",
    )
    assert updated_server["description"] == "updated contract server"
    assert updated_server["enabled"] is False
    listed_servers = _cli_json(cli_live_engine, "mcp-servers", "list")
    assert any(item["id"] == server["id"] for item in listed_servers["items"])
    deleted_server = _cli_json(
        cli_live_engine,
        "mcp-servers",
        "delete",
        server["id"],
        "--yes",
    )
    assert deleted_server is not None
    missing_server = _cli_result(
        cli_live_engine,
        "mcp-servers",
        "get",
        server["id"],
    )
    assert missing_server.exit_code == 1
    assert "-> 404:" in missing_server.output

    # reset temp app-db defaults so the fixture stays self-contained
    reset_defaults = _cli_json(
        cli_live_engine,
        "settings",
        "set-ai-defaults",
        "--text-provider",
        defaults["text_provider"],
        "--text-model",
        defaults["text_model"],
    )
    assert reset_defaults["status"] == "ok"


def test_generated_provider_and_integration_no_500_bar_current_main(
    cli_live_engine,
) -> None:
    bad_profile = _cli_result(
        cli_live_engine,
        "settings",
        "create-model-profile",
        "--name",
        "Broken profile",
        "--provider",
        "not-a-provider",
        "--model",
        "broken-model",
    )
    assert bad_profile.exit_code == 1
    assert "-> 422:" in bad_profile.output

    for args in (
        ("providers", "delete-api-key", "openai", "--yes"),
        ("providers", "test-connection", "openai"),
        ("integrations", "list-devonthink-databases"),
        ("integrations", "list-bookends-libraries"),
        ("integrations", "list-tinderbox-documents"),
        ("integrations", "create-tinderbox-note", "--name", "CLI note"),
    ):
        result = _cli_result(cli_live_engine, *args)
        assert "-> 500:" not in result.output, result.output
