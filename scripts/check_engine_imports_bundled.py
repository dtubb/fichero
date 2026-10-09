#!/usr/bin/env python3
"""Every third-party module the engine imports is inside the staged engine bundle (2026-10-09).

The maintainer's rule: everything the app needs ships inside it. Found by this audit the first time:
security-scoped bookmarks (rubicon), background removal (rembg), Apple Speech, camera RAW (rawpy) and a
PDF outline reader (pypdf) were imported by the engine and never bundled, so each failed only in the
app. Run by `preflight-embedded-engine.sh` after the bundle steps, against the real `app_packages`.

    python scripts/check_engine_imports_bundled.py <path-to-app_packages>

Exit 1 names each missing module and the files that import it.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [ROOT / "fichero-server/src/fichero_server", ROOT / "fichero-mcp/src/fichero_mcp",
           ROOT / "fichero-cli/src/fichero_cli"]

#: Imported but deliberately not bundled, each with why. Keep this short.
NOT_BUNDLED = {
    "peft": "Hugging Face training: runs on Hugging Face Jobs, never in the app",
    "iiif_fetch": "the cluster job's own module, run on the cluster (remote_read/runner.py)",
    "cld3": "optional language detector with a built-in fallback (llm/multilingual.py)",
    "libxmp": "XMP needs the exempi C library; to be read as XML instead (#5638)",
}


def bundled_modules(app_packages: Path) -> set[str]:
    have: set[str] = set()
    for entry in app_packages.iterdir():
        if entry.name.endswith(".dist-info"):
            top_level = entry / "top_level.txt"
            if top_level.exists():
                have |= {line.strip() for line in top_level.read_text().split() if line.strip()}
            continue
        have.add(entry.name.split(".")[0])
    return have


def engine_imports() -> dict[str, set[str]]:
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    uses: dict[str, set[str]] = {}
    for src in SOURCES:
        for path in src.rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module]
                else:
                    continue
                for name in names:
                    top = name.split(".")[0]
                    if top not in stdlib and not top.startswith("fichero"):
                        uses.setdefault(top, set()).add(str(path.relative_to(ROOT)))
    return uses


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    have = bundled_modules(Path(argv[1]))
    missing = {name: files for name, files in engine_imports().items()
               if name not in have and name not in NOT_BUNDLED}
    if missing:
        print("error: the engine imports modules the app does not bundle:", file=sys.stderr)
        for name, files in sorted(missing.items()):
            print(f"  {name}: {', '.join(sorted(files)[:3])}", file=sys.stderr)
        print("Bundle each (a build step after briefcase update -r, as Kraken and MLX are), or list it in "
              "NOT_BUNDLED with why.", file=sys.stderr)
        return 1
    print("ok: every module the engine imports is bundled (or listed as not bundled, with why)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
