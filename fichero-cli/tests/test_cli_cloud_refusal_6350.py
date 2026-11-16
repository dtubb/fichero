"""`ai.cloud.cli-refuses-in-words` (#6350): `fichero workflow run` prints a cloud refusal's words, figures and each way through,
and exits 3 (not 1, not a traceback); the two one-run flags are sent."""
from __future__ import annotations

from typer.testing import CliRunner

from fichero_cli import __main__ as cli
from fichero_cli import cloud_refusal
from fichero_cli.client import CloudRefusedError

CAP = {"kind": "cap-monthly", "scope": "app", "project": "P", "cap_usd": 10.0, "spent_usd": 9.9, "estimate_usd": 0.5,
       "words": "This call could cost up to $0.50 and this project's cloud spend is capped at $10.00 a month, of which $9.90 is spent this month.",
       "fixes": [{"kind": "raise-to", "usd": 10.4}, {"kind": "over-cap-once"}, {"kind": "open-settings", "control": "settings.ai.cloudCaps"}]}
IMAGES = {"kind": "images", "scope": "project", "project": "P", "words": "The project P keeps its pages on this Mac.",
          "fixes": [{"kind": "allow-everywhere"}, {"kind": "allow-project"}, {"kind": "allow-once"},
                    {"kind": "open-settings", "control": "settings.ai.cloudAllowed"}]}


def test_a_cap_refusal_says_the_figures_and_each_route():
    text = cloud_refusal.words(CAP)
    assert "capped at $10.00 a month" in text and "cap $10.00, spent $9.90" in text
    assert "fichero ai put-cloud-cap --which monthly --cap-usd 10.40" in text
    assert "--over-cap-once" in text and "settings.ai.cloudCaps" in text


def test_an_images_refusal_names_the_commands_and_the_flag():
    text = cloud_refusal.words(IMAGES)
    assert "fichero recipes allow-cloud" in text and "--allow-cloud-once" in text and "put-places" in text


def test_a_project_cap_routes_to_the_project_command():
    text = cloud_refusal.words({**CAP, "scope": "project"})
    assert "fichero recipes change-cloud-cap --cap-usd 10.40" in text


class _Client:
    def __init__(self, refusal=None):
        self.refusal, self.sent = refusal, {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def run_workflow(self, workflow_id, inputs, **kw):
        self.sent = kw
        if self.refusal:
            raise CloudRefusedError(self.refusal["words"], self.refusal)
        return {"thread_id": "t1"}


def _run(monkeypatch, client, *args):
    monkeypatch.setattr(cli, "_client", lambda ctx: client)
    monkeypatch.setattr(cli, "_resolve_workflow", lambda c, name: "wf")
    return CliRunner().invoke(cli.app, ["workflow", "run", "W", "doc-1", *args])


def test_the_command_exits_3_with_the_words_not_a_traceback(monkeypatch):
    result = _run(monkeypatch, _Client(CAP))
    assert result.exit_code == 3, result.output
    assert "Ways through:" in result.stderr and "Traceback" not in result.stderr


def test_the_flags_are_sent(monkeypatch):
    client = _Client()
    result = _run(monkeypatch, client, "--allow-cloud-once", "--over-cap-once")
    assert result.exit_code == 0, result.output
    assert client.sent == {"provider_override": None, "model_override": None, "allow_cloud_once": True, "over_cap_once": True}


def _refusing_client():
    import httpx

    from fichero_cli.client import FicheroClient

    body = {"detail": {"message": "capped", "refusal": CAP}}
    return FicheroClient(base_url="http://engine.test", token="t",
                         transport=httpx.MockTransport(lambda request: httpx.Response(400, json=body)))


def test_the_real_client_raises_a_fichero_error_subclass_that_keeps_the_refusal():
    from fichero_cli.client import FicheroError

    with _refusing_client() as client:
        try:
            client.request("GET", "/api/auth/me")
        except FicheroError as exc:
            assert isinstance(exc, CloudRefusedError) and exc.status_code == 400
            assert exc.refusal["kind"] == "cap-monthly" and exc.detail["refusal"] == CAP
        else:
            raise AssertionError("a cloud refusal was not raised")


def test_a_command_that_is_not_a_run_prints_the_words_not_a_traceback(monkeypatch):
    monkeypatch.setattr(cli, "_client", lambda ctx: _refusing_client())
    result = CliRunner().invoke(cli.app, ["auth", "whoami"])
    assert result.exit_code != 0 and "Traceback" not in result.output
    assert "capped at $10.00 a month" in result.output
