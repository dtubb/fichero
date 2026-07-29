#!/usr/bin/env python3
"""File GitHub issues for current fast-verification guardrail violations.

Default mode is dry-run. Use --apply to create issues.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

MILESTONES = {
    "swiftlint": "Mac Polish - Fonts, SF Symbols, No Emoji",
    "view-endpoint-access": "Observable Data Layer",
    "duplicate-paths": "Developer Experience",
    "endpoint-usage": "Developer Experience",
    "feature-flags": "Developer Experience",
    "native-controls": "Native SwiftUI Controls",
    "no-emoji-sf-symbols": "Mac Polish - Fonts, SF Symbols, No Emoji",
    "comment-hygiene": "Developer Experience",
    "ui-wiring": "Developer Experience",
    "version-date": "Developer Experience",
    "openapi-model-sync": "Developer Experience",
}


@dataclass(frozen=True)
class Violation:
    guardrail: str
    location: str
    rule: str
    detail: str

    @property
    def fingerprint(self) -> str:
        seed = f"{self.guardrail}|{self.location}|{self.rule}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    @property
    def milestone(self) -> str:
        return MILESTONES.get(self.guardrail, "Developer Experience")

    @property
    def title(self) -> str:
        return f"[verify:{self.guardrail}] {self.location} ({self.rule})"

    @property
    def body(self) -> str:
        return "\n".join(
            [
                f"<!-- verify-fp: {self.fingerprint} -->",
                "",
                "Fast verification found this current guardrail violation.",
                "",
                f"- Guardrail: `{self.guardrail}`",
                f"- Location: `{self.location}`",
                f"- Rule: `{self.rule}`",
                f"- Detail: {self.detail}",
            ]
        )


def _module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _key_parts(key: str) -> tuple[str, str]:
    parts = key.split(":")
    if len(parts) >= 3 and parts[-2].isdigit():
        return ":".join(parts[:-1]), parts[-1]
    if len(parts) >= 2 and parts[-1].isdigit():
        return key, "violation"
    return key, "violation"


def _scan_guardrail(module_name: str, script_name: str, guardrail: str, *, prefix: str = "") -> list[Violation]:
    module = _module(module_name, SCRIPTS / script_name)
    found = module.scan()
    violations: list[Violation] = []
    for key, detail in sorted(found.items()):
        location, rule = _key_parts(key)
        if prefix and not location.startswith(prefix):
            location = f"{prefix}{location}"
        if isinstance(detail, list):
            detail_text = "; ".join(str(item) for item in detail)
        else:
            detail_text = str(detail)
        violations.append(Violation(guardrail, location, rule, detail_text))
    return violations


def collect_view_endpoint_access() -> list[Violation]:
    module = _module("check_view_endpoint_access_report", SCRIPTS / "check_view_endpoint_access.py")
    violations: list[Violation] = []
    for rel, reasons in sorted(module.scan().items()):
        for reason in reasons:
            violations.append(
                Violation(
                    "view-endpoint-access",
                    f"fichero/fichero/Views/{rel}",
                    reason.split(" ", 1)[0],
                    reason,
                )
            )
    return violations


def collect_duplicate_paths() -> list[Violation]:
    module = _module("check_duplicate_paths_report", SCRIPTS / "check_duplicate_paths.py")
    violations: list[Violation] = []
    for concern, occurrences in sorted(module.find_violations().items()):
        detail = "; ".join(f"{occ.file}:{occ.line}::{occ.symbol}" for occ in occurrences)
        violations.append(Violation("duplicate-paths", concern, "duplicate-concern", detail))
    return violations


def collect_endpoint_usage() -> list[Violation]:
    module = _module("check_endpoint_usage_report", SCRIPTS / "check_endpoint_usage.py")
    _openapi_path, rows = module.build_matrix()
    violations: list[Violation] = []
    for row in rows:
        if row.status == "both":
            continue
        violations.append(
            Violation(
                "endpoint-usage",
                row.endpoint,
                row.status,
                f"operationId={row.operation_id}",
            )
        )
    return violations


def collect_ui_wiring() -> list[Violation]:
    module = _module("check_ui_wiring_report", SCRIPTS / "check_ui_wiring.py")
    openapi_data = json.loads(module.OPENAPI.read_text(encoding="utf-8"))
    violations: list[Violation] = []
    for name, surface in module.SURFACES.items():
        for path in module.unwired(surface, openapi_data):
            violations.append(Violation("ui-wiring", f"{name}:{path}", "unwired-endpoint", path))
    return violations


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


def collect_swiftlint() -> list[Violation]:
    if shutil.which("swiftlint") is None:
        return [Violation("swiftlint", "swiftlint", "tool-unavailable", "swiftlint is not installed")]
    result = _run(
        [
            "swiftlint",
            "lint",
            "--quiet",
            "--cache-path",
            ".swiftlint-cache",
            "--reporter",
            "json",
            "fichero/fichero/",
        ]
    )
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        detail = (result.stderr or result.stdout or "swiftlint failed").strip()
        return [Violation("swiftlint", "swiftlint", "unparseable-output", detail)]
    violations: list[Violation] = []
    for item in payload:
        file_path = str(item.get("file") or "")
        try:
            location = Path(file_path).resolve().relative_to(ROOT).as_posix()
        except ValueError:
            location = file_path
        line = item.get("line")
        if line:
            location = f"{location}:{line}"
        rule = str(item.get("rule_id") or item.get("type") or "swiftlint")
        detail = str(item.get("reason") or item.get("message") or rule)
        violations.append(Violation("swiftlint", location, rule, detail))
    return violations


def collect_version_date() -> list[Violation]:
    result = _run(["scripts/check_version_date.sh"])
    if result.returncode == 0:
        return []
    detail = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    return [Violation("version-date", "fichero version", "invalid-version-date", detail)]


def collect_openapi_model_sync() -> list[Violation]:
    python_bin = shutil.which("python3") or sys.executable
    result = _run(
        [
            "env",
            "PYTHONPATH=fichero-server/src",
            python_bin,
            "fichero-server/scripts/validate_model_sync.py",
        ]
    )
    if result.returncode == 0:
        return []
    detail = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    return [Violation("openapi-model-sync", "OpenAPI model sync", "model-drift", detail)]


def collect_violations() -> list[Violation]:
    collectors = [
        collect_swiftlint,
        collect_view_endpoint_access,
        lambda: _scan_guardrail("check_native_controls_report", "check_native_controls.py", "native-controls", prefix="fichero/fichero/Views/"),
        lambda: _scan_guardrail("check_no_emoji_report", "check_no_emoji_sf_symbols.py", "no-emoji-sf-symbols"),
        lambda: _scan_guardrail("check_comment_hygiene_report", "check_comment_hygiene.py", "comment-hygiene"),
        lambda: _scan_guardrail("check_feature_flags_report", "check_feature_flags.py", "feature-flags"),
        collect_duplicate_paths,
        collect_endpoint_usage,
        collect_ui_wiring,
        collect_version_date,
        collect_openapi_model_sync,
    ]
    violations: list[Violation] = []
    for collect in collectors:
        try:
            violations.extend(collect())
        except Exception as exc:
            name = getattr(collect, "__name__", "collector")
            violations.append(Violation("verify-report", name, "collector-error", str(exc)))
    return violations


class IssueClient:
    def __init__(self) -> None:
        self.available = shutil.which("gh") is not None
        self.disabled_reason = "" if self.available else "gh is not installed"

    def _gh(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        result = _run(["gh", *args])
        if result.returncode != 0:
            self.available = False
            self.disabled_reason = (result.stderr or result.stdout or "gh command failed").strip()
        return result

    def already_filed(self, violation: Violation) -> bool:
        if not self.available:
            return False
        for query in (violation.fingerprint, violation.title):
            result = self._gh(
                [
                    "issue",
                    "list",
                    "--search",
                    query,
                    "--state",
                    "all",
                    "--limit",
                    "1",
                    "--json",
                    "number",
                ]
            )
            if not self.available:
                return False
            try:
                if json.loads(result.stdout or "[]"):
                    return True
            except json.JSONDecodeError:
                self.available = False
                self.disabled_reason = "gh returned non-JSON issue list output"
                return False
        return False

    def create(self, violation: Violation) -> str:
        if not self.available:
            return "not-created-gh-unavailable"
        result = self._gh(
            [
                "issue",
                "create",
                "--title",
                violation.title,
                "--body",
                violation.body,
                "--milestone",
                violation.milestone,
            ]
        )
        if result.returncode != 0:
            return "create-failed"
        output = result.stdout.strip()
        return output.rsplit("/", 1)[-1] if output else "created"


def aggregate(violations: list[Violation]) -> list[Violation]:
    """Roll up per-finding violations into ONE issue per guardrail.

    Why: filing one issue per finding would create hundreds of issues and do
    hundreds of `gh` searches on every run. We instead emit a single rollup per
    guardrail with a STABLE fingerprint (location='all', rule='rollup') so a
    re-run dedups to the same issue and never spams. The body lists the current
    findings (capped) so the issue stays small and token-cheap.
    """
    from collections import OrderedDict

    groups: "OrderedDict[str, list[Violation]]" = OrderedDict()
    for v in violations:
        groups.setdefault(v.guardrail, []).append(v)

    rollups: list[Violation] = []
    for guardrail, items in groups.items():
        shown = items[:25]
        lines = [f"- `{v.location}` — {v.rule}: {v.detail}"[:300] for v in shown]
        if len(items) > len(shown):
            lines.append(f"- …and {len(items) - len(shown)} more")
        detail = f"{len(items)} finding(s):\n" + "\n".join(lines)
        rollups.append(Violation(guardrail, "all", "rollup", detail))
    return rollups


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="list what would be filed without creating issues")
    mode.add_argument("--apply", action="store_true", help="create missing issues")
    args = parser.parse_args(argv)

    apply = args.apply
    violations = aggregate(collect_violations())  # ≤ one rollup issue per guardrail
    client = IssueClient()

    known: list[Violation] = []
    new: list[Violation] = []
    for violation in violations:
        if client.already_filed(violation):
            known.append(violation)
        else:
            new.append(violation)

    filed: list[str] = []
    if apply:
        for violation in new:
            filed.append(client.create(violation))

    if apply:
        print(f"{len(known)} known (already filed), {len(filed)} new (filed {', '.join(filed) if filed else 'none'}).")
    else:
        print(f"{len(known)} known (already filed), {len(new)} new (dry-run, files nothing).")
        for violation in new:
            print(f"WOULD FILE {violation.fingerprint} [{violation.milestone}] {violation.title}")

    if not client.available:
        print(f"gh unavailable; treated existing issue state as unknown: {client.disabled_reason}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
