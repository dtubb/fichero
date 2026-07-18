#!/usr/bin/env python3
"""Endpoint usage matrix guardrail (#1920).

Reads the committed OpenAPI schema, enumerates every operation, and checks
whether each endpoint is referenced by the Swift app and by the Python CLI.

Usage:
    scripts/check_endpoint_usage.py
    scripts/check_endpoint_usage.py --list
    scripts/check_endpoint_usage.py --json
    scripts/check_endpoint_usage.py --help
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

OPENAPI_CANDIDATES = (
    ROOT / "fichero-engine" / "src" / "fichero" / "api" / "openapi.json",
    ROOT / "fichero" / "fichero-api-client" / "Sources" / "FicheroAPIClient" / "openapi.json",
    ROOT / "fichero-engine" / "tests" / "contracts" / "openapi.json",
    ROOT / "fichero" / "fichero-api-client" / "Sources" / "openapi.json",
)
SWIFT_DIR = ROOT / "fichero" / "fichero"
CLI_DIR = ROOT / "fichero-engine" / "src" / "fichero" / "cli"
HTTP_METHODS = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}

# Current baseline. The script exits 0 while every unused/asymmetric endpoint is
# listed here and exits 1 when a new gap appears.
KNOWN_GAPS: dict[str, str] = {
    'GET /api/entities/digest': "CLI/engine-only: the app renders the entity digest via the WebKit document view, not this endpoint; the dead Swift entityDigest() wrapper was removed in #3765.",
    'DELETE /api/chains/executions/{execution_id}': "#1920 baseline - cli-only",
    'DELETE /api/folders/{entity_type}/folders': "#1920 baseline - cli-only",
    'DELETE /api/library/links/{link_id}': "#1920 baseline - cli-only",
    'GET /api/activity/stream': "#2633 app-only SSE refresh stream; CLI remains request/response",
    'GET /api/auth/sessions': "#1920 baseline - cli-only",
    'GET /api/folders/{entity_type}/folders': "#1920 baseline - cli-only",
    'GET /api/folders/{folder_id}/views': "#1920 baseline - cli-only",
    'GET /api/kg/export/rdf': "#1920 baseline - cli-only",
    'GET /api/library-items/{item_id}/links': "#1920 baseline - cli-only",
    'GET /api/library/links': "#1920 baseline - cli-only",
    'GET /api/library/links/{link_id}': "#1920 baseline - cli-only",
    'GET /api/local-inference/capabilities': "#1920 baseline - cli-only",
    'GET /api/providers/apple-intelligence/probe': "#1920 baseline - cli-only",
    'GET /api/registry/unicode-collisions': "#1920 baseline - cli-only",
    'GET /api/storage/debug/{doc_id}': "endpoint ownership audit tracked in #3759",
    'GET /api/workflow-execution/stream/{thread_id}': "endpoint ownership audit tracked in #3759",
    'GET /api/workflow-execution/threads/{thread_id}/diagram.svg': "#1920 baseline - cli-only",
    'PATCH /api/library/links/{link_id}': "#1920 baseline - cli-only",
    'POST /api/auth/sessions/{session_id}/revoke': "#1920 baseline - cli-only",
    'POST /api/bibliography/import/persist': "#1920 baseline - cli-only",
    'POST /api/canvas/folders/{folder_id}/arrange': "#1920 baseline - cli-only",
    'POST /api/folders/{entity_type}/folders': "#1920 baseline - cli-only",
    'POST /api/library/links': "#1920 baseline - cli-only",
    'POST /api/pair/enroll': "#3789 engine/CLI device enrollment; iOS automatic-enrollment store wiring is deferred",
    'POST /api/registry/unicode-collisions/merge': "#1920 baseline - cli-only",
    'PUT /api/folders/{entity_type}/folders': "#1920 baseline - cli-only",
    'PUT /api/folders/{entity_type}/move': "#1920 baseline - cli-only",
    'PUT /api/schedules/{schedule_id}': "#1920 baseline - cli-only",
    'PUT /api/triggers/{trigger_id}': "#1920 baseline - cli-only",
    'POST /api/agent-memory': "#2152 agent memory - cli-only (SwiftUI deferred)",
    'GET /api/agent-memory': "#2152 agent memory - cli-only (SwiftUI deferred)",
    'GET /api/agent-memory/{note_id}': "#2152 agent memory - cli-only (SwiftUI deferred)",
    'PATCH /api/agent-memory/{note_id}': "#2152 agent memory - cli-only (SwiftUI deferred)",
    'DELETE /api/agent-memory/{note_id}': "#2152 agent memory - cli-only (SwiftUI deferred)",
    'POST /api/artifacts/': "#1943 - cli-only (Swift creates artifacts via ingest/workflow, not a direct call)",
    'PUT /api/actions/{action_id}': "#1920 baseline - cli-only",
    'GET /api/activity/entity-types': "#1920 baseline - cli-only",
    'GET /api/activity/feed': "#1920 baseline - cli-only",
    'GET /api/activity/metrics/summary': "#1920 baseline - cli-only",
    'GET /api/activity/top': "#1920 baseline - cli-only",
    'GET /api/activity/trends': "#1920 baseline - cli-only",
    'GET /api/actions/registry': "#1848 action layer - cli-only, store/UI deferred",
    'POST /api/agents/write': "#1920 baseline - cli-only",
    'POST /api/agents/write/approve': "#1920 baseline - cli-only",
    'GET /api/agents/write/audit': "#1920 baseline - cli-only",
    'GET /api/agents/write/audit/{record_id}': "#1920 baseline - cli-only",
    'POST /api/bibliography/document/{document_id}/attach': "#1920 baseline - cli-only",
    'GET /api/chains/presets/paleography': "#1920 baseline - cli-only",
    'POST /api/chains/presets/paleography': "#1920 baseline - cli-only",
    'DELETE /api/citations/graph/{citation_id}': "#1920 baseline - cli-only",
    'POST /api/claims/assign-time-period-from-metadata': "#1920 baseline - cli-only",
    'GET /api/claims/{claim_id}/links': "#1920 baseline - cli-only",
    'POST /api/documents/cleanup-orphans': "#1920 baseline - cli-only",
    'POST /api/documents/pdfs/backfill-pages': "#1920 baseline - cli-only",
    'GET /api/documents/trash': "#2075 backend; UI tracked in #2077",
    'DELETE /api/documents/{doc_id}/notes': "#1920 baseline - cli-only",
    'DELETE /api/documents/{doc_id}/purge': "#2075 backend; UI tracked in #2077",
    'DELETE /api/users/{user_id}': "#3859 engine/CLI user deletion; Swift UsersStore deletion surface is deferred",
    'GET /api/documents/{doc_id}/annotations.jsonld': "backend/CLI annotation export; Swift store wiring tracked as annotation export UI backlog",
    'GET /api/documents/{doc_id}/notes': "#1920 baseline - cli-only",
    'PUT /api/documents/{doc_id}/notes': "#1920 baseline - cli-only",
    'GET /api/documents/{doc_id}/page-ranges': "#1920 baseline - cli-only",
    'PUT /api/documents/{doc_id}/page-ranges': "#1920 baseline - cli-only",
    'GET /api/documents/{doc_id}/page-ranges/at/{page}': "#1920 baseline - cli-only",
    'GET /api/documents/{doc_id}/related': "#1920 baseline - cli-only",
    'GET /api/entities/{entity_id}/export': "engine-side complete; Swift drag-export tracked in #3703",
    'POST /api/export/excel': "#1920 baseline - cli-only",
    'POST /api/export/markdown-folder': "#1920 baseline - cli-only",
    'POST /api/export/word': "#1920 baseline - cli-only",
    'GET /api/iiif/iiif/image/{document_id}': "#1920 baseline - cli-only",
    'GET /api/iiif/iiif/manifest/{document_id}': "#1920 baseline - cli-only",
    'GET /api/iiif/iiif/{identifier}/info.json': "#1920 baseline - cli-only",
    'GET /api/iiif/iiif/{identifier}/{region}/{size}/{rotation}/{quality}.{format}': "#1920 baseline - cli-only",
    'POST /api/ingest/xlsx': "#1920 baseline - cli-only",
    'POST /api/images/batch-apply': "reversible image editing with undo; Swift wiring tracked in #3756",
    'POST /api/images/batch-apply/{batch_id}/undo': "reversible image editing with undo; Swift wiring tracked in #3756",
    'POST /api/images/crops/batch': "reversible image editing with undo; Swift wiring tracked in #3756",
    'POST /api/images/{document_id}/crop': "reversible image editing with undo; Swift wiring tracked in #3756",
    'POST /api/images/{document_id}/split': "reversible image editing with undo; Swift wiring tracked in #3756",
    'POST /api/images/{document_id}/uncrop': "reversible image editing with undo; Swift wiring tracked in #3756",
    'POST /api/images/{document_id}/unsplit': "reversible image editing with undo; Swift wiring tracked in #3756",
    'GET /api/model-comparison/language-fit': "#1820 backend LOOVE language-fit API; Settings/model-picker UI wiring tracked by #2116",
    'POST /api/model-comparison/compare-workflow': "#2195 baseline - cli-only model bake-off; SwiftUI comparison UI is #1753/#1739",
    'POST /api/model-comparison/recommend-models': "#2204 backend model recommendation API; Settings/model-picker UI wiring tracked by #2116",
    'GET /api/integrations/available': "#1920 baseline - cli-only",
    'GET /api/integrations/tinderbox/notes/{external_id}/attributes': "#1920 baseline - cli-only",
    'PUT /api/integrations/tinderbox/notes/{external_id}/attributes': "#1920 baseline - cli-only",
    'GET /api/integrations/{app_name}': "#1920 baseline - cli-only",
    'DELETE /api/hermeneutics/frameworks/{framework_id}': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'GET /api/hermeneutics/circle-state': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'GET /api/hermeneutics/circle-state/{state_id}': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'GET /api/hermeneutics/frameworks/{framework_id}': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'GET /api/hermeneutics/interpretations/{interpretation_id}': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'GET /api/hermeneutics/patterns': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'GET /api/hermeneutics/patterns/{pattern_id}': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'GET /api/hermeneutics/taxonomy/methods': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'PATCH /api/hermeneutics/frameworks/{framework_id}': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'PATCH /api/hermeneutics/patterns/{pattern_id}': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'POST /api/hermeneutics/circle-state': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'POST /api/hermeneutics/circle-state/{state_id}/backtrack': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'POST /api/hermeneutics/circle-state/{state_id}/navigate': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'POST /api/hermeneutics/patterns': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'POST /api/hermeneutics/patterns/{pattern_id}/claims/{claim_id}': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'POST /api/hermeneutics/suggestions': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'DELETE /api/kg/interpretations/frameworks/{framework_id}': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'GET /api/kg/interpretations/circle-state': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'GET /api/kg/interpretations/circle-state/{state_id}': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'GET /api/kg/interpretations/frameworks': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'GET /api/kg/interpretations/frameworks/{framework_id}': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'GET /api/kg/interpretations/interpretations': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'GET /api/kg/interpretations/interpretations/{interpretation_id}': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'GET /api/kg/interpretations/patterns': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'GET /api/kg/interpretations/patterns/{pattern_id}': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'GET /api/kg/interpretations/taxonomy/methods': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'PATCH /api/kg/interpretations/frameworks/{framework_id}': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'PATCH /api/kg/interpretations/interpretations/{interpretation_id}': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'PATCH /api/kg/interpretations/patterns/{pattern_id}': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'POST /api/kg/interpretations/circle-state': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'POST /api/kg/interpretations/circle-state/{state_id}/backtrack': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'POST /api/kg/interpretations/circle-state/{state_id}/navigate': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'POST /api/kg/interpretations/frameworks': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'POST /api/kg/interpretations/interpretations': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'POST /api/kg/interpretations/patterns': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'POST /api/kg/interpretations/patterns/{pattern_id}/claims/{claim_id}': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'POST /api/kg/interpretations/suggestions': "#3299 hermeneutics engine/CLI surface; SwiftUI deferred",
    'GET /api/kg/review/summary': "#1920 baseline - cli-only",
    'POST /api/local-inference/profiles/validate': "#1814 backend local-MLX control surface; Mac/SwiftUI wiring deferred",
    'POST /api/local-inference/profiles/{profile_id}/health': "#1814 backend local-MLX control surface; Mac/SwiftUI wiring deferred",
    'GET /api/settings/model-profiles': "#2058 backend model-profile API; Settings UI/store wiring deferred",
    'POST /api/settings/model-profiles': "#2058 backend model-profile API; Settings UI/store wiring deferred",
    'GET /api/settings/model-profiles/{profile_id}': "#2058 backend model-profile API; Settings UI/store wiring deferred",
    'PUT /api/settings/model-profiles/{profile_id}': "#2058 backend model-profile API; Settings UI/store wiring deferred",
    'DELETE /api/settings/model-profiles/{profile_id}': "#2058 backend model-profile API; Settings UI/store wiring deferred",
    'GET /api/mcp/tools/knowledge/claims': "#1920 baseline - cli-only",
    'POST /api/mcp/tools/knowledge/claims/create': "#1920 baseline - cli-only",
    'DELETE /api/mcp/tools/knowledge/claims/{claim_id}': "#1920 baseline - cli-only",
    'GET /api/mcp/tools/knowledge/claims/{claim_id}': "#1920 baseline - cli-only",
    'GET /api/mcp/tools/knowledge/entities': "#1920 baseline - cli-only",
    'POST /api/mcp/tools/knowledge/entities/upsert': "#1920 baseline - cli-only",
    'DELETE /api/mcp/tools/knowledge/entities/{entity_id}': "#1920 baseline - cli-only",
    'GET /api/mcp/tools/knowledge/entities/{entity_id}': "#1920 baseline - cli-only",
    'GET /api/migrations/migrations': "#1920 baseline - cli-only",
    'GET /api/migrations/migrations/integrity-check': "#1920 baseline - cli-only",
    'POST /api/migrations/migrations/rollback': "#1920 baseline - cli-only",
    'POST /api/migrations/migrations/run': "#1920 baseline - cli-only",
    'GET /api/migrations/migrations/status/{run_id}': "#1920 baseline - cli-only",
    'POST /api/migrations/migrations/validate': "#1920 baseline - cli-only",
    'POST /api/storage/regenerate-missing': "#2297 sweep baseline - cli-only",
    'POST /api/model-comparison/compare-node/apply': "#1920 baseline - cli-only",
    'GET /api/notes/{note_id}': "#1920 baseline - cli-only",
    'POST /api/notes/{note_id}/links': "#1920 baseline - cli-only",
    'DELETE /api/notes/{note_id}/links/{link_id}': "#1920 baseline - cli-only",
    'GET /api/policies/orchestration': "#1920 baseline - cli-only",
    'POST /api/policies/orchestration': "#1920 baseline - cli-only",
    'POST /api/policies/orchestration/evaluate': "#1920 baseline - cli-only",
    'DELETE /api/policies/orchestration/{rule_id}': "#1920 baseline - cli-only",
    'GET /api/policies/orchestration/{rule_id}': "#1920 baseline - cli-only",
    'PATCH /api/policies/orchestration/{rule_id}': "#1920 baseline - cli-only",
    'GET /api/projects': "#1920 baseline - cli-only",
    'POST /api/projects': "#1920 baseline - cli-only",
    'GET /api/projects/membership/{target_id}': "#1920 baseline - cli-only",
    'DELETE /api/projects/{project_id}': "#1920 baseline - cli-only",
    'GET /api/projects/{project_id}': "#1920 baseline - cli-only",
    'PATCH /api/projects/{project_id}': "#1920 baseline - cli-only",
    'POST /api/projects/{project_id}/include': "#1920 baseline - cli-only",
    'DELETE /api/projects/{project_id}/include/{inclusion_id}': "#1920 baseline - cli-only",
    'GET /api/projects/{project_id}/items': "#1920 baseline - cli-only",
    'POST /api/registry/update-access': "#1920 baseline - cli-only",
    'GET /api/registry/open': "endpoint ownership audit tracked in #3759",
    'GET /api/research/projects/{project_id}': "#1920 baseline - cli-only",
    'POST /api/research/tools/browser-navigate': "#1920 baseline - cli-only",
    'POST /api/research/tools/document-fetch': "#1920 baseline - cli-only",
    'POST /api/search/explain': "#1920 baseline - cli-only",
    'GET /api/search/explain/{query}': "#1920 baseline - cli-only",
    'GET /api/search/metrics': "#1920 baseline - cli-only",
    'GET /api/search/modes': "#1920 baseline - cli-only",
    'GET /api/search/views': "#1920 baseline - cli-only",
    'GET /api/search/views/grid': "#1920 baseline - cli-only",
    'GET /api/search/views/map': "#1920 baseline - cli-only",
    'GET /api/search/views/table': "#1920 baseline - cli-only",
    'POST /api/settings/ai-defaults/repair': "#1920 baseline - cli-only",
    'GET /api/storage/snapshots/{snapshot_id}': "#1920 baseline - cli-only",
    'PATCH /api/storage/snapshots/{snapshot_id}/pin': "#1920 baseline - cli-only",
    'GET /api/tasks': "#1920 baseline - cli-only",
    'GET /api/tasks/health': "doubled tasks-router prefix bug tracked in #3755",
    'POST /api/tasks/kg-metrics': "#1920 baseline - cli-only",
    'GET /api/tasks/kg-metrics/{task_id}/data': "#1920 baseline - cli-only",
    'POST /api/tasks/metrics': "#1920 baseline - cli-only",
    'GET /api/tasks/metrics/{task_id}/data': "#1920 baseline - cli-only",
    'POST /api/tasks/reindex': "#1920 baseline - cli-only",
    'GET /api/tasks/reindex/{task_id}/progress': "#1920 baseline - cli-only",
    'POST /api/tasks/vector-repair': "#1920 baseline - cli-only",
    'GET /api/tasks/vector-repair/{task_id}/progress': "#1920 baseline - cli-only",
    'DELETE /api/tasks/{task_id}': "#1920 baseline - cli-only",
    'GET /api/tasks/{task_id}': "#1920 baseline - cli-only",
    'POST /api/tasks/{task_id}/cancel': "#1920 baseline - cli-only",
    'GET /api/tasks/{task_id}/result': "#1920 baseline - cli-only",
    'DELETE /api/workflow-execution/cache': "#1920 baseline - cli-only",
    'GET /api/workflow-execution/cache/stats': "#1920 baseline - cli-only",
    'GET /api/workflow-execution/threads/{thread_id}/diagram.png': "#1920 baseline - cli-only",
    'DELETE /api/workflow-execution/workflows/{workflow_id}/cache': "#1920 baseline - cli-only",
    'GET /api/workflow-execution/workflows/{workflow_id}/cache/stats': "#1920 baseline - cli-only",
    'GET /api/workflow-execution/workflows/{workflow_id}/visualization': "#1920 baseline - cli-only",
    'GET /api/workflow-execution/workflows/{workflow_id}/visualization.png': "#1920 baseline - cli-only",
    'GET /api/workflows/modes': "#1920 baseline - cli-only",
    'POST /api/workflows/{workflow_id}/estimate-cost': "#1920 baseline - cli-only",
}


@dataclass(frozen=True)
class Endpoint:
    method: str
    path: str
    operation_id: str

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"


@dataclass(frozen=True)
class Row:
    endpoint: str
    operation_id: str
    used_by_swift: bool
    used_by_cli: bool
    status: str


def _read_tree_text(root: Path, suffixes: tuple[str, ...]) -> str:
    chunks: list[str] = []
    if not root.exists():
        return ""
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in suffixes:
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def _find_openapi() -> Path:
    for candidate in OPENAPI_CANDIDATES:
        if candidate.exists():
            return candidate
    searched = "\n  ".join(str(p.relative_to(ROOT)) for p in OPENAPI_CANDIDATES)
    raise FileNotFoundError(f"OpenAPI schema not found. Searched:\n  {searched}")


def _load_endpoints(openapi_path: Path) -> list[Endpoint]:
    spec = json.loads(openapi_path.read_text(encoding="utf-8"))
    endpoints: list[Endpoint] = []
    for path, path_item in sorted(spec.get("paths", {}).items()):
        if not isinstance(path_item, dict):
            continue
        for method, operation in sorted(path_item.items()):
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            operation_id = str(operation.get("operationId") or "")
            endpoints.append(Endpoint(method.upper(), path, operation_id))
    return endpoints


def _camel_from_operation_id(operation_id: str) -> str:
    parts = [part for part in operation_id.split("_") if part]
    if not parts:
        return ""
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _path_without_api(path: str) -> str:
    return path[4:] if path.startswith("/api/") else path


def _path_regex(path: str, *, swift: bool) -> re.Pattern[str]:
    """Match literal endpoint paths, including placeholder syntax in code."""
    placeholder = r"\\\([^)]+\)" if swift else r"\{[^}]+\}"
    pieces: list[str] = []
    cursor = 0
    for match in re.finditer(r"\{[^}]+\}", path):
        pieces.append(re.escape(path[cursor:match.start()]))
        pieces.append(placeholder)
        cursor = match.end()
    pieces.append(re.escape(path[cursor:]))
    return re.compile("".join(pieces))


def _swift_uses(endpoint: Endpoint, swift_text: str) -> bool:
    camel = _camel_from_operation_id(endpoint.operation_id)
    if camel and re.search(rf"\b{re.escape(camel)}\b", swift_text):
        return True
    if endpoint.operation_id and endpoint.operation_id in swift_text:
        return True
    path = _path_without_api(endpoint.path)
    if path in swift_text:
        return True
    return bool(_path_regex(path, swift=True).search(swift_text))


def _cli_uses(endpoint: Endpoint, cli_text: str) -> bool:
    if endpoint.operation_id and endpoint.operation_id in cli_text:
        return True
    if endpoint.path in cli_text:
        return True
    return bool(_path_regex(endpoint.path, swift=False).search(cli_text))


def build_matrix() -> tuple[Path, list[Row]]:
    openapi_path = _find_openapi()
    swift_text = _read_tree_text(SWIFT_DIR, (".swift",))
    cli_text = _read_tree_text(CLI_DIR, (".py",))
    rows: list[Row] = []
    for endpoint in _load_endpoints(openapi_path):
        swift = _swift_uses(endpoint, swift_text)
        cli = _cli_uses(endpoint, cli_text)
        if swift and cli:
            status = "both"
        elif swift:
            status = "swift-only"
        elif cli:
            status = "cli-only"
        else:
            status = "dead"
        rows.append(Row(endpoint.key, endpoint.operation_id, swift, cli, status))
    return openapi_path, rows


def counts(rows: list[Row]) -> dict[str, int]:
    return {
        "total": len(rows),
        "dead": sum(row.status == "dead" for row in rows),
        "swift_only": sum(row.status == "swift-only" for row in rows),
        "cli_only": sum(row.status == "cli-only" for row in rows),
        "both": sum(row.status == "both" for row in rows),
    }


def _print_matrix(rows: list[Row]) -> None:
    print("endpoint | used-by-swift? | used-by-cli? | status | operationId")
    print("-" * 96)
    for row in rows:
        print(
            f"{row.endpoint} | "
            f"{'yes' if row.used_by_swift else 'no'} | "
            f"{'yes' if row.used_by_cli else 'no'} | "
            f"{row.status} | {row.operation_id}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print the full endpoint matrix")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = parser.parse_args(argv)

    try:
        openapi_path, rows = build_matrix()
    except Exception as exc:
        print(f"Endpoint usage check failed: {exc}", file=sys.stderr)
        return 1

    summary = counts(rows)
    gaps = {row.endpoint: row.status for row in rows if row.status != "both"}
    new_gaps = sorted(set(gaps) - set(KNOWN_GAPS))
    stale_known = sorted(set(KNOWN_GAPS) - set(gaps))

    if args.json:
        payload: dict[str, Any] = {
            "openapi": openapi_path.relative_to(ROOT).as_posix(),
            "summary": summary,
            "new_gaps": new_gaps,
            "stale_known_gaps": stale_known,
            "matrix": [asdict(row) for row in rows],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Endpoint usage matrix: {openapi_path.relative_to(ROOT)}")
        print(
            "  total={total} both={both} dead={dead} swift-only={swift_only} "
            "cli-only={cli_only}".format(**summary)
        )
        if args.list:
            print()
            _print_matrix(rows)
        if stale_known:
            print(f"\n  {len(stale_known)} KNOWN_GAPS entries are now clean; remove them:")
            for endpoint in stale_known:
                print(f"      {endpoint}  ({KNOWN_GAPS[endpoint]})")
        if new_gaps:
            print(f"\n  {len(new_gaps)} new endpoint usage gap(s):")
            for endpoint in new_gaps:
                print(f"      {endpoint}  <-  {gaps[endpoint]}")
            print("\nFix: wire the endpoint through Swift and/or CLI, or add a tracked baseline entry.")
        elif not stale_known:
            print("\nOK: no new endpoint usage gaps.")

    return 1 if new_gaps else 0


if __name__ == "__main__":
    raise SystemExit(main())
