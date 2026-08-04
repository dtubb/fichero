#!/usr/bin/env python3
"""Xcode-registration guardrail — flag Swift files missing from the Fichero target.

Rule (#1941): every `.swift` file under `fichero/fichero/` must be registered in
`fichero/fichero.xcodeproj/project.pbxproj` so the Fichero target compiles it.
Files written only to disk are invisible to the compiler; after creating one,
run:

    ruby scripts/add-swift-file.rb fichero/fichero/Views/MyFolder/MyView.swift

This script parses the project file directly:
  * disk files come from `fichero/fichero/**/*.swift`
  * registered files come from the Fichero target's PBXSourcesBuildPhase
  * synchronized test roots (`PBXFileSystemSynchronizedRootGroup`) are reported
    for visibility but are outside this app-target scan

`KNOWN_VIOLATIONS` is the current orphan backlog. The script PASSES today
because every current orphan is listed, and it FAILS when a new Swift file under
the app source root is not registered in the Fichero target.

Usage:
    python3 scripts/check_xcode_registration.py
    python3 scripts/check_xcode_registration.py --list
    python3 scripts/check_xcode_registration.py -h

Exit codes:
    0  no new unregistered Swift files
    1  a Swift file under fichero/fichero/ is missing from the Fichero target
    2  BLIND — the committed project file could not be parsed / the Fichero
       target was not found (#4487); never a pass, never a fake violation
"""
from __future__ import annotations

import re
import sys

from _check_floor import require_scan_floor
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
XCODE_ROOT = ROOT / "fichero"
SWIFT_ROOT = XCODE_ROOT / "fichero"
PROJECT_FILE = XCODE_ROOT / "fichero.xcodeproj" / "project.pbxproj"
TARGET_NAME = "Fichero"
RULE_DOC = "AGENTS.md"

# Swift files currently present on disk but not compiled by the Fichero target.
# Drop entries after registering with scripts/add-swift-file.rb or removing the
# orphaned file.
KNOWN_VIOLATIONS: dict[str, str] = {
}

OBJECT_HEADER = re.compile(r"^\t\t([A-Za-z0-9_]+)(?: /\* .*? \*/)? = \{$")
OBJECT_INLINE = re.compile(r"^\t\t([A-Za-z0-9_]+)(?: /\* .*? \*/)? = \{(.*)\};$")
FIELD = re.compile(r"^\s*([A-Za-z0-9_]+) = (.*?);$")
LIST_FIELD = re.compile(r"^\s*([A-Za-z0-9_]+) = \($")
LIST_ITEM = re.compile(r"^\s*([A-Za-z0-9_]+)(?: /\* .*? \*/)?,?$")
OBJECT_ID_VALUE = re.compile(r"^([A-Za-z0-9_]+)\b")
INLINE_FIELD = re.compile(r"\b([A-Za-z0-9_]+) = ([^;]+);")


@dataclass
class PBXObject:
    object_id: str
    isa: str | None = None
    fields: dict[str, str] = field(default_factory=dict)
    lists: dict[str, list[str]] = field(default_factory=dict)


def _unquote(value: str) -> str:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


def _path_part(value: str | None) -> str:
    if not value:
        return ""
    return _unquote(value).replace("\\", "/")


def _join(*parts: str) -> str:
    cleaned = [part.strip("/") for part in parts if part and part.strip("/")]
    return PurePosixPath(*cleaned).as_posix() if cleaned else ""


def parse_pbxproj(project_file: Path | None = None) -> dict[str, PBXObject]:
    # Resolved at CALL time (not a def-time default) so tests can either pass
    # a fixture path or monkeypatch the module constant — both existing styles.
    project_file = project_file or PROJECT_FILE
    objects: dict[str, PBXObject] = {}
    current: PBXObject | None = None
    list_key: str | None = None

    for line in project_file.read_text(errors="ignore").splitlines():
        if current is None:
            inline = OBJECT_INLINE.match(line)
            if inline:
                object_id, body = inline.groups()
                obj = PBXObject(object_id=object_id)
                for key, value in INLINE_FIELD.findall(body):
                    if key == "isa":
                        obj.isa = value
                    else:
                        obj.fields[key] = value
                objects[object_id] = obj
                continue

            header = OBJECT_HEADER.match(line)
            if header:
                current = PBXObject(object_id=header.group(1))
            continue

        if line.startswith("\t\t};"):
            objects[current.object_id] = current
            current = None
            list_key = None
            continue

        if list_key is not None:
            if line.strip() == ");":
                list_key = None
                continue
            item = LIST_ITEM.match(line)
            if item:
                current.lists.setdefault(list_key, []).append(item.group(1))
            continue

        list_match = LIST_FIELD.match(line)
        if list_match:
            list_key = list_match.group(1)
            current.lists.setdefault(list_key, [])
            continue

        field_match = FIELD.match(line)
        if field_match:
            key, value = field_match.groups()
            if key == "isa":
                current.isa = value
            else:
                current.fields[key] = value

    return objects


def synchronized_roots(objects: dict[str, PBXObject]) -> list[str]:
    roots = []
    for obj in objects.values():
        if obj.isa == "PBXFileSystemSynchronizedRootGroup":
            roots.append(_path_part(obj.fields.get("path")))
    return sorted(root for root in roots if root)


def target_synchronized_prefixes(objects: dict[str, PBXObject]) -> set[str]:
    """Repo-relative path prefixes covered by the target's synchronized root groups.

    Post-#3754 the Fichero app target compiles its whole source tree via a
    PBXFileSystemSynchronizedRootGroup (folder = source of truth) instead of
    listing each file in PBXSourcesBuildPhase. Every .swift under such a folder
    is compiled by construction, so an orphan is impossible there — files are
    only ever "unregistered" if they live OUTSIDE every synchronized root the
    target references (or outside an explicit Sources phase).
    """
    prefixes: set[str] = set()
    for obj in objects.values():
        if obj.isa != "PBXNativeTarget":
            continue
        if _unquote(obj.fields.get("name", "")) != TARGET_NAME:
            continue
        for group_id in obj.lists.get("fileSystemSynchronizedGroups", []):
            group = objects.get(group_id)
            if group and group.isa == "PBXFileSystemSynchronizedRootGroup":
                part = _path_part(group.fields.get("path"))
                if part:
                    prefixes.add(_join("fichero", part))
    return prefixes


def parent_map(objects: dict[str, PBXObject]) -> dict[str, str]:
    parents: dict[str, str] = {}
    for parent_id, obj in objects.items():
        for child_id in obj.lists.get("children", []):
            parents[child_id] = parent_id
    return parents


def group_path(
    group_id: str,
    objects: dict[str, PBXObject],
    parents: dict[str, str],
    memo: dict[str, str],
) -> str:
    if group_id in memo:
        return memo[group_id]

    obj = objects.get(group_id)
    if obj is None:
        memo[group_id] = ""
        return ""

    parent_path = ""
    if group_id in parents:
        parent_path = group_path(parents[group_id], objects, parents, memo)

    part = "" if obj.fields.get("sourceTree") == "SOURCE_ROOT" else _path_part(obj.fields.get("path"))
    memo[group_id] = _join(parent_path, part)
    return memo[group_id]


def file_reference_paths(objects: dict[str, PBXObject]) -> dict[str, str]:
    parents = parent_map(objects)
    group_memo: dict[str, str] = {}
    refs: dict[str, str] = {}

    for object_id, obj in objects.items():
        if obj.isa != "PBXFileReference":
            continue
        raw_path = _path_part(obj.fields.get("path") or obj.fields.get("name"))
        if not raw_path.endswith(".swift"):
            continue

        source_tree = obj.fields.get("sourceTree")
        if source_tree == "SOURCE_ROOT":
            resolved = raw_path
        else:
            resolved = _join(group_path(parents.get(object_id, ""), objects, parents, group_memo), raw_path)

        # The project root is `fichero/`, so convert to repo-relative paths.
        refs[object_id] = _join("fichero", resolved)

    return refs


def target_sources_phase_ids(objects: dict[str, PBXObject]) -> list[str]:
    for obj in objects.values():
        if obj.isa != "PBXNativeTarget":
            continue
        if _unquote(obj.fields.get("name", "")) == TARGET_NAME:
            return obj.lists.get("buildPhases", [])
    # #4487: cannot parse my own committed input — BLIND (exit 2), not a crash.
    #
    # #4512: this block was indented INSIDE the loop, so the FIRST target whose
    # name was not "Fichero" tripped it — the check went blind the moment
    # FicheroIOSTests became the first PBXNativeTarget in the file. The parser
    # itself read the objectVersion-100 project fine (short numeric ids match
    # the same object grammar); the blindness was six spaces of indentation.
    # test_check_xcode_registration.py pins target-after-a-decoy so this exact
    # regression fires a test instead of blinding the gate.
    print(
        f"BLIND: PBXNativeTarget {TARGET_NAME!r} not found in {PROJECT_FILE} "
        "— the project parser resolved nothing (#4487)",
        file=sys.stderr,
    )
    raise SystemExit(2)


def registered_swift_files(objects: dict[str, PBXObject]) -> set[str]:
    refs = file_reference_paths(objects)
    source_phase_ids = target_sources_phase_ids(objects)
    build_file_ids: list[str] = []

    for phase_id in source_phase_ids:
        phase = objects.get(phase_id)
        if phase and phase.isa == "PBXSourcesBuildPhase":
            build_file_ids.extend(phase.lists.get("files", []))

    registered: set[str] = set()
    for build_file_id in build_file_ids:
        build_file = objects.get(build_file_id)
        if not build_file:
            continue
        match = OBJECT_ID_VALUE.match(build_file.fields.get("fileRef", ""))
        if match and match.group(1) in refs:
            registered.add(refs[match.group(1)])

    return registered


def disk_swift_files(swift_root: Path | None = None, root: Path | None = None) -> list[str]:
    swift_root = swift_root or SWIFT_ROOT
    root = root or ROOT
    return sorted(path.relative_to(root).as_posix() for path in swift_root.rglob("*.swift"))


def scan(
    project_file: Path | None = None,
    swift_root: Path | None = None,
    root: Path | None = None,
) -> dict[str, list[str]]:
    objects = parse_pbxproj(project_file)
    registered = registered_swift_files(objects)
    sync_prefixes = target_synchronized_prefixes(objects)
    found: dict[str, list[str]] = {}

    for rel in disk_swift_files(swift_root, root):
        if rel in registered:
            continue
        # Covered by a synchronized root group on the target (#3754) → compiled.
        if any(rel == prefix or rel.startswith(prefix + "/") for prefix in sync_prefixes):
            continue
        found[rel] = [f"not in {TARGET_NAME} target (no Sources entry, not under a synchronized root)"]

    return found


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    # #4487: ANY failure parsing the committed project file is BLIND (exit
    # 2) — "I could not read the registry I compare against" must never
    # surface as a crash (rc=1, reads as violation) or worse, a pass.
    try:
        objects = parse_pbxproj()
        found = scan()
        sync_roots = synchronized_roots(objects)
    except SystemExit:
        raise
    except Exception as exc:
        print(
            f"BLIND: could not parse {PROJECT_FILE} / enumerate sources "
            f"({type(exc).__name__}: {exc}) (#4487)",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    known = set(KNOWN_VIOLATIONS)

    if "--list" in sys.argv[1:]:
        print(f"Unregistered Swift files ({len(found)} files):\n")
        for rel, reasons in sorted(found.items()):
            tag = "known" if rel in known else "NEW"
            print(f"  [{tag}] {rel}")
            for reason in reasons:
                print(f"          - {reason}")
        if sync_roots:
            print("\nSynchronized roots outside the app-target scan:")
            for root in sync_roots:
                print(f"  fichero/{root}/")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    # #4487 scan floor: a dead disk enumeration -> 0 files -> 0 unregistered
    # -> pass. 884 on 2026-08-02.
    require_scan_floor(len(disk_swift_files()), 400, "Swift files on disk (884 on 2026-08-02)")
    print(f"Xcode-registration guardrail: scanned {SWIFT_ROOT.relative_to(ROOT)}")
    print(f"  {len(disk_swift_files())} Swift file(s) on disk; {len(found)} not registered in {TARGET_NAME}.")
    if sync_roots:
        print("  Synchronized roots outside this scan: " + ", ".join(f"fichero/{root}/" for root in sync_roots))

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entry now registered — drop from the set:")
        for rel in stale:
            print(f"      {rel}")

    if new:
        print(f"\n  ✗ {len(new)} Swift file(s) missing from the {TARGET_NAME} target:")
        for rel in new:
            for reason in found[rel]:
                print(f"      {rel}  ←  {reason}")
        print(
            "\nFix: run `ruby scripts/add-swift-file.rb <path>` for app source files, "
            f"or add a documented KNOWN_VIOLATIONS entry if intentionally orphaned. Rule: {RULE_DOC}."
        )
        return 1

    if stale:
        print("\n(KNOWN_VIOLATIONS has stale entries — clean them up when convenient.)")

    print("\n✓ No unregistered Swift files beyond the known backlog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
