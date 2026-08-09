#!/usr/bin/env python3
"""Scene-granularity environment-injection guardrail (#4513 / #4448).

SwiftUI's environment flows down ONE view tree. It does NOT cross a Scene
boundary: objects injected into the main `WindowGroup` are invisible to a
separate `Window`, `WindowGroup`, or `Settings` scene. A view that reads a
library-scoped service with a NON-optional `@Environment(T.self)` and is
mounted under a scene that never injected `T` does not degrade — it TRAPS the
moment its body is constructed.

That is the #4513 crash class, twice: `ActivityDetailWindow` (a new `Window`
scene reaching `ArtifactsInspectorPane`, which reads `ArtifactService`) and the
library column's `AnyView` host. Both were "the environment obviously flows
here" reasoning applied across a boundary where it does not.

TWO RULES, both at scene granularity.

RULE 1 — the static walk. For every scene declared in an App file, resolve the
view types its closure mounts (App-file helper functions inlined), walk the
types THOSE construct bounded to `MAX_DEPTH` levels and pruned wherever a type
re-injects the service, collect every CANONICAL library-scoped service read
non-optionally (`@Environment(ArtifactService.self) private var x`; an `X?`
read is a deliberate opt-out), and assert the scene injects each one — unless
the scene's root reaches `LibraryWorkspaceRoot`, which injects the whole list.

RULE 2 — the declared-contract tripwire. Every scene NOT rooted in
`LibraryWorkspaceRoot` must have an entry in `DETACHED_SCENES` recording what
it injects and why that suffices. A new detached scene fails until someone
writes that down; a contract for a scene that no longer exists is reported too.

The canonical list is DERIVED, never hand-copied: it is exactly the
`.environment(library.X)` calls in `LibraryWorkspaceRoot.swift`, resolved to
types through `LibraryManager.LibraryReference`'s stored properties. Adding a
service there automatically widens this check.

WHAT THIS CANNOT DO — measured, not assumed. Rule 1 would NOT have caught the
shipped `ActivityDetailWindow` crash: from that scene root there is no
construction-edge path to `ArtifactsInspectorPane` at ANY depth, because the
pane is reached through erased/indirect edges no static walk sees. Full
view-graph reachability is not statically decidable. Rule 1 catches the
straightforward shape (a scene root whose visible subtree reads a service);
RULE 2 is what actually covers the shipped class, by refusing to let a new
scene exist without a human statement of its environment contract.

Every waiver in `KNOWN_GAPS` must state WHY the reader is safe.

Usage:
    scripts/check_scene_environment_injection.py
    scripts/check_scene_environment_injection.py --list
    scripts/check_scene_environment_injection.py --self-test
    scripts/check_scene_environment_injection.py --help
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from _check_floor import require_scan_floor

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "fichero" / "fichero"
WORKSPACE_ROOT_FILE = APP_DIR / "Views" / "Library" / "Workspace" / "LibraryWorkspaceRoot.swift"
LIBRARY_MANAGER_FILE = APP_DIR / "Models" / "LibraryManager.swift"
SERVICE_ENV_HELPER_FILE = APP_DIR / "Views" / "Shell" / "LibraryServiceEnvironment.swift"
RULE_DOC = "#4513"

# How far below a scene root to look for readers. Deeper is more truthful and
# also more false-positive prone; 3 covers the two shipped crashes
# (scene -> window root -> pane -> reader) without drowning the signal.
MAX_DEPTH = 3

# Scene root views that reach `LibraryWorkspaceRoot` and therefore inherit the
# entire canonical service list. Detected structurally (see
# `reaches_workspace_root`); this set is only the seed for that walk.
WORKSPACE_ROOT_TYPE = "LibraryWorkspaceRoot"

# Waivers, keyed "<scene> needs <Service>". Each entry states WHY it is safe.
KNOWN_GAPS: dict[str, str] = {}

# RULE 2 — the declared-contract tripwire. Every scene that is NOT rooted in
# `LibraryWorkspaceRoot` must be listed here with the environment contract its
# author reasoned about. A NEW `Window`/`WindowGroup`/`Settings` scene fails
# this check until someone writes that line down, which is the whole point:
# both #4513 crashes came from adding a scene and assuming the environment
# would follow it. Rule 1 (the static walk below) cannot substitute — the
# ActivityDetailWindow reader was reached through an `AnyView`/erased edge no
# static walk sees, which is exactly why the tripwire exists.
DETACHED_SCENES: dict[str, str] = {
    "about (Window)":
        "AboutView is chrome only — version/credits from Bundle; injects appState for the build tier.",
    "feature-tier-legend (Window)":
        "FeatureTierLegendWindow reads FeatureManager.shared directly; no library scope.",
    "artifact-detail (WindowGroup)":
        "Read-only tear-off; follows FocusedArtifact.shared's resolved snapshot (#2003).",
    "citation-detail (WindowGroup)":
        "Read-only tear-off; follows FocusedCitation.shared's resolved snapshot (#2004).",
    "annotation-detail (WindowGroup)":
        "Read-only tear-off; follows the shared annotation focus holder (#2010).",
    "note-detail (WindowGroup)":
        "Read-only tear-off; follows the shared note focus holder (#2011).",
    "document-detail (WindowGroup)":
        "Injects libraryManager + the claim/KG focus states; resolves its own library services from those.",
    "Activity (Window)":
        "Injects libraryManager + the app execution observer; resolves the active library's stores itself.",
    "Activity Detail (Window)":
        "Injects libraryManager, the execution observer, and the per-library stores its panes read "
        "(activityStore/apiClient/documentStore/workflowExecutionStore/artifactService — #4513).",
    "Settings (Settings)":
        "Separate scene by construction; re-injects appState, backendService, libraryManager, "
        "viewSettings and FeatureManager.shared (see the comment on the scene).",
}

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//.*$", re.MULTILINE)

_SCENE_DECL = re.compile(r"\b(WindowGroup|Window|Settings|DocumentGroup|MenuBarExtra)\b")
# `.environment(library.artifactService)`, `.environment(libraryManager)`,
# `.environment(FeatureManager.shared)` — capture the whole argument.
_ENVIRONMENT_CALL = re.compile(r"\.environment\(\s*([^)\n]+?)\s*\)")
# `let artifactService: ArtifactService` inside LibraryReference.
_STORED_PROPERTY = re.compile(r"^\s*(?:let|var)\s+(\w+)\s*:\s*([A-Z]\w*)", re.MULTILINE)
# `@Environment(ArtifactService.self) private var artifactService` — a trailing
# `?` on the declared type is the deliberate optional opt-out.
_ENVIRONMENT_READ = re.compile(
    r"@Environment\(\s*([A-Z]\w*)\.self\s*\)\s*(?:private\s+|internal\s+|public\s+)*var\s+\w+"
    r"(?:\s*:\s*([^\n=]+))?"
)
_TYPE_DECL = re.compile(
    r"^\s*(?:public\s+|internal\s+|private\s+|fileprivate\s+|final\s+)*(?:struct|class|enum|extension)\s+(\w+)",
    re.MULTILINE,
)


def strip_comments(text: str) -> str:
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", text))


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _balanced_from(text: str, open_index: int) -> str:
    """Source inside the braces/parens starting at `open_index`."""
    opener = text[open_index]
    closer = {"{": "}", "(": ")"}[opener]
    depth = 0
    for idx in range(open_index, len(text)):
        ch = text[idx]
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : idx]
    return text[open_index + 1 :]


def library_property_types(manager_file: Path = LIBRARY_MANAGER_FILE) -> dict[str, str]:
    """`{"artifactService": "ArtifactService"}` from LibraryReference's properties.

    Read non-optionally on purpose: a missing/renamed file must raise, not
    quietly yield an empty map that makes the canonical list empty (#4487).
    """
    text = strip_comments(manager_file.read_text(encoding="utf-8"))
    types: dict[str, str] = {}
    for name, type_name in _STORED_PROPERTY.findall(text):
        types.setdefault(name, type_name)
    # `lazy var entityStore: EntityStore = EntityStore(...)` is matched by the
    # same pattern; `@ObservationIgnored lazy var` prefixes do not interfere.
    for match in re.finditer(r"lazy\s+var\s+(\w+)\s*:\s*([A-Z]\w*)", text):
        types.setdefault(match.group(1), match.group(2))
    return types


def canonical_services(
    workspace_file: Path = WORKSPACE_ROOT_FILE,
    manager_file: Path = LIBRARY_MANAGER_FILE,
) -> set[str]:
    """The library-scoped service/store TYPES `LibraryWorkspaceRoot` injects.

    Derived, not hand-listed: adding `.environment(library.newThing)` there
    widens this guardrail on the next run.
    """
    property_types = library_property_types(manager_file)
    text = strip_comments(workspace_file.read_text(encoding="utf-8"))
    services: set[str] = set()
    for arg in _ENVIRONMENT_CALL.findall(text):
        match = re.fullmatch(r"library\.(\w+)", arg.strip())
        if match and match.group(1) in property_types:
            services.add(property_types[match.group(1)])
    return services


def view_files(app_dir: Path = APP_DIR) -> dict[str, tuple[Path, str]]:
    """`{TypeName: (file, own source)}` for every type declared in the app source.

    TYPE granularity, not file granularity. `ArtifactsInspectorPane` and
    `ArtifactDetailWindow` share one file; a per-file scan credits the detail
    window with the pane's `@Environment(ArtifactService.self)` and reports a
    crash that cannot happen (it mounts `ArtifactDetailView`, not the pane).
    Extensions are folded into the type they extend, since a view's `body` is
    routinely split across `Type+Feature.swift` files here.
    """
    index: dict[str, tuple[Path, str]] = {}
    for path in sorted(app_dir.rglob("*.swift")):
        if ".build" in path.parts:
            continue
        try:
            text = strip_comments(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        for match in _TYPE_DECL.finditer(text):
            name = match.group(1)
            brace = text.find("{", match.end())
            if brace == -1:
                continue
            body = _balanced_from(text, brace)
            if name in index:
                index[name] = (index[name][0], index[name][1] + "\n" + body)
            else:
                index[name] = (path, body)
    return index


def _read_text(path: Path) -> str:
    try:
        return strip_comments(path.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return ""


def non_optional_reads(text: str, services: set[str]) -> set[str]:
    """Canonical services this source reads with a NON-optional @Environment."""
    found: set[str] = set()
    for type_name, declared in _ENVIRONMENT_READ.findall(text):
        if type_name not in services:
            continue
        if declared and declared.strip().rstrip("!").endswith("?"):
            continue  # optional read — a deliberate "may be absent" opt-out
        found.add(type_name)
    return found


def injected_types(text: str, services: set[str], property_types: dict[str, str]) -> set[str]:
    """Canonical services a chunk of source injects via `.environment(...)`."""
    injected: set[str] = set()
    for arg in _ENVIRONMENT_CALL.findall(text):
        arg = arg.strip()
        bare = arg.split(".")[-1]
        for candidate in (property_types.get(bare), arg.split(".")[0], bare):
            if candidate in services:
                injected.add(candidate)
                break
    return injected


def _referenced_types(text: str, index: dict[str, tuple[Path, str]]) -> set[str]:
    """App-declared view types this source CONSTRUCTS — the edges of the walk.

    Construction (`SomePane(...)`), not every capitalized identifier: a
    name-anywhere edge treats a type annotation, a static lookup and an enum
    case as mounts, which fanned the walk out to most of the app and produced
    48 findings, nearly all false. `#Preview` blocks are excluded — a preview
    mounts things the shipping tree never does, and supplies its own
    environment.
    """
    text = _strip_previews(text)
    return {name for name in set(re.findall(r"\b([A-Z]\w+)\s*\(", text)) if name in index}


def _strip_previews(text: str) -> str:
    """Drop `#Preview { … }` blocks — they are not part of the shipping tree."""
    out = []
    cursor = 0
    for match in re.finditer(r"#Preview\b[^{\n]*", text):
        if match.start() < cursor:
            continue
        brace = text.find("{", match.end() - 1)
        if brace == -1:
            continue
        body = _balanced_from(text, brace)
        out.append(text[cursor : match.start()])
        cursor = brace + len(body) + 2
    out.append(text[cursor:])
    return "".join(out)


def reaches_workspace_root(
    root_type: str, index: dict[str, tuple[Path, str]], depth: int = MAX_DEPTH
) -> bool:
    """Whether `root_type`'s subtree mounts `LibraryWorkspaceRoot`.

    Such a scene inherits the whole canonical list and needs no per-service
    injection of its own.
    """
    seen: set[str] = set()
    frontier = {root_type}
    for _ in range(depth + 1):
        nxt: set[str] = set()
        for name in frontier:
            if name == WORKSPACE_ROOT_TYPE:
                return True
            if name in seen or name not in index:
                continue
            seen.add(name)
            nxt |= _referenced_types(index[name][1], index)
        frontier = nxt - seen
        if not frontier:
            break
    return False


def required_services(
    root_type: str,
    index: dict[str, tuple[Path, str]],
    services: set[str],
    property_types: dict[str, str],
    depth: int = MAX_DEPTH,
) -> set[str]:
    """Canonical services read below `root_type`, pruned where re-injected.

    A file that injects service `T` makes its whole subtree self-sufficient for
    `T`, so `T` stops propagating up from beyond it.
    """
    required: set[str] = set()
    seen: set[str] = set()
    frontier = {(root_type, frozenset())}
    for _ in range(depth + 1):
        nxt: set[tuple[str, frozenset]] = set()
        for name, satisfied in frontier:
            if name in seen or name not in index:
                continue
            seen.add(name)
            text = index[name][1]
            required |= non_optional_reads(text, services) - satisfied
            here = satisfied | injected_types(text, services, property_types)
            for child in _referenced_types(text, index) - seen:
                nxt.add((child, frozenset(here)))
        frontier = nxt
        if not frontier:
            break
    return required


def app_files(app_dir: Path = APP_DIR) -> list[Path]:
    """Files declaring a SwiftUI `App` — where every Scene must be declared."""
    found = []
    for path in sorted(app_dir.rglob("*.swift")):
        text = _read_text(path)
        if re.search(r"struct\s+\w+\s*:\s*App\b", text) and "some Scene" in text:
            found.append(path)
    return found


def scenes(path: Path) -> list[tuple[str, str, str]]:
    """`[(scene label, kind, content-closure source)]` declared in an App file."""
    text = _read_text(path)
    found: list[tuple[str, str, str]] = []
    for match in _SCENE_DECL.finditer(text):
        kind = match.group(1)
        cursor = match.end()
        label = kind
        if cursor < len(text) and text[cursor] == "(":
            args = _balanced_from(text, cursor)
            id_match = re.search(r'id:\s*"([^"]+)"', args) or re.search(r'"([^"]+)"', args)
            if id_match:
                label = id_match.group(1)
            cursor += len(args) + 2
        brace = text.find("{", cursor)
        if brace == -1 or text[cursor:brace].strip() not in ("", ")"):
            continue
        body = _balanced_from(text, brace)
        found.append((f"{label} ({kind})", kind, body))
    return found


def app_helpers(app_text: str) -> dict[str, str]:
    """`{helperName: body}` for the App type's own view-building helpers.

    `WindowGroup("Fichero", id: "main") { libraryWindowRoot(seed: nil) }` names
    no view type at all. Without inlining these the scene root resolves to
    whatever type happens to appear next in the closure (a `.sheet` content, in
    the real app) — the wrong tree entirely.
    """
    helpers: dict[str, str] = {}
    for match in re.finditer(r"\bfunc\s+(\w+)\s*\(", app_text):
        paren = app_text.index("(", match.end() - 1)
        after = paren + len(_balanced_from(app_text, paren)) + 2
        brace = app_text.find("{", after)
        if brace == -1 or "\n\n" in app_text[after:brace]:
            continue
        helpers[match.group(1)] = _balanced_from(app_text, brace)
    return helpers


def scene_root_types(
    body: str, index: dict[str, tuple[Path, str]], helpers: dict[str, str], depth: int = 3
) -> set[str]:
    """Every app-declared view type a scene's closure mounts, helpers inlined."""
    text = body
    for _ in range(depth):
        expanded = text
        for name, helper_body in helpers.items():
            if re.search(rf"\b{name}\s*\(", expanded):
                expanded += "\n" + helper_body
        if expanded == text:
            break
        text = expanded
    return {name for name in re.findall(r"\b([A-Z]\w+)\s*\(", text) if name in index}


def scan(
    app_dir: Path = APP_DIR,
    workspace_file: Path = WORKSPACE_ROOT_FILE,
    manager_file: Path = LIBRARY_MANAGER_FILE,
    detached: dict[str, str] | None = None,
    helper_env_file: Path = SERVICE_ENV_HELPER_FILE,
) -> tuple[dict[str, str], int]:
    """`({"<scene> needs <Service>": detail}, scenes examined)`."""
    services = canonical_services(workspace_file, manager_file)
    property_types = library_property_types(manager_file)
    index = view_files(app_dir)
    declared = DETACHED_SCENES if detached is None else detached

    found: dict[str, str] = {}
    examined = 0
    seen_detached: set[str] = set()
    for path in app_files(app_dir):
        helpers = app_helpers(_read_text(path))
        for label, _kind, body in scenes(path):
            examined += 1
            roots = scene_root_types(body, index, helpers)
            if not roots:
                found[f"{label} needs a resolvable root view"] = (
                    f"{_rel(path)} — the scene closure mounts no app-declared view type, so "
                    "its environment contract cannot be checked"
                )
                continue
            if any(reaches_workspace_root(root, index) for root in roots):
                continue  # inherits the canonical list from LibraryWorkspaceRoot
            seen_detached.add(label)
            if label not in declared:
                found[f"{label} needs a declared environment contract"] = (
                    f"{_rel(path)} — a scene outside the LibraryWorkspaceRoot tree inherits "
                    "NOTHING; add it to DETACHED_SCENES stating what it injects and why that "
                    "is sufficient"
                )
            # Injections are credited over the HELPER-EXPANDED body, the
            # same text the root walk sees — a scene whose closure calls a
            # same-file `documentDetailSceneRoot()` helper injects whatever
            # that helper injects (2026-08-09; extracting the scene body into
            # a helper for the type_body ratchet must not fail this check).
            expanded_body = body
            for name, helper_body in helpers.items():
                if re.search(rf"\b{name}\s*\(", body):
                    expanded_body += "\n" + helper_body
            injected = injected_types(expanded_body, services, property_types)
            if ".libraryServiceEnvironment(" in expanded_body:
                # The ONE shared boundary list (2026-08-09): a scene that
                # applies `libraryServiceEnvironment` injects exactly the
                # services that helper's own `.environment(library.X)` calls
                # name — parsed from the helper file, never assumed, so a
                # service the helper lacks still gets reported.
                injected |= injected_types(
                    _read_text(helper_env_file), services, property_types
                )
            for root in sorted(roots):
                for service in sorted(required_services(root, index, services, property_types) - injected):
                    found[f"{label} needs {service}"] = (
                        f"{_rel(path)} — root {root} reaches a non-optional "
                        f"@Environment({service}.self) reader, but the scene never injects it"
                    )
    for label in sorted(set(declared) - seen_detached):
        found[f"{label} is a stale DETACHED_SCENES entry"] = (
            "no scene with this label exists any more; remove the entry"
        )
    return found, examined


def build_fixture(app_dir: Path) -> tuple[Path, Path]:
    """Write the negative fixture app tree; returns (workspace file, manager file).

    One scene that injects `ArtifactService` and one that does not, over a pane
    that reads it non-optionally. Shared by `--self-test` and the pytest suite.
    """
    workspace = app_dir / "LibraryWorkspaceRoot.swift"
    workspace.write_text(
        "struct LibraryWorkspaceRoot: View {\n"
        "  var body: some View { DocumentTabView().environment(library.artifactService) }\n"
        "}\n",
        encoding="utf-8",
    )
    manager = app_dir / "LibraryManager.swift"
    manager.write_text(
        "class LibraryManager {\n  class LibraryReference {\n"
        "    let artifactService: ArtifactService\n  }\n}\n",
        encoding="utf-8",
    )
    (app_dir / "Panes.swift").write_text(
        "struct ArtifactsInspectorPane: View {\n"
        "  @Environment(ArtifactService.self) private var artifactService\n"
        '  var body: some View { Text("x") }\n}\n',
        encoding="utf-8",
    )
    (app_dir / "Windows.swift").write_text(
        "struct GoodWindow: View { var body: some View { ArtifactsInspectorPane() } }\n"
        "struct BadWindow: View { var body: some View { ArtifactsInspectorPane() } }\n",
        encoding="utf-8",
    )
    # The shared boundary helper (LibraryServiceEnvironment) — a scene that
    # applies it is credited with EXACTLY the services the helper names.
    helper = app_dir / "LibraryServiceEnvironment.swift"
    helper.write_text(
        "extension View {\n"
        "  func libraryServiceEnvironment(_ library: LibraryManager.LibraryReference) -> some View {\n"
        "    self.environment(library.artifactService)\n  }\n}\n",
        encoding="utf-8",
    )
    (app_dir / "Windows2.swift").write_text(
        "struct HelperWindow: View { var body: some View { ArtifactsInspectorPane() } }\n",
        encoding="utf-8",
    )
    (app_dir / "App.swift").write_text(
        "struct DemoApp: App {\n  var body: some Scene {\n"
        '    Window("Good", id: "good") { GoodWindow().environment(library.artifactService) }\n'
        '    Window("Bad", id: "bad") { BadWindow() }\n'
        '    Window("Helper", id: "helper") { HelperWindow().libraryServiceEnvironment(library) }\n'
        "  }\n}\n",
        encoding="utf-8",
    )
    return workspace, manager


FIXTURE_CONTRACTS = {
    "good (Window)": "fixture: injects what its tree reads",
    "bad (Window)": "fixture: deliberately omits the injection",
    "helper (Window)": "fixture: injects via the shared libraryServiceEnvironment helper",
}


def _self_test() -> int:
    """Prove the check FIRES on a scene that drops an injection (#4513).

    A guardrail that has never seen its bad case is worthless
    (guardrails-must-match-granularity). Both rules are exercised: the static
    walk (rule 1) against a scene missing an injection, and the declared-contract
    tripwire (rule 2) against a scene nobody wrote a contract for.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        app_dir = Path(tmp)
        workspace, manager = build_fixture(app_dir)
        fixture_helper = app_dir / "LibraryServiceEnvironment.swift"
        found, examined = scan(
            app_dir, workspace, manager, detached=FIXTURE_CONTRACTS,
            helper_env_file=fixture_helper,
        )
        undeclared, _ = scan(
            app_dir, workspace, manager, detached={}, helper_env_file=fixture_helper
        )
        stale, _ = scan(
            app_dir, workspace, manager,
            detached=FIXTURE_CONTRACTS | {"ghost (Window)": "gone"},
            helper_env_file=fixture_helper,
        )

    failures = []
    if examined != 3:
        failures.append(f"expected 3 scenes examined, got {examined}")
    if "bad (Window) needs ArtifactService" not in found:
        failures.append(f"rule 1: the missing-injection scene was NOT reported: {sorted(found)}")
    if any(key.startswith("good (Window)") for key in found):
        failures.append(f"rule 1: the correctly-injecting scene was falsely reported: {sorted(found)}")
    if any(key.startswith("helper (Window)") for key in found):
        failures.append(
            "helper rule: a scene injecting via libraryServiceEnvironment was falsely "
            f"reported: {sorted(found)}"
        )
    if "good (Window) needs a declared environment contract" not in undeclared:
        failures.append(f"rule 2: an undeclared detached scene was NOT reported: {sorted(undeclared)}")
    if "ghost (Window) is a stale DETACHED_SCENES entry" not in stale:
        failures.append(
            "stale-entry rule: a contract for a scene that no longer exists was NOT "
            f"reported: {sorted(stale)}"
        )

    if failures:
        print("SELF-TEST FAILED — this guardrail cannot detect its own bad case:")
        for failure in failures:
            print(f"    {failure}")
        return 1
    print(
        "SELF-TEST PASS: fires on a scene missing an injection, on an undeclared detached "
        "scene, and on a stale contract; stays quiet on a scene that injects what it reads."
    )
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if any(arg in ("-h", "--help") for arg in argv):
        print(__doc__)
        return 0
    if "--self-test" in argv:
        return _self_test()

    services = canonical_services()
    found, examined = scan()
    known = set(KNOWN_GAPS)

    if "--list" in argv:
        print(f"Scene environment-injection findings ({len(found)}):\n")
        for key, reason in sorted(found.items()):
            tag = "known" if key in known else "NEW"
            print(f"  [{tag}] {key}  <-  {reason}")
        return 0

    # #4487 scan floor: 14 scenes across 2 App files, 36 canonical services on
    # 2026-08-04. Halved and rounded down — a tripwire, not a ratchet.
    require_scan_floor(examined, 7, "scenes in App files (14 on 2026-08-04)")
    require_scan_floor(len(services), 18, "canonical library services (36 on 2026-08-04)")

    print("Scene environment-injection guardrail: scanned fichero/fichero App files")
    print(f"  {examined} scene(s); {len(services)} canonical service(s); {len(found)} finding(s).")

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    if stale:
        print(f"\n  {len(stale)} KNOWN_GAPS entries are now clean; remove them:")
        for key in stale:
            print(f"      {key}")

    if new:
        print(f"\n  {len(new)} scene/service pair(s) with no injection on the scene boundary:")
        for key in new:
            print(f"      {key}  <-  {found[key]}")
        print(
            "\nFix: inject the service on the SCENE, next to the view it hosts — the\n"
            "environment does not cross a Scene boundary, so an omission is a trap, not\n"
            "a degraded render. If the reader is genuinely optional, declare it\n"
            f"`@Environment(T.self) private var t: T?`. Rule pointer: {RULE_DOC}."
        )
        return 1

    print("\nPASS every scene injects the library-scoped services its tree reads.")
    return 0


def _require_scan_roots_4382(*roots):
    """#4382: a guardrail must know when it has gone blind, and say so."""
    missing = [str(r) for r in roots if not r.exists()]
    if missing:
        print(
            f"{Path(__file__).name}: BLIND -- scan root(s) missing: "
            + ", ".join(missing)
            + " (the tree moved; update this guardrail's paths)",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    _require_scan_roots_4382(APP_DIR, WORKSPACE_ROOT_FILE, LIBRARY_MANAGER_FILE)
    raise SystemExit(main())
