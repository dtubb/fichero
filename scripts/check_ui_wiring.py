#!/usr/bin/env python3
"""Programmatic UI-wiring coverage gate.

Asserts that every backend endpoint in openapi.json is actually referenced
(by its URL path) somewhere in the SwiftUI app — i.e. it has a call site and
isn't orphaned backend. Endpoints that are intentionally not-yet-wired live in
an allowlist (with a reason), which doubles as the frontend wiring backlog.

This is deterministic and token-free — the same philosophy as the OpenAPI
drift check. It catches two failure modes:
  1. A backend endpoint exists but nothing in the app calls it (orphaned).
  2. A NEW endpoint is added without either wiring it OR allowlisting it.

The app calls endpoints by raw URL path (Services/*.swift build URLRequests),
so we match each openapi path — with {params} turned into wildcards — against
the app Swift source.

Usage:
    python scripts/check_ui_wiring.py              # report + exit 1 if drift
    python scripts/check_ui_wiring.py --write-allowlist   # seed/refresh allowlist baseline
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OPENAPI = ROOT / "fichero-engine" / "tests" / "contracts" / "openapi.json"
CONTRACTS = ROOT / "fichero-engine" / "tests" / "contracts"
MATRIX = CONTRACTS / "coverage_matrix.json"

# Each consuming surface: the HAND-WRITTEN layer that should call endpoints, the
# file glob, dirs to exclude (the GENERATED clients — their method names are
# always present by codegen, so they are NOT the signal), and its allowlist.
SURFACES = {
    "swiftui": {
        "dir": ROOT / "fichero" / "fichero",          # the SwiftUI app
        "glob": "*.swift",
        "exclude": ("fichero-api-client",),            # generated Swift client
        "allowlist": CONTRACTS / "ui_wiring_allowlist_swiftui.json",
    },
    "cli": {
        "dir": ROOT / "fichero-engine" / "src" / "fichero" / "cli",
        "glob": "*.py",
        "exclude": ("generated", "__pycache__"),       # generated CLI client
        "allowlist": CONTRACTS / "ui_wiring_allowlist_cli.json",
    },
}


def surface_source(surface: dict) -> str:
    """Hand-written source for a surface, excluding generated client dirs."""
    blob = []
    for f in surface["dir"].rglob(surface["glob"]):
        if any(ex in f.parts for ex in surface["exclude"]):
            continue
        try:
            blob.append(f.read_text(errors="ignore"))
        except OSError:
            pass
    return "\n".join(blob)


def path_regex(path: str) -> re.Pattern:
    """openapi path -> regex that matches the raw URL in Swift source.

    `/api/kg/entities/{entity_id}/bio` -> /api/kg/entities/<...>/bio
    where <...> is a Swift interpolation or a literal id segment.
    """
    parts = re.split(r"\{[^}]+\}", path)
    escaped = r"[^/\"\s]+".join(re.escape(p) for p in parts)
    return re.compile(escaped)


def _snake_to_lower_camel(value: str) -> str:
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", value) if p]
    if not parts:
        return value
    return parts[0].lower() + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def _operation_tokens(operation_id: str, path: str | None = None) -> set[str]:
    """Potential handwritten method-name tokens for an OpenAPI operation.

    - raw operationId from openapi
    - normalized snake_case form
    - lowerCamel form (Swift generated client methods)
    """
    op = operation_id.strip()
    snake = re.sub(r"[^A-Za-z0-9]+", "_", op).strip("_").lower()
    tokens = {op, snake, _snake_to_lower_camel(snake)}

    if path and "_api_" in snake:
        prefix, route_tail = snake.split("_api_", 1)
        method = route_tail.rsplit("_", 1)[-1]
        path_snake = re.sub(r"[^A-Za-z0-9]+", "_", path).strip("_").lower()
        stable = f"{prefix}_{path_snake}_{method}"
        tokens.update({stable, _snake_to_lower_camel(stable)})

    return tokens


def endpoint_specs(openapi_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten OpenAPI paths into path+operation specs.

    Returns one dict per path:
      {"path": "/api/...", "operations": [{"method":"get","operationId":"..."}, ...]}
    """
    out: list[dict[str, Any]] = []
    for path, methods in sorted((openapi_data.get("paths") or {}).items()):
        ops: list[dict[str, str]] = []
        for method, meta in (methods or {}).items():
            if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                continue
            if not isinstance(meta, dict):
                continue
            op_id = str(meta.get("operationId") or "").strip()
            if not op_id:
                continue
            ops.append({"method": method.lower(), "operationId": op_id})
        out.append({"path": path, "operations": ops})
    return out


def _is_path_wired(path: str, operations: list[dict[str, str]], src: str) -> bool:
    """A path is wired if raw URL is referenced OR a generated-client operation token is used."""
    if path_regex(path).search(src):
        return True

    for op in operations:
        op_id = op.get("operationId") or ""
        for token in _operation_tokens(op_id, path):
            if not token:
                continue
            if re.search(rf"\b{re.escape(token)}\b", src):
                return True
    return False


def endpoint_paths(openapi_data: dict[str, Any]) -> list[str]:
    return [spec["path"] for spec in endpoint_specs(openapi_data)]


def unwired(surface: dict, openapi_data: dict[str, Any]) -> list[str]:
    src = surface_source(surface)
    miss: list[str] = []
    for spec in endpoint_specs(openapi_data):
        if not _is_path_wired(spec["path"], spec["operations"], src):
            miss.append(spec["path"])
    return miss


def _domain_for_path(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "api":
        return parts[1]
    return parts[0] if parts else path


def coverage_matrix(openapi_data: dict[str, Any]) -> dict[str, Any]:
    specs = endpoint_specs(openapi_data)
    misses = {name: set(unwired(surface, openapi_data)) for name, surface in SURFACES.items()}
    allowlists = {
        name: set(load_allowlist(surface, name).get("paths", {}).keys())
        for name, surface in SURFACES.items()
    }
    rows: list[dict[str, Any]] = []
    for domain in sorted({_domain_for_path(spec["path"]) for spec in specs}):
        domain_paths = [spec["path"] for spec in specs if _domain_for_path(spec["path"]) == domain]
        row: dict[str, Any] = {"domain": domain, "total": len(domain_paths)}
        for name in SURFACES:
            miss = sum(path in misses[name] for path in domain_paths)
            allow = sum(path in allowlists[name] for path in domain_paths)
            wired = len(domain_paths) - miss
            gap_key = "unwired" if name == "swiftui" else "untested"
            row[f"{name}_wired"] = wired
            row[f"{name}_{gap_key}"] = miss
            row[f"{name}_allowlisted"] = allow
            row[f"{name}_coverage"] = round(wired / len(domain_paths), 4) if domain_paths else 1.0
        rows.append(row)
    return {
        "_doc": (
            "Per-domain endpoint wiring/test-harness coverage generated by "
            "scripts/check_ui_wiring.py --matrix. Ratchet file: unwired/untested "
            "counts per domain may only go down."
        ),
        "rows": rows,
    }


def write_matrix(openapi_data: dict[str, Any]) -> None:
    MATRIX.write_text(json.dumps(coverage_matrix(openapi_data), indent=2) + "\n")


def load_allowlist(surface: dict, name: str) -> dict:
    al = surface["allowlist"]
    if al.exists():
        return json.loads(al.read_text())
    return {"_doc": f"Backend endpoints intentionally not (yet) wired into the {name} surface. "
                    "Each key is an openapi path; value is the reason. This file IS the "
                    f"{name} wiring backlog — drop an entry once it's called. CI-enforced.",
            "paths": {}}


def check_surface(name: str, surface: dict, write: bool) -> int:
    openapi_data = json.loads(OPENAPI.read_text())
    miss = unwired(surface, openapi_data)
    allow = load_allowlist(surface, name)
    allowed = set(allow.get("paths", {}).keys())

    if write:
        allow["paths"] = {p: allow.get("paths", {}).get(p, "baseline: not yet wired") for p in miss}
        surface["allowlist"].write_text(json.dumps(allow, indent=2) + "\n")
        print(f"[{name}] wrote allowlist baseline: {len(miss)} unwired endpoints")
        return 0

    drift = [p for p in miss if p not in allowed]
    stale = [p for p in allowed if p not in set(miss)]
    total = len(endpoint_paths(openapi_data))
    wired = total - len(miss)
    print(f"[{name}] {wired}/{total} endpoints wired, {len(miss)} unwired ({len(allowed)} allowlisted).")
    if stale:
        print(f"  ✓ {len(stale)} allowlisted endpoints now CALLED — drop from allowlist: {stale[:8]}")
    if drift:
        print(f"  ✗ {len(drift)} endpoint(s) NOT called and NOT allowlisted:")
        for p in drift:
            print(f"      {p}")
        return 1
    return 0


def main() -> int:
    write = "--write-allowlist" in sys.argv
    emit_matrix = "--matrix" in sys.argv
    openapi_data = json.loads(OPENAPI.read_text())
    if emit_matrix:
        write_matrix(openapi_data)
        print(f"wrote {MATRIX.relative_to(ROOT)}")
    rc = 0
    for name, surface in SURFACES.items():
        rc |= check_surface(name, surface, write)
    if not write and rc == 0:
        print("✓ Every backend endpoint is called from each surface, or explicitly allowlisted.")
    elif not write and rc:
        print("\nFix: call the endpoint from that surface, or add it to the surface's "
              "allowlist with a reason (the allowlist IS the wiring backlog).")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
