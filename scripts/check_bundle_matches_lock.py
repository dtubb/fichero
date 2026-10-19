#!/usr/bin/env python3
"""Fail if any distribution in the engine bundle differs from fichero-server/uv.lock.

The bundle is installed with the lock's versions as pip constraints, so it should equal
the venv the tests ran against. A bundled package the lock also resolves must carry one
of the lock's versions. Packages the lock does not know (Kraken, MLX, their extras) are
installed by their own steps and are not checked here.

usage: check_bundle_matches_lock.py <app_packages> <uv.lock>
       check_bundle_matches_lock.py --sdist-only <uv.lock>   (print name==version for pins with no wheel)
"""

import re
import sys
import tomllib
from email.parser import HeaderParser
from pathlib import Path


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def main(app_packages: Path, lock: Path) -> int:
    locked: dict[str, set[str]] = {}
    for pkg in tomllib.loads(lock.read_text())["package"]:
        if "version" in pkg:
            locked.setdefault(norm(pkg["name"]), set()).add(pkg["version"])

    drift = []
    for meta in sorted(app_packages.glob("*.dist-info/METADATA")):
        headers = HeaderParser().parsestr(meta.read_text(errors="replace"))
        name, version = norm(headers["Name"]), headers["Version"]
        if name in locked and version not in locked[name]:
            drift.append(f"  {name} {version} (lock: {', '.join(sorted(locked[name]))})")

    if drift:
        print("error: the engine bundle differs from uv.lock:", file=sys.stderr)
        print("\n".join(drift), file=sys.stderr)
        return 1
    print("  Bundle matches uv.lock")
    return 0


def sdist_only(lock: Path) -> None:
    for pkg in tomllib.loads(lock.read_text())["package"]:
        if "version" in pkg and "sdist" in pkg and not pkg.get("wheels"):
            print(f"{pkg['name']}=={pkg['version']}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--sdist-only":
        sys.exit(sdist_only(Path(sys.argv[2])))
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
