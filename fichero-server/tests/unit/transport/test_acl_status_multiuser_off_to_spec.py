"""library-sharing: sharing.acl-status-when-multiuser-off (#3335).

With Multi-user off the ACL status is an explicit, successful "multiuser_enabled: false" answer
(never an error), so the app can say "not enforcing per-library access" instead of a red
"Server error" that sends diagnosis down the accounts path.
"""

from __future__ import annotations

from types import SimpleNamespace

from fichero_server.api.routes.auth.authz import get_library_authz_snapshot


def test_multiuser_off_answers_with_an_explicit_disabled_state(db, app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")
    request = SimpleNamespace(state=SimpleNamespace(user=None))
    snap = get_library_authz_snapshot(request, x_fichero_library_path="/tmp/lib-3335", target_id=None)
    assert snap.multiuser_enabled is False
    assert snap.roles == []
    assert snap.can_manage_roles is False
