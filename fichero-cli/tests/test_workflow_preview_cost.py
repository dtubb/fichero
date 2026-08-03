"""`fichero workflow preview-cost` — ask before you run (#4503).

Twice on 2026-08-03 money was spent because "is this workflow free?" could not
be answered before running. The resolver answers it; until now nobody could
reach the answer without writing Python, and a cost preview only prevents spend
if it is reachable at the moment someone is deciding.

Two properties are load-bearing and both are pinned here:

**It contacts no provider.** A cost preview that costs money is self-defeating.
The server-side resolver already has that guarantee; this extends it through
the CLI path, which is the one an operator actually runs.

**It describes the SERVER's configuration, not this machine's.** The server may
be remote. A preview that read the local app database would confidently
describe the wrong computer — the same "the answer is somewhere the reader is
not looking" failure the preview exists to end. So the defaults come over HTTP.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from fichero_cli.__main__ import app


PAID_DEFAULTS = SimpleNamespace(
    vision_provider="openrouter",
    vision_model="google/gemini-3-flash-preview",
    vision_small_provider="openrouter",
    vision_small_model="google/gemini-3-flash-preview",
    vision_medium_provider="openrouter",
    vision_medium_model="google/gemini-3-flash-preview",
    vision_large_provider="openrouter",
    vision_large_model="google/gemini-3-flash-preview",
    text_provider="openrouter",
    text_model="google/gemini-3-flash-preview",
    small_provider="openrouter",
    small_model="google/gemini-3-flash-preview",
    medium_provider="openrouter",
    medium_model="google/gemini-3-flash-preview",
    large_provider="openrouter",
    large_model="google/gemini-3-flash-preview",
)

ON_DEVICE_DEFAULTS = SimpleNamespace(
    **{
        field: ("apple" if field.endswith("_provider") else "apple-vision")
        for field in vars(PAID_DEFAULTS)
    }
)


def _workflow(nodes):
    return SimpleNamespace(
        id="wf-1",
        name="Transcribe",
        nodes=nodes,
        edges=[],
        direct_runnable=True,
        provider="",
        model="",
    )


def _node(node_id, tool, **cfg):
    return SimpleNamespace(
        id=node_id, tool=tool, config=cfg,
        provider_name=cfg.get("provider_name", ""),
        model_name=cfg.get("model_name", ""),
    )


class _FakeClient:
    """Records every HTTP-ish call the command makes."""

    def __init__(self, defaults, nodes):
        self.defaults = defaults
        self.nodes = nodes
        self.calls: list[str] = []

    def list_workflows(self):
        self.calls.append("list_workflows")
        return [_workflow(self.nodes)]

    def get_settings(self):
        self.calls.append("get_settings")
        return self.defaults

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def run_cli(monkeypatch):
    def _run(defaults, nodes, *, json_out=False):
        client = _FakeClient(defaults, nodes)
        monkeypatch.setattr("fichero_cli.__main__._client", lambda ctx: client)
        monkeypatch.setattr(
            "fichero_cli.__main__._resolve_workflow", lambda c, n: "wf-1"
        )
        args = ["workflow", "preview-cost", "Transcribe"]
        if json_out:
            args = ["--json", *args]
        result = CliRunner().invoke(app, args)
        return result, client

    return _run


class TestItAnswersTheQuestionThatCostMoney:
    def test_an_unpinned_workflow_on_a_paid_server_reads_COSTS_MONEY(self, run_cli):
        result, _ = run_cli(PAID_DEFAULTS, [_node("t", "transcribe")])
        assert result.exit_code == 0, result.output
        assert "COSTS MONEY" in result.output

    def test_the_same_workflow_on_an_on_device_server_reads_FREE(self, run_cli):
        """Same workflow definition, opposite verdict — because the verdict is
        a property of the SERVER, which is the whole finding."""
        result, _ = run_cli(ON_DEVICE_DEFAULTS, [_node("t", "transcribe")])
        assert result.exit_code == 0, result.output
        assert "FREE" in result.output

    def test_surprises_get_their_own_block_not_a_column(self, run_cli):
        """A billable node that looks free from the definition is the shape
        that cost money. A column is how it stayed invisible."""
        result, _ = run_cli(PAID_DEFAULTS, [_node("t", "transcribe")])
        assert "SURPRISES" in result.output
        assert "NOT visible in the workflow definition" in result.output

    def test_it_names_the_layer_that_decided(self, run_cli):
        result, _ = run_cli(PAID_DEFAULTS, [_node("t", "transcribe")])
        assert "app_db" in result.output, (
            "the output must say WHERE the provider came from — 'openrouter, "
            "pinned on the node' and 'openrouter, from the database' are "
            "different facts and only one is a surprise"
        )

    def test_a_node_that_calls_no_model_is_shown_as_such(self, run_cli):
        result, _ = run_cli(PAID_DEFAULTS, [_node("s", "split_images")])
        assert "no model" in result.output
        assert "FREE" in result.output


class TestItIsMachineReadable:
    def test_json_output_parses_and_carries_the_verdict(self, run_cli):
        result, _ = run_cli(PAID_DEFAULTS, [_node("t", "transcribe")], json_out=True)
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["would_cost_money"] is True
        assert payload["free"] is False
        assert payload["surprises"], "surprises must survive into the JSON"
        assert payload["nodes"][0]["decided_by"] == "app_db"

    def test_json_is_gateable_by_a_script(self, run_cli):
        """The next thing someone wants is `if free: run`. Pin that the field
        needed for it is a plain boolean, not prose to be parsed."""
        result, _ = run_cli(ON_DEVICE_DEFAULTS, [_node("t", "transcribe")], json_out=True)
        assert json.loads(result.output)["free"] is True


class TestItMakesNoModelCalls:
    """The guarantee that makes the command safe to run at the deciding moment."""

    def test_it_reads_only_configuration_endpoints(self, run_cli):
        _, client = run_cli(PAID_DEFAULTS, [_node("t", "transcribe")])
        assert set(client.calls) <= {"list_workflows", "get_settings"}, (
            f"the preview called something beyond configuration: {client.calls}"
        )

    def test_no_chat_or_vision_call_is_made(self, run_cli, monkeypatch):
        """Extends the server-side no-call guarantee through the CLI path —
        the one an operator actually runs."""
        import fichero_server.llm as llm_mod

        fired: list[str] = []

        async def _forbidden(*a, **k):
            fired.append("call")
            raise AssertionError("the cost preview contacted a provider")

        for attr in ("chat", "chat_with_fallback", "chat_structured_with_fallback"):
            monkeypatch.setattr(llm_mod, attr, _forbidden, raising=False)

        result, _ = run_cli(PAID_DEFAULTS, [_node("t", "transcribe")])
        assert result.exit_code == 0
        assert fired == []

    def test_it_does_not_read_this_machines_app_database(self, run_cli, monkeypatch):
        """The server may be remote. If the preview fell back to local
        configuration it would describe the wrong computer — confidently."""
        import fichero_server.db.app as app_module

        def _boom():
            raise AssertionError(
                "the preview read the LOCAL app database instead of the "
                "server's settings; on a remote server that answer describes "
                "the wrong machine"
            )

        monkeypatch.setattr(app_module, "get_app_db", _boom)
        result, _ = run_cli(PAID_DEFAULTS, [_node("t", "transcribe")])
        assert result.exit_code == 0, result.output
        assert "COSTS MONEY" in result.output
