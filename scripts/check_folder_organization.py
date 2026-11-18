#!/usr/bin/env python3
"""Folder-organization guardrail — flag Swift dumping-ground directories.

Rule (#1940/#1944): directories under `fichero/fichero` should not collect a
large number of unrelated Swift files directly in one folder. Put files in a
feature-specific subfolder when a directory becomes a catch-all.

This detector intentionally uses cheap static signals:
  1. More than MAX_DIRECT_SWIFT_FILES `.swift` files directly in a directory.
  2. Known mixed-concern directories that already need subdivision.

It does not try to prove architecture. `KNOWN_VIOLATIONS` is the current backlog:
the script exits 0 while only these known folders are found, and exits 1 if a new
dumping-ground folder appears. See agents/ROADMAP.md for the guardrail roadmap.

Rules added by spec: code-organization (code-org.folders.swift-test-mirror, code-org.folders.swift-view-local-state):
  3. A folder under Views/ with ONE .swift file and no subfolder: fold it into the feature that opens it.
  4. A folder under Views/ named for a layer (LAYER_NAMES): the layer is the top folder, not a feature.
  5. Test mirror: a test folder Tests/Unit/<platform>/<Layer>/<A>/<B>/ whose app folder fichero/<Layer>/<A>/<B>/
     does not exist (Layer: Views, Models, Services, App, Intents).
  6. View-local state: an @Observable or ObservableObject type declared under Views/<Feature>/ and read from a
     different Views/<Other>/ or from App/ belongs in Models/<Feature>/ (read by two features).
KNOWN_VIOLATIONS carries each folder's file count at baseline (--generate); a count ABOVE it fails.
KNOWN_TEST_ORPHANS and KNOWN_SHARED_STATE baseline rules 5 and 6. Rules 3-6 report only; they move nothing.

Usage:
    python3 scripts/check_folder_organization.py
    python3 scripts/check_folder_organization.py --list
    python3 scripts/check_folder_organization.py --generate     print the three baselines for today's tree
    python3 scripts/check_folder_organization.py --self-test    plant each kind of finding in a scratch tree
    python3 scripts/check_folder_organization.py -h
"""
from __future__ import annotations

import re
import sys
import tempfile

from _check_floor import require_scan_floor
from pathlib import Path
from _scan_files import scan_rglob

ROOT = Path(__file__).resolve().parent.parent
SWIFT_ROOT = ROOT / "fichero" / "fichero"
TEST_ROOT = ROOT / "fichero" / "Tests" / "Unit"
LAYER_NAMES = frozenset({"Models", "Services", "Views", "Helpers", "Utils", "Misc", "Common", "Shared"})
MIRROR_LAYERS = ("Views", "Models", "Services", "App", "Intents")
RULE_DOC = "agents/ROADMAP.md"
MAX_DIRECT_SWIFT_FILES = 18

MIXED_CONCERN_DIRS: dict[str, str] = {
    "Views/Library": "mixes browser, picker, inspector, viewer, and workspace surfaces",
    "Views/Sidebar": "mixes sidebar state, rows, drag/drop, modes, and commands",
}

SUGGESTED_SUBFOLDERS: dict[str, str] = {
    "Views/Library": "Artifacts/, PDFReading/, QuickLook/, KnowledgeGraph/, Pickers/, Tools/, Thumbnails/",
}

# Current folder-organization backlog: folder -> (file count at baseline 2026-11-15, note). A count above it fails; drop
# entries as directories are split. Regenerate with --generate only to LOWER counts.
KNOWN_VIOLATIONS: dict[str, tuple[int, str]] = {
    'Models': (355, '#1944 — 53 Swift files directly in Models'),
    'Services': (220, '#1944 — 60 Swift files directly in Services'),
    'Views/Auth': (1, 'baseline 2026-11-15'),
    'Views/Components': (28, '#1944 sibling — 19 files; grew by DragPreviewLabel (2026-08-09)'),
    'Views/Inspector/Model': (1, 'baseline 2026-11-15'),
    'Views/Inspector/Source/Bulk': (1, 'baseline 2026-11-15'),
    'Views/Inspector/Source/Tries': (1, 'baseline 2026-11-15'),
    'Views/Library': (49, '#1944 — 42 Swift files directly; mixed Library concerns'),
    'Views/Library/Bookmarks': (1, 'baseline 2026-11-15'),
    'Views/Library/Export': (1, 'baseline 2026-11-15'),
    'Views/Library/Notes': (1, 'baseline 2026-11-15'),
    'Views/Library/ViewModes/Dataset/Calendar': (1, 'baseline 2026-11-15'),
    'Views/Library/ViewModes/Dataset/Cards': (1, 'baseline 2026-11-15'),
    'Views/Library/ViewModes/Dataset/Grid': (1, 'baseline 2026-11-15'),
    'Views/Library/ViewModes/Dataset/Map': (1, 'baseline 2026-11-15'),
    'Views/Library/ViewModes/Dataset/Timeline': (1, 'baseline 2026-11-15'),
    'Views/Library/ViewModes/List': (1, 'baseline 2026-11-15'),
    'Views/Models': (2, 'baseline 2026-11-15'),
    'Views/Reader/Disagreement': (1, 'baseline 2026-11-15'),
    'Views/SPARQLConsole': (1, 'baseline 2026-11-15'),
    'Views/Settings/History': (1, 'baseline 2026-11-15'),
    'Views/Settings/Knowledge': (1, 'baseline 2026-11-15'),
    'Views/Settings/Sharing/Access': (1, 'baseline 2026-11-15'),
    'Views/Settings/Snapshots': (1, 'baseline 2026-11-15'),
    'Views/Settings/Tools': (1, 'baseline 2026-11-15'),
    'Views/Shell/ContentView': (35, '#1944 sibling — 20 files; grew by ShellPrimarySelection + SheetLibraryEnvironment-adjacent splits'),
    'Views/Shell/Toolbar': (33, '2026-08-31 — 20 files: the workflow bar grew ChainRow/Context splits (file_length budget); the WorkflowBar* family wants its own subfolder, queued with the toolbar reorg'),
    'Views/Sidebar': (2, '#1944 — 27 Swift files directly; mixed Sidebar concerns'),
    'Views/Sidebar/ItemRow': (22, '#1944 sibling — 20 files; grew by the preview catalog + drag/drop splits'),
}
KNOWN_TEST_ORPHANS: dict[str, int] = {
    'general/Models/ActivityPane': 13,
    'general/Views/Source': 12,
}
KNOWN_SHARED_STATE: dict[str, str] = {
    'Views/Activity/ActivityViewHelpers.swift::ActivityWindowSelectionState': 'App/Menus/FocusedCommands/FocusedCommandButtons+Recipe.swift',
    'Views/Inspector/Artifacts/FocusedArtifact.swift::FocusedArtifact': 'Views/Shell/ContentView/Layout/ContentView+WorkflowScope.swift',
    'Views/Inspector/FocusedDocument.swift::FocusedDocument': 'Views/Shell/ContentView/ContentView.swift',
    'Views/Inspector/FocusedRegionSelection.swift::FocusedRegionSelection': 'Views/Shell/ContentView/Layout/ContentView+WorkflowScope.swift',
    'Views/Inspector/Knowledge/KnowledgeGraphSupport.swift::ActiveSurfaceState': 'Views/Reader/Page/ReadingPaneView.swift',
    'Views/Inspector/Knowledge/KnowledgeGraphSupport.swift::ClaimSourceNavigationState': 'Views/Reader/Page/ReadingPaneView.swift',
    'Views/Inspector/Knowledge/KnowledgeGraphSupport.swift::EntitySearchState': 'Views/Shell/ContentView/ContentView.swift',
    'Views/Inspector/Notes/Annotations/FocusedAnnotation.swift::FocusedAnnotation': 'Views/Reader/Page/ReadingPaneView.swift',
    'Views/Inspector/Notes/FocusedNote.swift::FocusedNote': 'Views/Library/Notes/NoteListView.swift',
    'Views/Library/LibraryToolbarState.swift::LibraryToolbarState': 'Views/Shell/Toolbar/LibraryToolbarPolicy.swift',
    'Views/Library/Workspace/WorkspaceItemPicker.swift::WorkspacePickerService': 'Views/Components/NodeClassPicker.swift',
    'Views/Preview/ImageEditor/ImageEditorModel.swift::ImageEditorModel': 'Views/Inspector/Document/DocumentInspector+Sections.swift',
    'Views/Reader/Knowledge/DocumentKGSurfaceTypes.swift::DocumentScrollSyncState': 'Views/Shell/ContentView/ContentView.swift',
    'Views/Reader/ReaderPageActivationState.swift::ReaderPageActivationState': 'Views/Shell/ContentView/ContentView.swift',
    'Views/Shell/PaneHead/PreviewPaneChrome.swift::PreviewPaneChrome': 'Views/Preview/PDFViewer/PDFPageWithToolbar.swift',
    'Views/Shell/WindowLayout/WindowWorkspaceStore.swift::WindowWorkspaceStore': 'App/Menus/WorkspacesMenuBody.swift',
    'Views/Sidebar/State/SidebarStateManagers.swift::SidebarSelectionState': 'Views/Inspector/Project/ProjectInspector.swift',
    'Views/Workflow/Execution/WorkflowRunProviderCache.swift::WorkflowRunProviderCache': 'Views/Sidebar/ItemRow/SidebarItemRow.swift',
}


def direct_swift_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix == ".swift")


def scan() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for directory in sorted(p for p in scan_rglob(SWIFT_ROOT, "*") if p.is_dir()):
        rel = directory.relative_to(SWIFT_ROOT).as_posix()
        files = direct_swift_files(directory)
        reasons: list[str] = []
        if len(files) > MAX_DIRECT_SWIFT_FILES:
            reasons.append(
                f"{len(files)} Swift files directly in one directory "
                f"(limit: {MAX_DIRECT_SWIFT_FILES})"
            )
        if rel in MIXED_CONCERN_DIRS:
            reasons.append(MIXED_CONCERN_DIRS[rel])
        if rel.startswith("Views/"):
            has_subfolder = any(p.is_dir() and not p.name.startswith(".") for p in directory.iterdir())
            if len(files) == 1 and not has_subfolder:
                reasons.append("one Swift file and no subfolder: fold it into the feature that opens it")
            if directory.name in LAYER_NAMES:
                reasons.append(f"a folder named for a layer ({directory.name}): name it for the feature")
        if reasons:
            found[rel] = reasons
    return found


def _test_dirs() -> list[Path]:
    return sorted({p.parent for p in scan_rglob(TEST_ROOT, "*.swift", optional=True)})


def scan_test_mirror() -> dict[str, int]:
    """{<platform>/<Layer>/<A>/<B>: test files} for each test folder whose app folder does not exist."""
    found: dict[str, int] = {}
    for directory in _test_dirs():
        parts = directory.relative_to(TEST_ROOT).parts  # <platform>/<Layer>/<A>/...
        if len(parts) < 3 or parts[1] not in MIRROR_LAYERS:
            continue
        if not (SWIFT_ROOT.joinpath(*parts[1:])).is_dir():
            found["/".join(parts)] = len(direct_swift_files(directory))
    return found


_OBSERVABLE = re.compile(
    r"@Observable\b(?:\s|@\w+(?:\([^)]*\))?|\b(?:public|internal|final|private|fileprivate|open)\b)*\b(?:class|struct)\s+([A-Za-z_]\w*)"
    r"|\b(?:class|struct)\s+([A-Za-z_]\w*)\s*(?:<[^>{]*>)?\s*:[^{]*\bObservableObject\b"
)
_IDENT = re.compile(r"[A-Za-z_]\w*")


def scan_shared_state() -> dict[str, str]:
    """{<declaring file>::<Type>: the other place that reads it} for view-local state a second feature reads."""
    from check_swift_one_type_per_file import strip_comments_and_strings

    declared: dict[str, tuple[str, str]] = {}  # type name -> (file, feature)
    idents: dict[str, set[str]] = {}
    for path in scan_rglob(SWIFT_ROOT, "*.swift"):
        rel = path.relative_to(SWIFT_ROOT).as_posix()
        code = strip_comments_and_strings(path.read_text(encoding="utf-8", errors="replace"))
        idents[rel] = set(_IDENT.findall(code))
        parts = rel.split("/")
        if parts[0] == "Views" and len(parts) > 2:
            for m in _OBSERVABLE.finditer(code):
                declared.setdefault(m.group(1) or m.group(2), (rel, parts[1]))
    found: dict[str, str] = {}
    for name, (decl_file, feature) in sorted(declared.items()):
        for rel, names in idents.items():
            if rel == decl_file or name not in names:
                continue
            parts = rel.split("/")
            other = parts[0] == "App" or (parts[0] == "Views" and len(parts) > 2 and parts[1] != feature)
            if other:
                found[f"{decl_file}::{name}"] = rel
                break
    return found


def print_list(found: dict[str, list[str]]) -> None:
    print(f"Folder-organization offenders ({len(found)} directories):\n")
    for rel, reasons in sorted(found.items(), key=lambda item: (-len(direct_swift_files(SWIFT_ROOT / item[0])), item[0])):
        tag = "known" if rel in KNOWN_VIOLATIONS else "NEW"
        print(f"  [{tag}] {rel}")
        for reason in reasons:
            print(f"          - {reason}")
        if rel in SUGGESTED_SUBFOLDERS:
            print(f"          - suggested subfolders: {SUGGESTED_SUBFOLDERS[rel]}")
        print(f"          - move new files into a specific subfolder under {rel}")


def file_count(rel: str) -> int:
    return len(direct_swift_files(SWIFT_ROOT / rel))


def over_baseline(found: dict[str, list[str]]) -> dict[str, str]:
    """{folder: why} for each found folder that is new, or holds more files than its baseline count."""
    out: dict[str, str] = {}
    for rel in sorted(found):
        if rel not in KNOWN_VIOLATIONS:
            out[rel] = "new"
        elif file_count(rel) > KNOWN_VIOLATIONS[rel][0]:
            out[rel] = f"{file_count(rel)} files, baseline {KNOWN_VIOLATIONS[rel][0]}"
    return out


def generate() -> None:
    found = scan()
    print("KNOWN_VIOLATIONS: dict[str, tuple[int, str]] = {")
    for rel in sorted(found):
        note = KNOWN_VIOLATIONS.get(rel, (0, "baseline 2026-11-15"))[1]
        print(f"    {rel!r}: ({file_count(rel)}, {note!r}),")
    print("}\nKNOWN_TEST_ORPHANS: dict[str, int] = {")
    for rel, n in sorted(scan_test_mirror().items()):
        print(f"    {rel!r}: {n},")
    print("}\nKNOWN_SHARED_STATE: dict[str, str] = {")
    for key, reader in sorted(scan_shared_state().items()):
        print(f"    {key!r}: {reader!r},")
    print("}")


def _plant(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def _self_test() -> int:
    global SWIFT_ROOT, TEST_ROOT
    saved = SWIFT_ROOT, TEST_ROOT
    try:
        with tempfile.TemporaryDirectory() as tmp:
            SWIFT_ROOT = Path(tmp) / "fichero" / "fichero"
            TEST_ROOT = Path(tmp) / "fichero" / "Tests" / "Unit"
            _plant(SWIFT_ROOT, {
                "Views/Alpha/AView.swift": "struct AView {}\n",  # lone file in a leaf folder
                "Views/Beta/BView.swift": "struct BView {}\n",
                "Views/Beta/BState.swift": "@Observable final class BState {}\n",
                "Views/Beta/Inner/InnerView.swift": "struct InnerView {}\n",
                "Views/Beta/Inner/InnerRow.swift": "struct InnerRow {}\n",
                "Views/Gamma/GView.swift": "struct GView { let s = BState() }\n",
                "Views/Gamma/GRow.swift": "struct GRow {}\n",
                "Views/Gamma/Models/GModel.swift": "struct GModel {}\n",
                "Views/Gamma/Models/GModel2.swift": "struct GModel2 {}\n",
                "Views/Delta/DView.swift": "struct DView {}\n",
                "Views/Delta/DRow.swift": "struct DRow {}\n",
                "Views/Delta/DState.swift": "final class DState: ObservableObject {}\n",
                "Models/Thing/Thing.swift": "struct Thing {}\n",
            })
            _plant(TEST_ROOT, {
                "general/Views/Beta/BTests.swift": "x\n",
                "general/Views/Missing/MTests.swift": "x\n",
                "general/Views/Beta/Gone/GTests.swift": "x\n",
                "general/Models/Thing/ThingTests.swift": "x\n",
                "mac/MacTests.swift": "x\n",
            })
            found = scan()
            problems = []
            if not any("one Swift file" in r for r in found.get("Views/Alpha", [])):
                problems.append("a lone-file folder under Views/ was not found")
            if not any("layer" in r for r in found.get("Views/Gamma/Models", [])):
                problems.append("a layer-named folder under Views/ was not found")
            if "Views/Beta/Inner" in found or "Views/Delta" in found:
                problems.append("a two-file folder was reported")
            if set(scan_test_mirror()) != {"general/Views/Missing", "general/Views/Beta/Gone"}:
                problems.append(f"test mirror found {sorted(scan_test_mirror())}")
            shared = scan_shared_state()
            if set(shared) != {"Views/Beta/BState.swift::BState"}:
                problems.append(f"shared state found {sorted(shared)} (own-feature DState must pass, BState read by Gamma must not)")
            if any(file_count(r) > 3 for r in found):
                problems.append("file counts are wrong")
    finally:
        SWIFT_ROOT, TEST_ROOT = saved
    if problems:
        print("self-test FAILED: " + "; ".join(problems), file=sys.stderr)
        return 1
    print("self-test ok")
    return 0


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0
    if "--self-test" in sys.argv[1:]:
        return _self_test()

    found = scan()
    known = set(KNOWN_VIOLATIONS)
    # #4487 scan floor: 884 app Swift files on 2026-08-02.
    require_scan_floor(
        sum(1 for _ in scan_rglob((ROOT / "fichero" / "fichero"), "*.swift")), 400,
        "app Swift files (884 on 2026-08-02)",
    )

    if "--generate" in sys.argv[1:]:
        generate()
        return 0

    orphans = scan_test_mirror()
    shared = scan_shared_state()
    if "--list" in sys.argv[1:]:
        print_list(found)
        print(f"\nTest folders with no app folder ({len(orphans)}):")
        for rel, n in sorted(orphans.items()):
            print(f"  [{'known' if rel in KNOWN_TEST_ORPHANS else 'NEW'}] Tests/Unit/{rel} ({n} files)")
        print(f"\nView-local state read by a second feature ({len(shared)}):")
        for key, reader in sorted(shared.items()):
            path, name = key.split("::")
            feature = path.split("/")[1]
            print(f"  [{'known' if key in KNOWN_SHARED_STATE else 'NEW'}] {name} ({path}) -> Models/{feature}/ (read by two features: {reader})")
        return 0

    new = over_baseline(found)
    stale = sorted(known - set(found))
    new_orphans = sorted(r for r, n in orphans.items() if n > KNOWN_TEST_ORPHANS.get(r, 0))
    new_shared = sorted(set(shared) - set(KNOWN_SHARED_STATE))

    print(f"Folder-organization guardrail: scanned {SWIFT_ROOT.relative_to(ROOT)}")
    print(f"  {len(found)} dumping-ground directorie(s); {len(known)} known backlog entries.")
    print(f"  {len(orphans)} test folder(s) with no app folder; {len(shared)} view-local state type(s) read by a second feature.")

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entry now CLEAN — drop from the set:")
        for rel in stale:
            print(f"      {rel}")

    failed = False
    if new:
        failed = True
        print(f"\n  ✗ {len(new)} directorie(s) new or above their baseline count:")
        for rel, why in new.items():
            for reason in found[rel]:
                print(f"      {rel}  ←  {reason}  [{why}]")
        print(
            "\nFix: move the added Swift file(s) into a focused subfolder, or split the "
            f"directory as part of the organization roadmap. Rule: {RULE_DOC}."
        )
    if new_orphans:
        failed = True
        print(f"\n  ✗ {len(new_orphans)} test folder(s) with no app folder to mirror:")
        for rel in new_orphans:
            print(f"      Tests/Unit/{rel}  →  fichero/fichero/{rel.split('/', 1)[1]}/ (the test folder mirrors an app folder)")
    if new_shared:
        failed = True
        print(f"\n  ✗ {len(new_shared)} view-local state type(s) read by a second feature:")
        for key in new_shared:
            path, name = key.split("::")
            print(f"      {name} ({path})  →  Models/{path.split('/')[1]}/ (read by two features: {shared[key]})")
    if failed:
        return 1

    if stale:
        print("\n(KNOWN_VIOLATIONS has stale entries — clean them up when convenient.)")

    print("\n✓ No folder-organization offenders beyond the known backlog.")
    return 0


def _require_scan_roots_4382(*roots):
    """#4382: a guardrail must know when it has gone blind, and say so.

    A missing scan root means "I could not check" (exit 2) -- never a silent
    exit 0. Distinct from exit 1 ("I checked and found violations"), so a
    moved or renamed directory can never disable this guardrail while the
    gate stays green.
    """
    import sys as _sys

    flat = []
    for root in roots:
        flat.extend(root if isinstance(root, (tuple, list)) else [root])
    missing = [str(r) for r in flat if not r.exists()]
    if missing:
        print(
            f"{__file__.rsplit('/', 1)[-1]}: BLIND -- scan root(s) missing: "
            + ", ".join(missing)
            + " (the tree moved; update this guardrail's paths)",
            file=_sys.stderr,
        )
        _sys.exit(2)


if __name__ == "__main__":
    _require_scan_roots_4382(SWIFT_ROOT)
    raise SystemExit(main())
