"""Security-scoped bookmark resolution for the sandboxed engine (#3747).

A real grant needs an entitled, sandboxed parent, so the Foundation call itself is
faked here. What IS tested is everything that can silently go wrong around it: the
env payload parsing, the fail-soft behaviour, the stale-bookmark path, and — most
importantly — that a resolved URL is HELD, because access is revoked the moment the
URL is released.
"""

from __future__ import annotations

import base64
import json

import pytest

from fichero import security_scoped_access as ssa


@pytest.fixture(autouse=True)
def _clear_active_urls():
    ssa._ACTIVE_URLS.clear()
    yield
    ssa._ACTIVE_URLS.clear()


def _payload(mapping: dict[str, bytes]) -> str:
    return json.dumps({p: base64.b64encode(b).decode() for p, b in mapping.items()})


class FakeURL:
    def __init__(self, granted=True):
        self.granted = granted
        self.started = 0

    def startAccessingSecurityScopedResource(self):  # noqa: N802 - PyObjC name
        self.started += 1
        return self.granted


class FakeFoundation:
    """Stands in for PyObjC Foundation. Signature matches the real selector."""

    NSURLBookmarkResolutionWithSecurityScope = 1024

    def __init__(self, url=None, stale=False, error=None):
        self._url = url if url is not None else FakeURL()
        self._stale = stale
        self._error = error
        self.calls = []

        outer = self

        class NSURL:
            @staticmethod
            def URLByResolvingBookmarkData_options_relativeToURL_bookmarkDataIsStale_error_(  # noqa: N802
                data, options, relative, stale, error
            ):
                outer.calls.append((data, options))
                return (outer._url, outer._stale, outer._error)

        self.NSURL = NSURL


# --- parsing: the payload is attacker-adjacent (it crosses a process boundary) ---


def test_parses_paths_and_base64():
    out = ssa.parse_bookmarks(_payload({"/Users/d/Documents/L.fichero": b"BOOKMARKBYTES"}))
    assert out == {"/Users/d/Documents/L.fichero": b"BOOKMARKBYTES"}


def test_empty_and_missing_payloads_are_noops():
    assert ssa.parse_bookmarks(None) == {}
    assert ssa.parse_bookmarks("") == {}
    assert ssa.parse_bookmarks("   ") == {}


def test_malformed_json_does_not_raise():
    # A corrupt bookmark must never stop the engine booting.
    assert ssa.parse_bookmarks("{not json") == {}


def test_non_object_json_rejected():
    assert ssa.parse_bookmarks('["a", "b"]') == {}


def test_bad_base64_entry_is_skipped_not_fatal():
    raw = json.dumps({"/good": base64.b64encode(b"ok").decode(), "/bad": "!!!not base64!!!"})
    assert ssa.parse_bookmarks(raw) == {"/good": b"ok"}


def test_multiple_libraries_each_get_an_entry():
    out = ssa.parse_bookmarks(_payload({"/a": b"1", "/b": b"2"}))
    assert out == {"/a": b"1", "/b": b"2"}


# --- resolution ---


def test_start_access_grants_and_uses_security_scope_option():
    f = FakeFoundation()
    assert ssa.start_access("/lib", b"data", f) is True
    assert f._url.started == 1
    # The option MUST be WithSecurityScope; without it the resolve gives a URL that
    # cannot actually be accessed.
    assert f.calls == [(b"data", 1024)]


def test_resolved_url_is_HELD_alive():
    # Access lasts only while the URL lives. Dropping it silently revokes the grant.
    f = FakeFoundation()
    ssa.start_access("/lib", b"data", f)
    assert ssa._ACTIVE_URLS == [f._url]


def test_denied_access_returns_false():
    f = FakeFoundation(url=FakeURL(granted=False))
    assert ssa.start_access("/lib", b"data", f) is False
    assert ssa._ACTIVE_URLS == []


def test_resolution_error_returns_false():
    f = FakeFoundation(error="NSError: bookmark corrupt")
    assert ssa.start_access("/lib", b"data", f) is False
    assert ssa._ACTIVE_URLS == []


def test_stale_bookmark_still_grants_access():
    # Stale means "the app should re-mint it", not "unusable" — the user keeps working.
    f = FakeFoundation(stale=True)
    assert ssa.start_access("/lib", b"data", f) is True


# --- the top-level entry point ---


def test_activate_returns_granted_paths(monkeypatch):
    f = FakeFoundation()
    monkeypatch.setattr(ssa, "_load_foundation", lambda: f)
    granted = ssa.activate_library_bookmarks(_payload({"/lib": b"x"}))
    assert granted == ["/lib"]


def test_activate_is_a_noop_without_the_env_var(monkeypatch):
    monkeypatch.delenv(ssa.ENV_VAR, raising=False)
    called = []
    monkeypatch.setattr(ssa, "_load_foundation", lambda: called.append(1))
    # Nothing to do → must not even reach for Foundation (the DMG build has no bookmarks).
    assert ssa.activate_library_bookmarks() == []
    assert called == []


def test_activate_without_pyobjc_does_not_raise(monkeypatch):
    monkeypatch.setattr(ssa, "_load_foundation", lambda: None)
    assert ssa.activate_library_bookmarks(_payload({"/lib": b"x"})) == []


def test_activate_partial_grant_reports_only_the_successes(monkeypatch):
    f = FakeFoundation()
    granted_paths = []

    def fake_start(path, data, foundation):
        ok = data != b"deny"
        if ok:
            granted_paths.append(path)
        return ok

    monkeypatch.setattr(ssa, "_load_foundation", lambda: f)
    monkeypatch.setattr(ssa, "start_access", fake_start)
    granted = ssa.activate_library_bookmarks(_payload({"/ok": b"yes", "/no": b"deny"}))
    assert granted == ["/ok"]
