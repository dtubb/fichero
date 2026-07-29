"""Incremental backend verification planning helpers.

This module keeps the "what should I run?" logic in Python so the shell gate
can stay thin. The first slice is backend-only: classify changed engine files
into targeted pytest files and decide when a full manager gate is required.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_GOD_NODE_PATHS = {
    "fichero-server/src/fichero_server/db.py": "database god-node changed",
    "fichero-server/src/fichero_server/api/main.py": "api main wiring changed",
    "fichero-server/src/fichero_server/actions/registry.py": "action registry changed",
    "fichero-server/src/fichero_server/actions/audit_chain.py": "audit chain changed",
}

_SECURITY_PATH_PREFIXES = (
    "fichero-server/src/fichero_server/api/auth",
    "fichero-server/src/fichero_server/api/routes/auth",
    "fichero-server/src/fichero_server/authz",
    "fichero-server/src/fichero_server/accounts",
)

_CONTRACT_PATH_PREFIXES = (
    "fichero-server/tests/contracts/",
    "fichero-server/tests/integration/",
)

_REPO_ROOT_MARKERS = ("fichero-server", ".git")

_EXTRA_TEST_TARGETS = {
    "fichero-server/src/fichero_server/api/routes/mcp_tools.py": (
        "fichero-server/tests/unit/test_mcp_knowledge_adapters.py",
    ),
}


@dataclass(frozen=True)
class VerificationPlan:
    pytest_targets: tuple[str, ...]
    requires_full_gate: bool
    reasons: tuple[str, ...] = ()
    unmatched_paths: tuple[str, ...] = ()


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if all((candidate / marker).exists() for marker in _REPO_ROOT_MARKERS):
            return candidate
    return start.resolve()


def _normalize(path: str) -> str:
    return path.strip().lstrip("./")


def _is_contract_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _CONTRACT_PATH_PREFIXES)


def _is_security_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _SECURITY_PATH_PREFIXES)


def _candidate_tests_for_source(repo_root: Path, normalized_path: str) -> set[str]:
    source_name = Path(normalized_path).stem
    tests_root = repo_root / "fichero-server" / "tests"
    patterns = {
        f"test_{source_name}.py",
        f"test_routes_{source_name}.py",
        f"test_*{source_name}*.py",
    }

    matches: set[str] = set()
    for pattern in patterns:
        for path in tests_root.rglob(pattern):
            if path.is_file():
                matches.add(path.relative_to(repo_root).as_posix())
    matches.update(_EXTRA_TEST_TARGETS.get(normalized_path, ()))
    return matches


def plan_backend_verification(
    changed_paths: Iterable[str],
    *,
    repo_root: Path | None = None,
) -> VerificationPlan:
    resolved_root = _find_repo_root(repo_root or Path.cwd())
    pytest_targets: set[str] = set()
    reasons: list[str] = []
    unmatched: list[str] = []

    for raw_path in changed_paths:
        path = _normalize(raw_path)
        if not path:
            continue

        if path in _GOD_NODE_PATHS:
            reasons.append(_GOD_NODE_PATHS[path])
        elif _is_contract_path(path):
            reasons.append("contract or integration surface changed")
        elif _is_security_path(path):
            reasons.append("security-sensitive backend path changed")

        if path.startswith("fichero-server/tests/") and path.endswith(".py"):
            pytest_targets.add(path)
            continue

        if path.startswith("fichero-server/src/") and path.endswith(".py"):
            matches = _candidate_tests_for_source(resolved_root, path)
            if matches:
                pytest_targets.update(matches)
            else:
                unmatched.append(path)
            continue

    return VerificationPlan(
        pytest_targets=tuple(sorted(pytest_targets)),
        requires_full_gate=bool(reasons),
        reasons=tuple(dict.fromkeys(reasons)),
        unmatched_paths=tuple(sorted(dict.fromkeys(unmatched))),
    )
