"""Direct tests for auth.py session/loopback/actor helpers (#1979 Test Coverage).

These pure-ish helpers gate security-sensitive behaviour (bootstrap-secret
loopback trust, sliding session refresh, forgery-proof audit actor) but had no
direct test — only the middleware exercised them indirectly. Focus is on the
security edges: forwarded headers defeating loopback trust, env-parsing
validation, and actor resolution falling back to "system".
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from starlette.requests import Request

from fichero_server.api import auth


def _request(client_host: str | None, headers: dict[str, str] | None = None) -> Request:
    headers = headers or {}
    scope = {
        "type": "http",
        "client": (client_host, 54321) if client_host is not None else None,
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "state": {},
    }
    return Request(scope)


# ---------------------------------------------------------------------------
# _is_loopback_request — bootstrap-secret gating (security critical)
# ---------------------------------------------------------------------------


def test_loopback_host_without_forwarding_is_loopback() -> None:
    assert auth._is_loopback_request(_request("127.0.0.1")) is True
    assert auth._is_loopback_request(_request("::1")) is True


def test_non_loopback_host_is_never_loopback() -> None:
    assert auth._is_loopback_request(_request("10.0.0.5")) is False
    assert auth._is_loopback_request(_request(None)) is False


def test_forwarding_header_defeats_loopback_trust() -> None:
    # A proxied request can arrive on 127.0.0.1 but originate elsewhere; any
    # forwarding header must drop it out of the bootstrap-secret trust path.
    for header in ("forwarded", "x-forwarded-for", "x-forwarded-host", "x-real-ip"):
        req = _request("127.0.0.1", {header: "1.2.3.4"})
        assert auth._is_loopback_request(req) is False, header


def test_tailscale_proxy_headers_defeat_loopback_trust() -> None:
    for header, value in (
        ("Tailscale-User-Login", "alice@example.com"),
        ("Tailscale-User-Name", "Alice Example"),
        ("Tailscale-App-Capabilities", "{\"example.com/cap\":true}"),
    ):
        req = _request("127.0.0.1", {header: value})
        assert auth._is_loopback_request(req) is False, header


def test_testclient_host_is_loopback_only_under_pytest(monkeypatch) -> None:
    # _TESTCLIENT_HOSTS are accepted only when PYTEST_CURRENT_TEST is set.
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "x")
    assert auth._is_loopback_request(_request("testserver")) is True
    assert auth._is_loopback_request(_request("testclient", {"x-real-ip": "9.9.9.9"})) is False

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert auth._is_loopback_request(_request("testserver")) is False


def test_rate_limit_scope_prefers_tailscale_identity_over_loopback_host() -> None:
    req = _request("127.0.0.1", {"Tailscale-User-Login": "alice@example.com"})
    assert auth._rate_limit_scope_from_request(req) == "proxy:alice@example.com"


# ---------------------------------------------------------------------------
# _should_touch_last_seen — throttle boundary
# ---------------------------------------------------------------------------


def test_should_touch_last_seen_boundary() -> None:
    now = datetime(2026, 6, 27, 12, 0, 0)
    throttle = auth._LAST_SEEN_THROTTLE_SECONDS
    assert auth._should_touch_last_seen(now - timedelta(seconds=throttle - 1), now) is False
    assert auth._should_touch_last_seen(now - timedelta(seconds=throttle), now) is True
    assert auth._should_touch_last_seen(now - timedelta(seconds=throttle + 5), now) is True
    # Clock skew (last_seen in the future) must not trigger a touch.
    assert auth._should_touch_last_seen(now + timedelta(seconds=10), now) is False


# ---------------------------------------------------------------------------
# _session_refresh_window — env parsing/validation
# ---------------------------------------------------------------------------


def test_refresh_window_unset_or_blank_is_none(monkeypatch) -> None:
    monkeypatch.delenv("FICHERO_SESSION_SLIDING_REFRESH_WINDOW_SECONDS", raising=False)
    assert auth._session_refresh_window() is None
    monkeypatch.setenv("FICHERO_SESSION_SLIDING_REFRESH_WINDOW_SECONDS", "   ")
    assert auth._session_refresh_window() is None


def test_refresh_window_invalid_or_nonpositive_is_none(monkeypatch) -> None:
    for value in ("notanint", "0", "-30", "3.5"):
        monkeypatch.setenv("FICHERO_SESSION_SLIDING_REFRESH_WINDOW_SECONDS", value)
        assert auth._session_refresh_window() is None, value


def test_refresh_window_valid_seconds(monkeypatch) -> None:
    monkeypatch.setenv("FICHERO_SESSION_SLIDING_REFRESH_WINDOW_SECONDS", "3600")
    assert auth._session_refresh_window() == timedelta(seconds=3600)


# ---------------------------------------------------------------------------
# _session_expiry_should_refresh — depends on the window
# ---------------------------------------------------------------------------


def test_expiry_refresh_false_when_window_unset(monkeypatch) -> None:
    monkeypatch.delenv("FICHERO_SESSION_SLIDING_REFRESH_WINDOW_SECONDS", raising=False)
    now = datetime(2026, 6, 27, 12, 0, 0)
    assert auth._session_expiry_should_refresh(now + timedelta(seconds=1), now) is False


def test_expiry_refresh_only_within_window(monkeypatch) -> None:
    monkeypatch.setenv("FICHERO_SESSION_SLIDING_REFRESH_WINDOW_SECONDS", "100")
    now = datetime(2026, 6, 27, 12, 0, 0)
    # Expires well outside the window -> no refresh.
    assert auth._session_expiry_should_refresh(now + timedelta(seconds=500), now) is False
    # Expires inside the window -> refresh.
    assert auth._session_expiry_should_refresh(now + timedelta(seconds=50), now) is True
    # Already expired (<= window, even negative) -> refresh.
    assert auth._session_expiry_should_refresh(now - timedelta(seconds=10), now) is True


# ---------------------------------------------------------------------------
# actor_from_request / request_actor — forgery-proof actor resolution
# ---------------------------------------------------------------------------


def test_actor_is_system_when_no_user() -> None:
    req = _request("127.0.0.1")
    # request.state has no `user` attribute at all.
    assert auth.actor_from_request(req) == "system"
    assert auth.request_actor(req) == "system"


def test_actor_prefers_username_then_id_then_system() -> None:
    req = _request("127.0.0.1")
    req.state.user = SimpleNamespace(username="alice", id="u-1")
    assert auth.actor_from_request(req) == "alice"

    req.state.user = SimpleNamespace(username=None, id="u-2")
    assert auth.actor_from_request(req) == "u-2"

    req.state.user = SimpleNamespace(username=None, id=None)
    assert auth.actor_from_request(req) == "system"


def test_actor_ignores_header_supplied_identity() -> None:
    # Identity must come only from middleware-populated state, never headers.
    req = _request("127.0.0.1", {"x-fichero-actor": "mallory", "x-user": "mallory"})
    assert auth.actor_from_request(req) == "system"
