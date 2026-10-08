"""audit.only-the-action-surface-reaches-capabilities, CLI half (#4847).

The MCP half is `fichero-server/tests/unit/api/test_mcp_tools_write_through_registry.py`.
The CLI changes a library only over HTTP, through the engine's routes and the action
layer behind them. Never in-process. This scan, parsed not grepped, reads every
`fichero_server` import in `fichero-cli/src` and allows only:

- response and model TYPES (CamelCase names) from `fichero_server.api.routes.*` and
  `fichero_server.models*`, which are data shapes the client decodes into;
- importer entry points that post to the engine (`*_via_http`) and their connection
  helpers;
- the few modules in ALLOWED_MODULES, each with the reason it cannot write a library.

It also fails on any `db.save(` / `db.delete(` call and any import of the database,
the action registry or a route FUNCTION. A synthetic case proves the scan still
catches a real bypass, so a green run means nothing bypasses, not a blind scan.
"""

from __future__ import annotations

import ast
from pathlib import Path

CLI_SRC = Path(__file__).resolve().parents[1] / "src"

#: {module: reason} -- grow only with a reason this module cannot write a library.
ALLOWED_MODULES: dict[str, str] = {
    "fichero_server.security.bind_host": "transport: which host the spawned engine binds",
    "fichero_server.security.remote_access_tls": "transport: TLS settings for the spawned engine",
    "fichero_server.knowledge._common": "formatting: renders a claim row the client already fetched",
    "fichero_server.importers.legacy_10_archive": (
        "scans an archive and writes a local manifest file; the import itself is "
        "POSTed to /api/ingest"
    ),
    "fichero_server.workflows.library_sync": (
        "pure manifest diffing for a files-only clone; the source is read over HTTP"
    ),
    "fichero_server.workflows.library_sync_io": (
        "hashes and lands files in the destination package folder; writes no database"
    ),
    "fichero_server.workflows.provider_preview": (
        "resolves which provider a workflow would use; makes no writes and no model calls"
    ),
}

#: Names an importer module may give the CLI besides its `*_via_http` entry point.
IMPORTER_HELPERS = frozenset({"DEFAULT_API_BASE", "DEFAULT_TOKEN_FILE", "resolve_http_token"})


def _is_type_name(name: str) -> bool:
    return name[:1].isupper() and not name.isupper()


def findings_for(source: str, filename: str = "<src>") -> list[str]:
    out: list[str] = []
    tree = ast.parse(source, filename=filename)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("fichero_server") and alias.name not in ALLOWED_MODULES:
                    out.append(f"{filename}:{node.lineno} import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("fichero_server"):
            module = node.module or ""
            if module in ALLOWED_MODULES:
                continue
            # `from pkg import submodule` names the submodule itself.
            names = [
                alias.name for alias in node.names if f"{module}.{alias.name}" not in ALLOWED_MODULES
            ]
            if module.startswith(("fichero_server.api.routes", "fichero_server.models")):
                bad = [n for n in names if not _is_type_name(n)]
            elif module.startswith("fichero_server.importers"):
                bad = [n for n in names if not n.endswith("_via_http") and n not in IMPORTER_HELPERS]
            else:
                bad = names
            for name in bad:
                out.append(f"{filename}:{node.lineno} from {module} import {name}")
        elif isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr in ("save", "delete")
                and isinstance(func.value, ast.Name)
                and func.value.id == "db"
            ):
                out.append(f"{filename}:{node.lineno} db.{func.attr}(")
    return out


def test_the_cli_reaches_no_capability_in_process():
    files = sorted(CLI_SRC.rglob("*.py"))
    assert len(files) >= 5, "scan found too few files to mean anything"
    found: list[str] = []
    for path in files:
        found += findings_for(path.read_text(encoding="utf-8"), str(path.relative_to(CLI_SRC)))
    assert not found, "CLI reaches a capability outside the engine's HTTP surface:\n" + "\n".join(found)


def test_the_scan_catches_a_real_bypass():
    bypasses = [
        "from fichero_server.actions.registry import registry",
        "from fichero_server.db import Database",
        "from fichero_server.api.routes.entity.entities import delete_entity_impl",
        "from fichero_server.models import Document\ndb.save(Document(name='x'))",
        "from fichero_server.importers.slipbox_import import import_slipbox",
        "import fichero_server.db",
    ]
    for source in bypasses:
        assert findings_for(source), source


def test_the_scan_allows_types_and_http_importers():
    allowed = (
        "from fichero_server.models import Document, KnownLibrary\n"
        "from fichero_server.api.routes.search import SearchResponse\n"
        "from fichero_server.importers.iiif_import import import_iiif_via_http, DEFAULT_API_BASE\n"
    )
    assert findings_for(allowed) == []
