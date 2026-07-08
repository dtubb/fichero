#!/usr/bin/env python3
"""Gardener helper for DX guardrails and roadmap progression.

Deterministic, read-only by default:

* Runs `scripts/verify_all.sh` at the requested tier.
* Summarizes guardrail baselines from known gaps/violations.
* Summarizes milestone progress and selects next work via `choose_next`.
* Optionally files issues when explicitly requested.

Usage:
    scripts/gardener.py
    scripts/gardener.py --tier fast
    scripts/gardener.py --json
    scripts/gardener.py --apply-issues
    scripts/gardener.py --self-test
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
ROADMAP_PATH = ROOT / "agents" / "ROADMAP.md"


@dataclass(frozen=True)
class GuardrailSnapshot:
    key: str
    scope: str
    total_targets: int
    remaining: int
    known: int
    stale: int
    new: int
    mismatch: int = 0
    detail_preview: tuple[str, ...] = ()

    @property
    def completed(self) -> int:
        return max(self.total_targets - self.remaining, 0)

    @property
    def is_clean(self) -> bool:
        return self.new == 0 and self.mismatch == 0

    @property
    def key_fingerprint(self) -> str:
        seed = f"{self.key}|{','.join(sorted(self.detail_preview))}|{self.new}|{self.mismatch}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _run(args: list[str], *, capture: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            cwd=ROOT,
            text=True,
            capture_output=capture,
            check=False,
        )
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr=str(exc))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _analyze_check_view_endpoint_access(module) -> GuardrailSnapshot:
    found = module.scan()
    known = set(module.KNOWN_VIOLATIONS)
    found_keys = set(found)
    stale = sorted(known - found_keys)
    new = sorted(found_keys - known)

    all_views = [
        path for path in sorted(module.VIEWS_DIR.rglob("*.swift")) if not module.is_excluded(path)
    ]
    details = tuple(
        f"{path} ({'known' if path in known else 'new'})" for path in sorted(found_keys)
    )

    return GuardrailSnapshot(
        key="view-endpoint-access",
        scope="Observable Data Layer",
        total_targets=len(all_views),
        remaining=len(found_keys),
        known=len(known),
        stale=len(stale),
        new=len(new),
        detail_preview=details,
    )


def _analyze_check_dead_files(module) -> GuardrailSnapshot:
    found = module.scan()
    known = set(module.KNOWN_VIOLATIONS)
    found_keys = set(found)
    stale = sorted(known - found_keys)
    new = sorted(found_keys - known)

    all_files = []
    for path in sorted(module.swift_files()):
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        names = module.primary_types(path, source)
        if names and not module.is_entry_or_generated(path, source, names):
            all_files.append(path)
    details = tuple(f"{path}" for path in sorted(found_keys))

    return GuardrailSnapshot(
        key="dead-files",
        scope="Developer Experience",
        total_targets=len(all_files),
        remaining=len(found_keys),
        known=len(known),
        stale=len(stale),
        new=len(new),
        detail_preview=details,
    )


def _analyze_gap_rows(key: str, scope: str, module, *, id_attr: str) -> GuardrailSnapshot:
    rows = module.scan()
    offenders = {getattr(row, id_attr) for row in rows if bool(getattr(row, "gap", False))}
    found = set(offenders)
    known = set(getattr(module, "KNOWN_GAPS", {}))
    stale = sorted(known - found)
    new = sorted(found - known)
    details = tuple(f"{item}" for item in sorted(found)[:20])
    return GuardrailSnapshot(
        key=key,
        scope=scope,
        total_targets=len(rows),
        remaining=len(found),
        known=len(known),
        stale=len(stale),
        new=len(new),
        detail_preview=details,
    )


def _analyze_endpoint_usage(module) -> GuardrailSnapshot:
    _, rows = module.build_matrix()
    found = {row.endpoint: row.status for row in rows if row.status != "both"}
    known = set(getattr(module, "KNOWN_GAPS", {}))
    stale = sorted(known - set(found))
    new_keys = sorted(set(found) - known)
    details = tuple(f"{endpoint} ({status})" for endpoint, status in sorted(found.items())[:20])
    return GuardrailSnapshot(
        key="endpoint-usage",
        scope="Developer Experience",
        total_targets=len(rows),
        remaining=len(found),
        known=len(known),
        stale=len(stale),
        new=len(new_keys),
        detail_preview=details,
    )


def _analyze_openapi_client_parity(module) -> GuardrailSnapshot:
    operations, mismatches, missing_cli, _ = module.scan()
    found = {op.endpoint for op in missing_cli}
    known = set(getattr(module, "KNOWN_GAPS", {}))
    stale = sorted(known - found)
    new = sorted(found - known)
    details = (
        tuple(f"missing-cli {endpoint}" for endpoint in sorted(found)[:20])
        + tuple(f"openapi drift: {path}" for path in sorted(mismatches))
    )
    return GuardrailSnapshot(
        key="openapi-client-parity",
        scope="Developer Experience",
        total_targets=len(operations),
        remaining=len(found),
        known=len(known),
        stale=len(stale),
        new=len(new),
        mismatch=len(mismatches),
        detail_preview=details[:20],
    )


def _analyze_guardrail(module_name: str, extractor: Any, *, module_path: Path) -> GuardrailSnapshot:
    module = _load_module(module_name, module_path)
    return extractor(module)


def analyze_guardrails() -> list[GuardrailSnapshot]:
    configs = (
        ("check_view_endpoint_access", "check_view_endpoint_access", _analyze_check_view_endpoint_access),
        ("check_dead_files", "check_dead_files", _analyze_check_dead_files),
        ("check_endpoint_usage", "check_endpoint_usage", _analyze_endpoint_usage),
        (
            "check_endpoint_coverage_matrix",
            "check_endpoint_coverage_matrix",
            lambda module: _analyze_gap_rows("endpoint-coverage-matrix", "Developer Experience", module, id_attr="endpoint"),
        ),
        (
            "check_undo_coverage",
            "check_undo_coverage",
            lambda module: _analyze_gap_rows("undo-coverage-matrix", "Developer Experience", module, id_attr="endpoint"),
        ),
        (
            "check_action_surface_matrix",
            "check_action_surface_matrix",
            lambda module: _analyze_gap_rows("action-surface-matrix", "Mac Polish", module, id_attr="action"),
        ),
        (
            "check_openapi_client_parity",
            "check_openapi_client_parity",
            _analyze_openapi_client_parity,
        ),
    )

    snapshots: list[GuardrailSnapshot] = []
    for module_name, script_name, extractor in configs:
        path = SCRIPTS_DIR / f"{script_name}.py"
        module_alias = f"fichero_gardener_{module_name}"
        snapshots.append(_analyze_guardrail(module_alias, extractor, module_path=path))
    return snapshots


def _run_verify(tier: str) -> int:
    result = _run(["bash", "scripts/verify_all.sh", f"--{tier}"], capture=False)
    return result.returncode


def _milestone_counts(milestone: str) -> tuple[int, int]:
    proc = _run(
        [
            "gh",
            "issue",
            "list",
            "--milestone",
            milestone,
            "--state",
            "all",
            "--limit",
            "200",
            "--json",
            "number,state",
        ]
    )
    if proc.returncode != 0:
        return (0, 0)
    try:
        payload = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return (0, 0)
    total = len(payload)
    open_count = sum(1 for item in payload if item.get("state") == "OPEN")
    return open_count, total


def _format_progress(snapshot: GuardrailSnapshot) -> str:
    base = f"{snapshot.key} [{snapshot.scope}] "
    if snapshot.total_targets:
        base += f"progress {snapshot.completed}/{snapshot.total_targets}"
    else:
        base += "progress N/A"
    base += f" | remaining={snapshot.remaining}"
    if snapshot.stale:
        base += f" | stale_known={snapshot.stale}"
    if snapshot.mismatch:
        base += f" | mismatches={snapshot.mismatch}"
    if snapshot.detail_preview:
        base += f" | sample={'; '.join(snapshot.detail_preview[:3])}"
    return base


def _already_filed(fingerprint: str) -> bool:
    if shutil.which("gh") is None:
        return False
    proc = _run(
        [
            "gh",
            "issue",
            "list",
            "--search",
            fingerprint,
            "--state",
            "all",
            "--json",
            "number",
            "--limit",
            "1",
        ]
    )
    if proc.returncode != 0:
        return False
    try:
        rows = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return False
    return bool(rows)


def _create_issue(title: str, body: str, milestone: str | None = None) -> str:
    if shutil.which("gh") is None:
        return "create-failed-gh-unavailable"
    args = ["gh", "issue", "create", "--title", title, "--body", body]
    if milestone:
        args.extend(["--milestone", milestone])
    proc = _run(args, capture=True)
    if proc.returncode != 0:
        return "create-failed"
    link = proc.stdout.strip()
    return link.rsplit("/", 1)[-1] if link else "created"


def _issue_body(snapshot: GuardrailSnapshot) -> str:
    lines = [
        f"Fingerprint: {snapshot.key_fingerprint}",
        "",
        f"Guardrail: {snapshot.key}",
        f"Scope: {snapshot.scope}",
        f"Remaining: {snapshot.remaining}",
        f"Known baseline: {snapshot.known}",
        f"New offenders: {snapshot.new}",
        f"Stale known offenders: {snapshot.stale}",
    ]
    if snapshot.mismatch:
        lines.append(f"Surface mismatches: {snapshot.mismatch}")
    if snapshot.detail_preview:
        lines.append("")
        for detail in snapshot.detail_preview[:25]:
            lines.append(f"- {detail}")
    return "\n".join(lines)


def file_issues_for_new_gaps(snapshots: list[GuardrailSnapshot]) -> tuple[list[str], list[str]]:
    new = [snapshot for snapshot in snapshots if snapshot.new > 0 or snapshot.mismatch > 0]
    created: list[str] = []
    skipped: list[str] = []
    for snapshot in new:
        fresh = snapshot.new + snapshot.mismatch
        title = f"[gardener] {snapshot.scope} — {snapshot.key} fresh gap(s): {fresh}"
        if _already_filed(snapshot.key_fingerprint):
            skipped.append(f"[SKIP] {snapshot.key} already filed ({snapshot.key_fingerprint})")
            continue
        issue_id = _create_issue(title=title, body=_issue_body(snapshot))
        if issue_id == "create-failed":
            created.append(f"[FAIL] {snapshot.key}")
        elif issue_id == "create-failed-gh-unavailable":
            created.append(f"[SKIP] {snapshot.key} (gh unavailable)")
        else:
            created.append(f"{snapshot.key} -> #{issue_id}")
    return created, skipped


def _choose_next_payload() -> dict[str, Any]:
    choose_next = _load_module("fichero_choose_next", SCRIPTS_DIR / "choose_next.py")
    tiers = choose_next.parse_roadmap()
    if not tiers:
        return {"selection": {"issues": []}, "tiers": []}
    issues = choose_next.load_issues(tiers, fixture=None, limit=1000)
    selection = choose_next.select_batch(tiers, issues)
    return {
        "selection": selection,
        "tiers": [
            {"key": tier.key, "title": tier.title, "milestones": list(tier.milestones)}
            for tier in tiers
        ],
    }


def summarize_milestone_progress() -> list[tuple[str, int, int]]:
    choose_next = _load_module("fichero_choose_next", SCRIPTS_DIR / "choose_next.py")
    tiers = choose_next.parse_roadmap(ROADMAP_PATH)
    progress: list[tuple[str, int, int]] = []
    seen = set()
    for tier in tiers:
        for milestone in tier.milestones:
            if milestone in seen:
                continue
            seen.add(milestone)
            open_count, total_count = _milestone_counts(milestone)
            progress.append((milestone, open_count, total_count))
    return progress


def run_self_test() -> int:
    sample = GuardrailSnapshot(
        key="self-test",
        scope="test",
        total_targets=10,
        remaining=3,
        known=4,
        stale=1,
        new=2,
        detail_preview=("a", "b"),
    )
    text = _format_progress(sample)
    assert "progress" in text, text

    choose_next = _load_module("fichero_choose_next_test", SCRIPTS_DIR / "choose_next.py")
    assert choose_next.run_self_test() == 0
    print("gardener self-test passed")
    return 0


def render_text_report(
    verify_exit: int,
    snapshots: list[GuardrailSnapshot],
    milestone_progress: list[tuple[str, int, int]],
    next_payload: dict[str, Any],
) -> str:
    lines = [
        "GARDENER REPORT",
        f"verify_exit: {verify_exit}",
        "",
        "Guardrail progress:",
    ]
    for snapshot in snapshots:
        lines.append(f"- {_format_progress(snapshot)}")

    lines.extend(["", "Milestone progress (roadmap):"])
    for milestone, open_count, total_count in milestone_progress:
        lines.append(f"- {milestone}: open={open_count}, total={total_count}")

    selection = next_payload.get("selection", {})
    lines.append("")
    lines.append("Next issue selection:")
    if not selection.get("issues"):
        lines.append("  No ready unclaimed issue found.")
    else:
        lines.append(f"  Tier: {selection.get('tier', {}).get('key')} - {selection.get('tier', {}).get('title')}")
        lines.append(f"  Milestone: {selection.get('milestone')}")
        lines.append(f"  Mode: {selection.get('mode')}")
        lines.append(f"  Model: {selection.get('model')}")
        lines.append(f"  Objective: {selection.get('objective')}")
        for issue in selection.get("issues", []):
            lines.append(f"  - #{issue['number']} {issue['title']}")

    return "\n".join(lines)


def render_json_report(
    verify_exit: int,
    snapshots: list[GuardrailSnapshot],
    milestone_progress: list[tuple[str, int, int]],
    next_payload: dict[str, Any],
    apply_summary: list[str] | None = None,
    skip_summary: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "verify_exit": verify_exit,
            "guardrails": [
                {
                    "key": snap.key,
                    "scope": snap.scope,
                    "total_targets": snap.total_targets,
                    "remaining": snap.remaining,
                    "known": snap.known,
                    "stale": snap.stale,
                    "new": snap.new,
                    "mismatch": snap.mismatch,
                    "fingerprint": snap.key_fingerprint,
                    "is_clean": snap.is_clean,
                }
                for snap in snapshots
            ],
            "milestone_progress": [
                {"name": name, "open": open_count, "total": total_count}
                for name, open_count, total_count in milestone_progress
            ],
            "next_selection": next_payload.get("selection"),
            "issues_created": apply_summary or [],
            "issues_skipped": skip_summary or [],
        },
        sort_keys=True,
        indent=2,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=("fast", "standard", "full"), default="standard")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--apply-issues",
        action="store_true",
        help="Create issues for fresh guardrail gaps.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run deterministic gardener self-test.",
    )
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    verify_exit = _run_verify(args.tier)

    snapshots = analyze_guardrails()
    try:
        milestone_progress = summarize_milestone_progress()
    except Exception as exc:
        milestone_progress = []
        print(f"gardener: milestone summary unavailable ({exc})")

    try:
        next_payload = _choose_next_payload()
    except Exception as exc:
        next_payload = {"selection": {"issues": []}, "tiers": []}
        print(f"gardener: choose_next unavailable ({exc})")

    created: list[str] = []
    skipped: list[str] = []
    if args.apply_issues:
        created, skipped = file_issues_for_new_gaps(snapshots)

    if args.json:
        print(
            render_json_report(
                verify_exit=verify_exit,
                snapshots=snapshots,
                milestone_progress=milestone_progress,
                next_payload=next_payload,
                apply_summary=created,
                skip_summary=skipped,
            )
        )
    else:
        print(render_text_report(verify_exit, snapshots, milestone_progress, next_payload))
        if created:
            print("\nFiled issues:")
            for item in created:
                print(f"  - {item}")
        if skipped:
            print("\nSkipped (already filed):")
            for item in skipped:
                print(f"  - {item}")
        if verify_exit:
            print(f"\nverify_exit={verify_exit} — failing checks were reported above.")
        else:
            print("\nAll requested checks completed.")

    return verify_exit


if __name__ == "__main__":
    raise SystemExit(main())
