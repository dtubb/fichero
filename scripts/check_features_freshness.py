#!/usr/bin/env python3
"""Fail when generated feature-tier artifacts drift from features.yaml."""
from __future__ import annotations

from pathlib import Path
import filecmp
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
FILES = (
    Path("docs/user/features.md"),
    Path("fichero/fichero/Models/FeatureTiers.generated.swift"),
    Path("fichero-server/src/fichero_server/api/feature_tiers_generated.py"),
)
COPIED = (
    Path("features.yaml"),
    Path("scripts/gen_feature_tiers.py"),
    *FILES,
)


def _copy_tree(dst_root: Path) -> None:
    for rel in COPIED:
        src = ROOT / rel
        dst = dst_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _generate(dst_root: Path) -> None:
    subprocess.run(
        [sys.executable, "scripts/gen_feature_tiers.py"],
        cwd=dst_root,
        check=True,
    )


def _stale_files(dst_root: Path) -> list[Path]:
    stale: list[Path] = []
    for rel in FILES:
        if not filecmp.cmp(ROOT / rel, dst_root / rel, shallow=False):
            stale.append(rel)
    return stale


def _stale_between(lhs_root: Path, rhs_root: Path) -> list[Path]:
    stale: list[Path] = []
    for rel in FILES:
        if not filecmp.cmp(lhs_root / rel, rhs_root / rel, shallow=False):
            stale.append(rel)
    return stale


def check_repo() -> int:
    with tempfile.TemporaryDirectory(prefix="feature-tiers-") as tmp:
        tmp_root = Path(tmp)
        _copy_tree(tmp_root)
        _generate(tmp_root)
        stale = _stale_files(tmp_root)
    if not stale:
        print("OK: feature-tier artifacts are fresh")
        return 0
    for rel in stale:
        print(f"STALE: {rel}")
    print("run python scripts/gen_feature_tiers.py")
    return 1


def self_check() -> int:
    with tempfile.TemporaryDirectory(prefix="feature-tiers-self-check-") as tmp:
        tmp_root = Path(tmp)
        drifted_root = tmp_root / "drifted"
        fresh_root = tmp_root / "fresh"
        _copy_tree(drifted_root)
        _copy_tree(fresh_root)
        drifted = drifted_root / FILES[0]
        drifted.write_text(drifted.read_text() + "\n<!-- self-check drift -->\n")
        _generate(fresh_root)
        stale = _stale_between(drifted_root, fresh_root)
    if stale:
        print("OK: self-check caught stale/generated drift")
        return 0
    print("FAIL: self-check did not catch stale/generated drift", file=sys.stderr)
    return 1


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[1] == "--self-check":
        return self_check()
    if len(argv) != 1:
        print("usage: python scripts/check_features_freshness.py [--self-check]", file=sys.stderr)
        return 2
    return check_repo()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
