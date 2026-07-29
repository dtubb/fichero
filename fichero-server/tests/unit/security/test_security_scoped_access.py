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

from fichero_server.security import security_scoped_access as ssa


@pytest.fixture(autouse=True)
def _clear_process_grant_state():
    # BOTH module-level structures, or tests contaminate each other: a path granted
    # by one test would satisfy grant_access()'s idempotency short-circuit in the
    # next, and the suite would pass in order and fail in isolation.
    ssa._ACTIVE_URLS.clear()
    ssa._GRANTED.clear()
    yield
    ssa._ACTIVE_URLS.clear()
    ssa._GRANTED.clear()


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


# --- runtime handoff: grant_access(), the endpoint's engine half (#3773) ---
#
# The spawn-time env var cannot cover a library the user picks while the engine is
# already running. These cover the path that can: one bookmark, resolved live.


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def test_grant_access_resolves_and_grants(monkeypatch):
    foundation = FakeFoundation()
    monkeypatch.setattr(ssa, "_load_foundation", lambda: foundation)

    assert ssa.grant_access("/Users/d/Documents/L.fichero", _b64(b"BOOKMARK")) is True
    assert "/Users/d/Documents/L.fichero" in ssa.granted_paths()
    # The bookmark actually reached Foundation, with the security-scope option.
    assert foundation.calls[0][0] == b"BOOKMARK"
    assert foundation.calls[0][1] == foundation.NSURLBookmarkResolutionWithSecurityScope


def test_grant_access_is_idempotent_and_does_not_re_resolve(monkeypatch):
    """Re-posting a held path must NOT resolve a second NSURL.

    A second startAccessingSecurityScopedResource() on a fresh URL for the same path
    is a redundant grant nothing ever balances. The app legitimately re-sends (retry,
    reopen), so this has to be free.
    """
    foundation = FakeFoundation()
    monkeypatch.setattr(ssa, "_load_foundation", lambda: foundation)

    assert ssa.grant_access("/lib", _b64(b"B")) is True
    assert ssa.grant_access("/lib", _b64(b"B")) is True  # again

    assert len(foundation.calls) == 1, "the second grant must short-circuit, not re-resolve"
    assert len(ssa._ACTIVE_URLS) == 1, "no redundant URL may be retained"


def test_grant_access_raises_when_access_is_refused(monkeypatch):
    """A refusal is an ERROR, not a False the caller might ignore.

    The app is about to open this library; a grant that quietly did nothing would
    resurface as an inscrutable DuckDB permission error instead of a clear message.
    """
    foundation = FakeFoundation(url=FakeURL(granted=False))
    monkeypatch.setattr(ssa, "_load_foundation", lambda: foundation)

    with pytest.raises(ssa.BookmarkGrantError):
        ssa.grant_access("/lib", _b64(b"B"))
    assert "/lib" not in ssa.granted_paths(), "a refused path must never be recorded as granted"


def test_grant_access_raises_on_resolution_error(monkeypatch):
    monkeypatch.setattr(ssa, "_load_foundation", lambda: FakeFoundation(url=None, error="boom"))
    with pytest.raises(ssa.BookmarkGrantError):
        ssa.grant_access("/lib", _b64(b"B"))
    assert "/lib" not in ssa.granted_paths()


def test_grant_access_rejects_malformed_bookmark(monkeypatch):
    monkeypatch.setattr(ssa, "_load_foundation", lambda: FakeFoundation())
    with pytest.raises(ssa.BookmarkGrantError, match="base64"):
        ssa.grant_access("/lib", "!!!not base64!!!")


def test_grant_access_rejects_empty_bookmark_and_empty_path(monkeypatch):
    monkeypatch.setattr(ssa, "_load_foundation", lambda: FakeFoundation())
    with pytest.raises(ssa.BookmarkGrantError):
        ssa.grant_access("/lib", "")          # decodes to b"" — nothing to resolve
    with pytest.raises(ssa.BookmarkGrantError):
        ssa.grant_access("", _b64(b"B"))      # no path to grant


def test_grant_access_raises_when_pyobjc_is_missing(monkeypatch):
    """Unlike the spawn path, this one RAISES rather than fail-soft.

    activate_library_bookmarks() must never stop the engine booting, so it logs and
    returns []. But a runtime grant is a direct request from the app about a specific
    library — answering "fine" when PyObjC is absent would be a lie.
    """
    monkeypatch.setattr(ssa, "_load_foundation", lambda: None)
    with pytest.raises(ssa.BookmarkGrantError, match="PyObjC"):
        ssa.grant_access("/lib", _b64(b"B"))


def test_granted_paths_snapshot_cannot_mutate_engine_state(monkeypatch):
    monkeypatch.setattr(ssa, "_load_foundation", lambda: FakeFoundation())
    ssa.grant_access("/lib", _b64(b"B"))
    snapshot = ssa.granted_paths()
    assert isinstance(snapshot, frozenset)
    assert snapshot == {"/lib"}


def test_spawn_and_runtime_grants_share_one_registry(monkeypatch):
    """The two entry points are two doors into the same room.

    A library granted at spawn must be seen as already-held by a later runtime post,
    or reopening the app's first library would resolve a redundant second URL.
    """
    foundation = FakeFoundation()
    monkeypatch.setattr(ssa, "_load_foundation", lambda: foundation)

    ssa.activate_library_bookmarks(_payload({"/lib": b"B"}))
    assert "/lib" in ssa.granted_paths()

    assert ssa.grant_access("/lib", _b64(b"B")) is True
    assert len(foundation.calls) == 1, "the spawn-time grant must satisfy the runtime one"
