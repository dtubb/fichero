"""spec: code-organization — behaviour code-org.folders.python-no-shim-modules (P1).

A move is a hard cutover (AGENTS.md rule 0): a module under api/routes does not alias
itself to another with an alias into sys.modules.
"""

from pathlib import Path

from _scan_files import scan_rglob

import fichero_server.api.routes as routes_pkg

ROUTES = Path(routes_pkg.__file__).parent
ALIAS_MARK = "sys.modules[" + "__name__]"  # split, so this test does not trip the placement rule


def test_no_new_route_module_aliases_itself_in_sys_modules():
    offenders = {
        str(p.relative_to(ROUTES)) for p in scan_rglob(ROUTES, "*.py") if ALIAS_MARK in p.read_text(encoding="utf-8")
    }
    assert not offenders, sorted(offenders)
