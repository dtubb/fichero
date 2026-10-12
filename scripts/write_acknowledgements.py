#!/usr/bin/env python3
"""What the app bundles, with each component's version and licence, as one JSON the About window shows (#5639,
`about.acknowledgements.generated`).

Read from what is actually bundled, never typed by hand: every `*.dist-info` in the engine's Python packages (the
staged engine's `app_packages`, or a venv's `site-packages`) and every pin in the Swift packages' `Package.resolved`.
Run by `preflight-embedded-engine.sh` after the bundle steps, into the staged engine's `Resources`:

    python scripts/write_acknowledgements.py --python <app_packages> \\
        --swift fichero/fichero.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved \\
        --out <engine.app>/Contents/Resources/acknowledgements.json

Exit 1 names each component whose licence could not be found (a Python package whose metadata states none, a Swift
package missing from `SWIFT_LICENCES`), so a new dependency is credited before it ships. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
from email.parser import HeaderParser
from pathlib import Path

#: Swift packages' licences: `Package.resolved` names a package and its version, never its licence. Keyed by the
#: pin's identity; a pin missing here fails the run (and `test_acknowledgements_5639.py`).
SWIFT_LICENCES: dict[str, str] = {
    "async-http-client": "Apache-2.0",
    "openapikit": "MIT",
    "sparkle": "MIT",
    "swift-algorithms": "Apache-2.0",
    "swift-argument-parser": "Apache-2.0",
    "swift-asn1": "Apache-2.0",
    "swift-async-algorithms": "Apache-2.0",
    "swift-atomics": "Apache-2.0",
    "swift-certificates": "Apache-2.0",
    "swift-collections": "Apache-2.0",
    "swift-configuration": "Apache-2.0",
    "swift-crypto": "Apache-2.0",
    "swift-distributed-tracing": "Apache-2.0",
    "swift-http-structured-headers": "Apache-2.0",
    "swift-http-types": "Apache-2.0",
    "swift-log": "Apache-2.0",
    "swift-markdown": "Apache-2.0",
    "swift-cmark": "BSD-2-Clause",
    "swift-metrics": "Apache-2.0",
    "swift-nio": "Apache-2.0",
    "swift-nio-extras": "Apache-2.0",
    "swift-nio-http2": "Apache-2.0",
    "swift-nio-ssl": "Apache-2.0",
    "swift-nio-transport-services": "Apache-2.0",
    "swift-numerics": "Apache-2.0",
    "swift-openapi-async-http-client": "Apache-2.0",
    "swift-openapi-generator": "Apache-2.0",
    "swift-openapi-runtime": "Apache-2.0",
    "swift-openapi-urlsession": "Apache-2.0",
    "swift-service-context": "Apache-2.0",
    "swift-service-lifecycle": "Apache-2.0",
    "swift-system": "Apache-2.0",
    "yams": "MIT",
}

_LICENCE_FILE_NAMES = ("LICENSE", "LICENCE", "COPYING", "NOTICE")
#: Fichero's own packages: not third-party, credited by the About window's own licence line.
OWN_PACKAGES = frozenset({"fichero-server", "fichero-cli", "fichero-mcp"})


def _python_licence(meta) -> str:
    """The licence a package's METADATA states: its SPDX expression, else a short `License:` line, else its OSI
    classifiers; "" when it states none."""
    expression = (meta.get("License-Expression") or "").strip()
    if expression:
        return expression
    # A `License:` field is sometimes the whole text: its first line names it ("MIT License").
    stated = next((line.strip() for line in (meta.get("License") or "").splitlines() if line.strip()), "")
    if stated and len(stated) <= 80 and stated.upper() != "UNKNOWN":
        return stated
    classifiers = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or []
                   if c.startswith("License ::") and c.strip() != "License :: OSI Approved"]
    return " OR ".join(dict.fromkeys(classifiers))


#: A licence named by its text, when the metadata names none: the opening words of the common licences.
_LICENCE_TEXTS = (("Permission is hereby granted, free of charge", "MIT"), ("Apache License", "Apache-2.0"),
                  ("Redistribution and use in source and binary forms", "BSD"),
                  ("GNU AFFERO GENERAL PUBLIC LICENSE", "AGPL-3.0"), ("GNU LESSER GENERAL PUBLIC LICENSE", "LGPL"),
                  ("GNU GENERAL PUBLIC LICENSE", "GPL"), ("Mozilla Public License", "MPL-2.0"))


def _licence_from_text(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")[:4000]
    return next((name for words, name in _LICENCE_TEXTS if words.lower() in text.lower()), "")


def _python_licence_text(dist_info: Path, meta) -> str | None:
    """Where the package's licence text is, relative to its packages folder; None when it ships none."""
    named = [f for f in meta.get_all("License-File") or []]
    candidates = [dist_info / "licenses" / f for f in named] + [dist_info / f for f in named]
    candidates += sorted(p for p in dist_info.rglob("*") if p.is_file() and p.name.upper().startswith(_LICENCE_FILE_NAMES))
    found = next((p for p in candidates if p.is_file()), None)
    return str(found.relative_to(dist_info.parent)) if found else None


def python_components(packages: Path) -> list[dict]:
    out = []
    for dist_info in sorted(packages.glob("*.dist-info")):
        metadata = dist_info / "METADATA"
        if not metadata.is_file():
            continue
        meta = HeaderParser().parsestr(metadata.read_text(encoding="utf-8", errors="replace"))
        name = meta.get("Name") or dist_info.name.split("-")[0]
        if name.lower().replace("_", "-") in OWN_PACKAGES:
            continue  # Fichero itself: the About window's own licence line
        text = _python_licence_text(dist_info, meta)
        out.append({"name": name, "version": meta.get("Version") or "",
                    "licence": _python_licence(meta) or _licence_from_text(packages / text if text else None),
                    "licence_text": text, "layer": "engine", "kind": "python"})
    return out


def swift_components(resolved: Path) -> list[dict]:
    pins = json.loads(resolved.read_text(encoding="utf-8")).get("pins", [])
    out = []
    for pin in pins:
        state = pin.get("state", {})
        version = state.get("version") or (state.get("revision") or "")[:12]
        location = (pin.get("location") or "").removesuffix(".git")
        out.append({"name": pin["identity"], "version": version, "licence": SWIFT_LICENCES.get(pin["identity"], ""),
                    "licence_text": f"{location}/blob/{state.get('revision')}/LICENSE" if location.startswith("https://")
                    else None, "layer": "app", "kind": "swift"})
    return out


def acknowledgements(python: list[Path], swift: list[Path]) -> dict:
    """The JSON: every component once, by layer and name; no timestamp, so it changes only when the bundle does."""
    seen: dict[tuple[str, str], dict] = {}
    for packages in python:
        for c in python_components(packages):
            seen.setdefault((c["kind"], c["name"].lower()), c)
    for resolved in swift:
        for c in swift_components(resolved):
            seen.setdefault((c["kind"], c["name"].lower()), c)
    components = sorted(seen.values(), key=lambda c: (c["layer"], c["name"].lower()))
    return {"format": "fichero-acknowledgements-v1", "components": components}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--python", action="append", default=[], type=Path, help="a site-packages or app_packages folder")
    parser.add_argument("--swift", action="append", default=[], type=Path, help="a Package.resolved")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    made = acknowledgements(args.python, args.swift)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(made, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    missing = [f"{c['kind']} {c['name']} {c['version']}" for c in made["components"] if not c["licence"]]
    print(f"Acknowledgements: {len(made['components'])} components -> {args.out}")
    if missing:
        print("error: no licence found for:\n  " + "\n  ".join(missing), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
