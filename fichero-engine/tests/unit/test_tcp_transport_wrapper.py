"""The local control surface is unreachable over TCP (#4222).

Both listeners serve ONE FastAPI application — `uds_transport` is middleware
that stamps a marker, not a second app — so a route added to `main:app` is
reachable on BOTH transports. The sharing control surface must not be: a remote
device asking the engine to open a port for it is the thing this prevents.

`tcp_transport` withholds those paths at the TCP entry point, so the request
never reaches the handler. That is structural, not an authz check inside the
handler that a future marker-stamping code path could satisfy.

The route stays a normal FastAPI route, so it keeps its OpenAPI schema and its
generated Swift client — the cost of deleting it from the app instead would be
a hand-rolled client call and a contract outside the spec (#4211's problem).

The weakness of an entry-point guarantee is that it holds only while every TCP
launcher uses the wrapper; `scripts/check_tcp_transport_wrapper.py` is what
makes a bare-app launcher a failing gate rather than a silent open door.
"""

from __future__ import annotations

import pytest

from fichero.api.tcp_transport import (
    LOCAL_ONLY_PREFIXES,
    TCPTransportApp,
    app as tcp_app,
    is_local_only_path,
)
from fichero.api.uds_transport import app as uds_app


class TestThePathRule:
    @pytest.mark.parametrize(
        "path",
        ["/api/sharing", "/api/sharing/", "/api/sharing/enable", "/api/sharing/status"],
    )
    def test_control_surface_paths_are_local_only(self, path):
        assert is_local_only_path(path)

    @pytest.mark.parametrize(
        "path",
        [
            "/api/health",
            "/api/documents",
            "/api/sharingx",  # prefix must not match a longer sibling segment
            "/api/shared",
            "/",
        ],
    )
    def test_everything_else_is_served(self, path):
        assert not is_local_only_path(path)

    def test_a_sibling_segment_is_not_captured(self):
        """`/api/sharingx` starts with the prefix as a STRING but is a different
        route. Matching on raw `startswith` alone would swallow it."""
        assert not is_local_only_path("/api/sharingx/enable")


class TestBothEntryPointsServeTheSameApp:
    """The premise. If this stops being true, the whole design changes."""

    def test_uds_and_tcp_wrap_one_application(self):
        assert uds_app._app is tcp_app._app


class TestTCPWithholdsTheControlSurface:
    @staticmethod
    async def _call(app, path: str, scope_type: str = "http"):
        sent: list[dict] = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        await app({"type": scope_type, "path": path, "headers": [], "method": "GET"}, receive, send)
        return sent

    @pytest.mark.anyio
    async def test_tcp_returns_404_without_reaching_the_app(self):
        """404, not 403: from the TCP surface the route does not exist."""
        reached = []

        async def spy(scope, receive, send):
            reached.append(scope["path"])

        sent = await self._call(TCPTransportApp(spy), "/api/sharing/enable")

        assert not reached, "the request reached the application"
        assert sent[0]["status"] == 404

    @pytest.mark.anyio
    async def test_tcp_forwards_everything_else(self):
        reached = []

        async def spy(scope, receive, send):
            reached.append(scope["path"])

        await self._call(TCPTransportApp(spy), "/api/documents")

        assert reached == ["/api/documents"]

    @pytest.mark.anyio
    async def test_uds_forwards_the_control_surface(self):
        """The other half of the guarantee: it IS reachable locally."""
        from fichero.api.uds_transport import UDSTransportApp

        reached = []

        async def spy(scope, receive, send):
            reached.append(scope["path"])

        await self._call(UDSTransportApp(spy), "/api/sharing/enable")

        assert reached == ["/api/sharing/enable"], "UDS must serve the control surface"

    @pytest.mark.anyio
    async def test_a_websocket_upgrade_is_refused_too(self):
        """Blocking only HTTP would leave a websocket route reachable."""
        sent = await self._call(TCPTransportApp(None), "/api/sharing/ws", "websocket")

        assert sent[0]["type"] == "websocket.close"


class TestTheGuardrailCoversTheEntryPoints:
    """The entry-point guarantee is only as good as the check that enforces it."""

    def test_no_launcher_serves_the_bare_app(self):
        import importlib.util
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        spec = importlib.util.spec_from_file_location(
            "_tcp_wrapper_check", root / "scripts" / "check_tcp_transport_wrapper.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        offenders = sorted(set(module.scan()) - set(module.ALLOWLIST_REASONS))

        assert not offenders, f"launchers serving the bare app: {offenders}"

    def test_every_allowlist_entry_states_a_reason(self):
        import importlib.util
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        spec = importlib.util.spec_from_file_location(
            "_tcp_wrapper_check2", root / "scripts" / "check_tcp_transport_wrapper.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        for rel, reason in module.ALLOWLIST_REASONS.items():
            assert len(reason.strip()) > 20, f"{rel} needs a real reason, got {reason!r}"


def test_the_prefix_list_is_not_empty():
    """A wrapper withholding nothing would pass every other test here."""
    assert LOCAL_ONLY_PREFIXES
