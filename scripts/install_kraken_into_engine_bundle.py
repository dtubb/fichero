#!/usr/bin/env python3
"""Install Kraken (and its genuinely missing dependencies) INTO the
Briefcase-built engine bundle, at build time, so it ships signed and
notarized with the app — never fetched or pip-installed at runtime (#4959:
a sandboxed app can neither copy its own executable into a venv nor load a
quarantined native library it wrote at runtime — see `kraken_runtime.py`'s
module docstring).

## Method

Kraken 7.1.1 pins `scipy~=1.15.3`/`click<8.3`/`rich<14.1.0`/`scikit-learn~=
1.7.2`, all OLDER than what the bundle already carries — a single resolve
refuses. So this installs kraken `--no-deps` (its own pins are never
consulted; the bundle's newer versions resolve instead), then
`missing_packages` normally (their transitive leaves are wanted), then
`no_deps_packages` (each `--no-deps` and hand-pinned — found only by
importing from a REAL bundle copy, because kraken's `--no-deps` install
hides its OWN transitive pins from a scratch-venv dry-run). All three read
`pyproject.toml`'s `[tool.fichero.kraken_bundle]` table — ONE place.

A constraints file (every distribution ALREADY in `app_packages`, pinned
`name==version`) is passed to every pip call, so a dependency that would
otherwise resolve off-pin FAILS instead of landing a second dist-info next
to the one the codesign pass already covers. After install, every
project name in `app_packages` must map to exactly one dist-info — belt and
braces against the same failure mode.

Refuses if this interpreter's Python does not match the bundle's own
(`release-all.sh` must invoke this with the project's `.venv` Python, via
`scripts/find_project_python.sh` — not a bare `python3`, whose ABI can drift
from the bundle's `python_version` pin and would fill it with wheels for a
different Python.

## Where this runs

Modelled on `scripts/place_pdfium_for_kreuzberg.py`'s seam in
`scripts/release-all.sh`: AFTER the bundle stages, BEFORE signing (Briefcase
has no supported post-build/pre-sign hook of its own).

## Usage

    <project-python> scripts/install_kraken_into_engine_bundle.py <path-to-app_packages>

Exits non-zero, with a specific reason, on any failure — never silently.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

_NAME_RE = re.compile(r"^Name:\s*(.+)$", re.MULTILINE)
_VERSION_RE = re.compile(r"^Version:\s*(.+)$", re.MULTILINE)
_CPYTHON_EXT_RE = re.compile(r"\.cpython-3(\d{1,2})-darwin\.so$")


def _normalize(name: str) -> str:
    """PEP 503 project-name normalization: case/`-_.`-insensitive."""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def _kraken_bundle_table() -> dict:
    """Read `pyproject.toml`'s `[tool.fichero.kraken_bundle]` (ONE place;
    `kraken_runtime.py` and the packaging test read the SAME table, never a
    copy)."""
    import tomllib

    pyproject = Path(__file__).resolve().parents[1] / "fichero-server" / "pyproject.toml"
    with open(pyproject, "rb") as fh:
        data = tomllib.load(fh)
    return data["tool"]["fichero"]["kraken_bundle"]


def _bundle_python_version(app_packages: Path) -> tuple[int, int] | None:
    """(major, minor) the bundle's OWN compiled extensions were built for,
    read from an existing `*.cpython-3XX-darwin.so` filename already inside
    `app_packages` — the ground truth on disk, not a guess."""
    for path in app_packages.rglob("*.cpython-3*-darwin.so"):
        m = _CPYTHON_EXT_RE.search(path.name)
        if m:
            return (3, int(m.group(1)))
    return None


def _dist_info_name_versions(app_packages: Path) -> dict[str, list[tuple[str, str]]]:
    """normalized project name -> [(raw name, version), ...] for every
    `*.dist-info` under `app_packages`. More than one entry for a name means
    pip landed two metadata records for one project — the shape `--target`
    silently allows when a dependency resolves off-pin (found by hand, 2026-
    09-20 trial: numpy could resolve newer than the bundle's own copy)."""
    by_name: dict[str, list[tuple[str, str]]] = {}
    for entry in app_packages.glob("*.dist-info"):
        metadata = entry / "METADATA"
        if not metadata.is_file():
            continue
        text = metadata.read_text(encoding="utf-8", errors="replace")
        name_m, version_m = _NAME_RE.search(text), _VERSION_RE.search(text)
        if not name_m or not version_m:
            continue
        name, version = name_m.group(1).strip(), version_m.group(1).strip()
        by_name.setdefault(_normalize(name), []).append((name, version))
    return by_name


def _write_constraints_file(app_packages: Path, dest: Path) -> None:
    """`name==version` for every distribution ALREADY in the bundle."""
    lines = []
    for versions in _dist_info_name_versions(app_packages).values():
        raw_name, version = versions[0]
        lines.append(f"{raw_name}=={version}")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_pip(app_packages: Path, args: list[str], *, constraints: Path) -> None:
    cmd = [
        sys.executable, "-m", "pip", "install",
        "--target", str(app_packages), "-c", str(constraints), *args,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"error: pip install failed: {' '.join(args)}", file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(4)
    # A "Target directory ... already exists" warning is the EXPECTED,
    # SAFE shape (a pre-existing distribution was correctly left alone,
    # not overwritten) -- print for visibility, never treat as failure.
    if result.stderr.strip():
        print(result.stderr, file=sys.stderr)


def install(app_packages: Path) -> int:
    if not app_packages.is_dir():
        print(f"error: not a directory: {app_packages}", file=sys.stderr)
        return 1

    bundle_py = _bundle_python_version(app_packages)
    if bundle_py is None or bundle_py != sys.version_info[:2]:
        found = f"{bundle_py[0]}.{bundle_py[1]}" if bundle_py else "unknown (no *.cpython-3XX-darwin.so found)"
        print(
            f"error: refusing to install -- this interpreter is Python "
            f"{sys.version_info[0]}.{sys.version_info[1]}, but the bundle's own compiled "
            f"extensions are for Python {found}. Wheels installed with the wrong "
            f"interpreter will not load. Run this with the PROJECT python "
            f"(scripts/find_project_python.sh), not a bare `python3`.",
            file=sys.stderr,
        )
        return 6

    table = _kraken_bundle_table()
    kraken_version = str(table["version"])
    missing_packages = tuple(table["missing_packages"])
    no_deps_packages = tuple(table.get("no_deps_packages", ()))

    before = _dist_info_name_versions(app_packages)
    if not before:
        print(f"error: no *.dist-info under {app_packages} — is this really app_packages?", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        constraints = Path(tmp) / "kraken-bundle-constraints.txt"
        _write_constraints_file(app_packages, constraints)

        # Step 1: kraken itself, --no-deps -- its own conflicting pins are
        # never consulted; the bundle's newer scipy/torch/numpy/click/rich/
        # scikit-learn are what `import kraken` will actually resolve against.
        _run_pip(app_packages, ["--no-deps", f"kraken=={kraken_version}"], constraints=constraints)

        # Step 2: what the bundle genuinely lacks -- normal resolution, so
        # each package's own transitive leaves land too. `-c` makes any of
        # those leaves that ALSO happen to already be in the bundle resolve
        # to the bundle's own version, or fail loudly, rather than landing
        # a second dist-info at a different version.
        if missing_packages:
            _run_pip(app_packages, list(missing_packages), constraints=constraints)

        # Step 3: packages that need --no-deps AND a hand pin because their
        # own resolution would try to move an already-pinned bundle package
        # (torchvision -> torch, above all). Found only by importing from a
        # REAL bundle copy (2026-09-20 manager trial): kraken's own
        # `torchvision>=0.5.0` pin is invisible to a --no-deps kraken
        # install, so a scratch-venv dry-run cannot see this gap.
        for pinned in no_deps_packages:
            _run_pip(app_packages, ["--no-deps", pinned], constraints=constraints)

    after = _dist_info_name_versions(app_packages)
    changed = [
        name for name, versions in before.items()
        if after.get(name) != versions
    ]
    duplicated = [name for name, versions in after.items() if len(versions) > 1]
    if changed or duplicated:
        if changed:
            print(
                f"error: installing Kraken changed a distribution ALREADY in the bundle: {sorted(changed)}",
                file=sys.stderr,
            )
        if duplicated:
            print(
                f"error: installing Kraken left TWO dist-info records for one project: {sorted(duplicated)}",
                file=sys.stderr,
            )
        print(
            "       this means a pin drifted -- resolve it by hand "
            "([tool.fichero.kraken_bundle] in pyproject.toml), never by letting "
            "pip silently replace or duplicate a bundle package (torch, numpy, "
            "scipy above all).",
            file=sys.stderr,
        )
        return 3

    if not any(name.startswith("kraken") for name in after):
        print("error: kraken.dist-info not found after install — did step 1 silently no-op?", file=sys.stderr)
        return 5

    total = len(missing_packages) + len(no_deps_packages)
    print(f"ok: kraken=={kraken_version} plus {total} missing package(s) installed into {app_packages}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 1
    return install(Path(argv[1]))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
