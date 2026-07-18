#!/usr/bin/env python3
"""Codemod bucket-A + pure bucket-B AppKit usage into Platform* shims.

Run from repo root:
    python3 scripts/ios_shim_codemod.py
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Bucket A: files where import AppKit is unused and should be removed.
BUCKET_A: list[str] = [
    "fichero/fichero/Views/Library/ArtifactRichTextCodec.swift",
]

# Bucket B: files whose ONLY AppKit symbols are shimmable (NSImage/NSColor/NSFont/NSViewRepresentable).
# Conservatively limited to files confirmed to contain no NSWindow/NSApp/NSEvent/NSSavePanel/etc.
BUCKET_B: list[str] = [
    "fichero/fichero/Views/Components/BackendConnectionView.swift",
    "fichero/fichero/Services/ImageEditingServiceGenerated.swift",
    "fichero/fichero/Views/Preview/ImageEditor/ImageEditorView.swift",
    "fichero/fichero/Views/Preview/ImageEditor/ImageEditorModel.swift",
    "fichero/fichero/Views/Library/PDFThumbnailView.swift",
]

# Word-boundary replacements for pure bucket-B files.
SUBSTITUTIONS: dict[str, str] = {
    "NSImage": "PlatformImage",
    "NSColor": "PlatformColor",
    "NSFont": "PlatformFont",
    "NSViewRepresentable": "PlatformViewRepresentable",
}

IMPORT_APPKIT_RE = re.compile(r"^import AppKit\s*$", re.MULTILINE)

# PlatformAliases.swift paths (we may add missing aliases here)
ALIASES_FILE = ROOT / "fichero/fichero/Models/Platform/PlatformAliases.swift"


def ensure_platform_aliases() -> list[str]:
    """Add PlatformFont / PlatformViewRepresentable aliases if missing."""
    text = ALIASES_FILE.read_text()
    added: list[str] = []

    def has_alias(name: str) -> bool:
        return re.search(rf"\btypealias\s+{re.escape(name)}\b", text) is not None

    mac_image_block = re.search(
        r"(#if canImport\(AppKit\).*?typealias PlatformImage = NSImage)",
        text,
        re.DOTALL,
    )
    ios_image_block = re.search(
        r"(#elseif canImport\(UIKit\).*?typealias PlatformImage = UIImage)",
        text,
        re.DOTALL,
    )

    if mac_image_block and not (has_alias("PlatformFont") and has_alias("PlatformViewRepresentable")):
        insert = mac_image_block.end()
        additions = []
        if not has_alias("PlatformFont"):
            additions.append("\n\ntypealias PlatformFont = NSFont")
        if not has_alias("PlatformViewRepresentable"):
            additions.append("\n\ntypealias PlatformViewRepresentable = NSViewRepresentable")
        text = text[:insert] + "".join(additions) + text[insert:]
        added.extend(a.strip() for a in additions)

    if ios_image_block and not (has_alias("PlatformFont") and has_alias("PlatformViewRepresentable")):
        insert = ios_image_block.end()
        additions = []
        if not has_alias("PlatformFont"):
            additions.append("\n\ntypealias PlatformFont = UIFont")
        if not has_alias("PlatformViewRepresentable"):
            additions.append("\n\ntypealias PlatformViewRepresentable = UIViewRepresentable")
        text = text[:insert] + "".join(additions) + text[insert:]
        added.extend(a.strip() for a in additions)

    if added:
        ALIASES_FILE.write_text(text)
        print(f"Updated {ALIASES_FILE.relative_to(ROOT)}")
        for a in added:
            print(f"  + {a}")

    return added


def remove_appkit_import(path: Path) -> bool:
    text = path.read_text()
    new_text, n = IMPORT_APPKIT_RE.subn("", text)
    if n == 0:
        return False
    # strip trailing blank lines at top of file if import was first line
    new_text = re.sub(r"\A\n+", "", new_text)
    path.write_text(new_text)
    print(f"Bucket A: removed import AppKit from {path.relative_to(ROOT)}")
    return True


def shim_bucket_b(path: Path) -> tuple[bool, dict[str, int]]:
    text = path.read_text()

    # First pass: count substitutions we would make.
    counts: dict[str, int] = {}
    for old, new in SUBSTITUTIONS.items():
        counts[old] = len(re.findall(rf"\b{re.escape(old)}\b", text))

    # Replace import AppKit with canImport guard.
    new_text, n = IMPORT_APPKIT_RE.subn(
        "#if canImport(AppKit)\nimport AppKit\n#elseif canImport(UIKit)\nimport UIKit\n#endif",
        text,
    )
    import_changed = n > 0

    # Apply word-boundary symbol substitutions.
    for old, new in SUBSTITUTIONS.items():
        new_text = re.sub(rf"\b{re.escape(old)}\b", new, new_text)

    changed = import_changed or any(counts.values())
    if changed:
        path.write_text(new_text)
        print(f"Bucket B: shimmed {path.relative_to(ROOT)}")
        if import_changed:
            print("  + import AppKit → #if canImport(AppKit)/import AppKit/#elseif canImport(UIKit)/import UIKit/#endif")
        for old, c in counts.items():
            if c:
                print(f"  + {old} → {SUBSTITUTIONS[old]} ({c} occurrence{'s' if c != 1 else ''})")

    return changed, counts


def main() -> int:
    added_aliases = ensure_platform_aliases()
    if added_aliases:
        print()

    changed_files: list[Path] = []

    for rel in BUCKET_A:
        p = ROOT / rel
        if p.exists() and remove_appkit_import(p):
            changed_files.append(p)

    for rel in BUCKET_B:
        p = ROOT / rel
        if p.exists():
            changed, _ = shim_bucket_b(p)
            if changed:
                changed_files.append(p)

    print(f"\nTotal files changed: {len(changed_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
