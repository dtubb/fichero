#!/usr/bin/env python3
"""Install MLX (mlx, mlx-lm, mlx-vlm, mlx-whisper) INTO the Briefcase-built engine bundle, at build
time, so it ships signed and notarized with the app (#4973, ruled 2026-10-09: everything the app needs
ships inside it). The sandboxed app could not build its own MLX runtime after install ("Operation not
permitted"), so local vision, OCR, text and Whisper models only ever worked with a dev engine.

Same method and checks as `install_kraken_into_engine_bundle.py` (its helpers are reused): every pip
call is constrained to the bundle's own pins, a bundle distribution may not change or be duplicated, and
the interpreter must match the bundle's Python. `[tool.fichero.mlx_bundle]` in pyproject.toml is the one
list: `missing_packages` resolve normally, then `no_deps_packages` go in `--no-deps`.

Runs after the Kraken step in `preflight-embedded-engine.sh`.

    <project-python> scripts/install_mlx_into_engine_bundle.py <path-to-app_packages>
"""

from __future__ import annotations

import sys
import tempfile
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_kraken_into_engine_bundle import (  # noqa: E402
    _bundle_python_version,
    _dist_info_name_versions,
    _run_pip,
    _write_constraints_file,
)


def _table() -> dict:
    pyproject = Path(__file__).resolve().parents[1] / "fichero-server" / "pyproject.toml"
    with open(pyproject, "rb") as fh:
        return tomllib.load(fh)["tool"]["fichero"]["mlx_bundle"]


def install(app_packages: Path) -> int:
    if not app_packages.is_dir():
        print(f"error: not a directory: {app_packages}", file=sys.stderr)
        return 1
    bundle_py = _bundle_python_version(app_packages)
    if bundle_py != sys.version_info[:2]:
        print(f"error: refusing: this is Python {sys.version_info[0]}.{sys.version_info[1]} and the bundle's "
              f"extensions are for {bundle_py}; run this with the project python", file=sys.stderr)
        return 6
    table = _table()
    before = _dist_info_name_versions(app_packages)
    if not before:
        print(f"error: no *.dist-info under {app_packages}", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        constraints = Path(tmp) / "mlx-bundle-constraints.txt"
        _write_constraints_file(app_packages, constraints)
        _run_pip(app_packages, list(table["missing_packages"]), constraints=constraints)
        for pinned in table["no_deps_packages"]:
            _run_pip(app_packages, ["--no-deps", pinned], constraints=constraints)
    after = _dist_info_name_versions(app_packages)
    changed = [n for n, v in before.items() if after.get(n) != v]
    duplicated = [n for n, v in after.items() if len(v) > 1]
    if changed or duplicated:
        print(f"error: installing MLX changed {sorted(changed)} or duplicated {sorted(duplicated)} in the bundle; "
              "fix the pins in [tool.fichero.mlx_bundle], never let pip replace a bundle package", file=sys.stderr)
        return 3
    for needed in ("mlx", "mlx-lm", "mlx-vlm", "mlx-whisper", "ultralytics", "rubicon-objc", "rembg", "rawpy", "pypdf", "av"):
        if needed not in after:
            print(f"error: {needed} is not in the bundle after install", file=sys.stderr)
            return 5
    print(f"ok: MLX ({', '.join(table['no_deps_packages'])}) installed into {app_packages}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 1
    return install(Path(argv[1]))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
