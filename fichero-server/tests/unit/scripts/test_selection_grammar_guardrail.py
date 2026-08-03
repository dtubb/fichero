"""The selection-grammar guardrail must FIRE on a fifth view mode (#4436).

The whole point of this check is the mode nobody has written yet: four modes
implemented one concept four ways and disagreed about the anchor, and the fix is
only a fix if adding a fifth that skips the grammar FAILS. So every rule gets a
positive fixture proving it fires, plus the near-miss negatives it must not fire
on — a guardrail that silently matches nothing reads as proof of safety
(#4487, and the .build/vendored lesson: it must also see only shipping source).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location(
        "_check_selection_grammar", SCRIPTS / "check_selection_grammar.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = _load()


def _mode(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body)
    return path


def _scan(tmp_path: Path, name: str, body: str):
    return check.violations([_mode(tmp_path, name, body)], root=tmp_path)


# ---------------------------------------------------------------------------
# POSITIVE — the fifth mode that did not adopt the grammar
# ---------------------------------------------------------------------------

_FIFTH_MODE = """
extension LibraryView {
    var gridModeView: some View {
        ForEach(filteredDocuments) { doc in
            Cell(doc).onTapGesture {
                selection = [doc.id]
            }
        }
    }
}
"""


def test_a_fifth_mode_that_replaces_the_selection_by_hand_fails(tmp_path):
    found = _scan(tmp_path, "LibraryView+GridMode.swift", _FIFTH_MODE)

    assert len(found) == 1
    assert "selection = [doc.id]" in found[0][2]


_ANCHOR_ONLY = """
extension LibraryView {
    func handleGridTap(_ doc: Document) {
        selectionAnchor = doc.id
    }
}
"""


def test_writing_only_the_anchor_fails(tmp_path):
    """The columns defect: the set and the anchor drifting apart."""
    found = _scan(tmp_path, "LibraryView+GridMode.swift", _ANCHOR_ONLY)

    assert len(found) == 1
    assert "selectionAnchor" in found[0][2]


_CANVAS_BY_HAND = """
struct NewCanvas: View {
    @Binding var selectedNodeIds: Set<String>
    var body: some View {
        Card().onTapGesture { selectedNodeIds = [node.id] }
    }
}
"""


def test_a_new_canvas_renderer_that_replaces_node_selection_fails(tmp_path):
    found = _scan(tmp_path, "NewCanvasView.swift", _CANVAS_BY_HAND)

    assert len(found) == 1


# ---------------------------------------------------------------------------
# NEGATIVE — the shapes that MUST NOT fire, or the check is unusable
# ---------------------------------------------------------------------------

_DELEGATING_MODE = """
extension LibraryView {
    func handleGridTap(_ doc: Document) {
        apply(SelectionGrammar.click(
            id: doc.id,
            in: keyboardNavigationDocuments.map(\\.id),
            selection: selection,
            anchor: selectionAnchor,
            modifiers: currentSelectionModifiers
        ))
    }
}
"""


def test_a_mode_that_delegates_passes(tmp_path):
    assert _scan(tmp_path, "LibraryView+GridMode.swift", _DELEGATING_MODE) == []


_COMMITTING_A_RESULT = """
extension LibraryView {
    func handleGridTap(_ doc: Document) {
        let result = SelectionGrammar.click(
            id: doc.id, in: ids, selection: selection,
            anchor: selectionAnchor, modifiers: []
        )
        selection = result.selection
        selectionAnchor = result.anchor
        selectionCursor = result.cursor
    }
}
"""


def test_committing_a_grammar_result_is_not_a_bypass(tmp_path):
    """The three assignments that APPLY a Result are the grammar, not a copy."""
    assert _scan(tmp_path, "LibraryView+GridMode.swift", _COMMITTING_A_RESULT) == []


_RENAMED_LOCAL = """
extension LibraryView {
    func clearIt() {
        let cleared = SelectionGrammar.clear()
        selection = cleared.selection
        selectionAnchor = cleared.anchor
    }
}
"""


def test_the_commit_exemption_does_not_depend_on_the_local_being_named_result(tmp_path):
    """Pinning the exemption to a variable name is how a check stops firing."""
    assert _scan(tmp_path, "LibraryView+GridMode.swift", _RENAMED_LOCAL) == []


_FORWARDING = """
struct ModeHost: View {
    @Binding var selectedNodeIds: Set<String>
    var body: some View {
        CanvasSceneView(selectedNodeIds: $selectedNodeIds)
        Table(of: Node.self, selection: $selection) { columns }
    }
}
"""


def test_forwarding_a_binding_to_a_child_is_not_a_second_implementation(tmp_path):
    assert _scan(tmp_path, "ModeHost.swift", _FORWARDING) == []


_PRUNE_AFTER_DELETE = """
extension LibraryView {
    func finishDelete() {
        for doc in documentsToDelete {
            selection.remove(doc.id)
            selection = selection.filter { !$0.hasPrefix("\\(doc.id):") }
        }
    }
}
"""


def test_pruning_deleted_ids_is_not_a_gesture(tmp_path):
    """No anchor rule applies — the rows are gone, not deselected."""
    assert _scan(tmp_path, "LibraryView+DeleteActions.swift", _PRUNE_AFTER_DELETE) == []


_RENDERER_MIRROR = """
final class CanvasOrtho2DRenderer {
    private var selection: Set<String> = []
    func apply(_ op: Op) {
        case .setSelection(let newSelection):
            let changed = selection.symmetricDifference(newSelection)
            selection = newSelection
    }
}
"""


def test_the_named_renderer_mirror_exemption_holds(tmp_path):
    assert _scan(tmp_path, "CanvasOrtho2DRenderer.swift", _RENDERER_MIRROR) == []


def test_the_renderer_exemption_is_by_NAME_not_by_shape(tmp_path):
    """A new file with the same shape but a different name still fires — the
    exemption is a decision about two known files, not a pattern hole."""
    found = _scan(tmp_path, "SomeOtherRenderer.swift", _RENDERER_MIRROR)

    assert len(found) == 1


_COMMENT_QUOTING_THE_SHAPE = """
extension LibraryView {
    // This used to be `selectedNodeIds = [node.id]`, a bare replace.
    /// Documented shape: selection = [doc.id]
    func handleGridTap(_ doc: Document) {
        apply(SelectionGrammar.click(id: doc.id, in: ids, selection: selection,
                                     anchor: selectionAnchor, modifiers: []))
    }
}
"""


def test_a_comment_quoting_the_forbidden_shape_is_prose_not_code(tmp_path):
    """A check that flags its neighbours' comments is a check people turn off."""
    assert _scan(tmp_path, "LibraryView+GridMode.swift", _COMMENT_QUOTING_THE_SHAPE) == []


_ID_ADAPTER = """
extension LibraryView {
    var canvasSelectedNodeIds: Binding<Set<String>> {
        Binding(
            get: { Self.canvasNodeIds(forSelection: selection) },
            set: { selection = Self.librarySelection(forCanvasNodeIds: $0) }
        )
    }
}
"""


def test_the_canvas_id_adapter_translates_rather_than_decides(tmp_path):
    """The grammar already ran on the controller before this binding is written."""
    assert _scan(tmp_path, "LibraryView+Selection.swift", _ID_ADAPTER) == []


_INLINE_IN_A_CLOSURE = """
struct GridMode: View {
    var body: some View {
        Cell().onTapGesture { selectedNodeIds = [node.id] }
    }
}
"""


def test_an_inline_write_inside_a_one_line_closure_still_fires(tmp_path):
    """The exact shape both legacy canvas renderers shipped. A start-of-line
    anchor walks straight past it, which is why the matcher has none."""
    found = _scan(tmp_path, "GridMode.swift", _INLINE_IN_A_CLOSURE)

    assert len(found) == 1


# ---------------------------------------------------------------------------
# The check must see only shipping source
# ---------------------------------------------------------------------------

def test_the_real_tree_is_clean_and_the_population_is_real():
    """Running against the repo: clean, and over a plausible number of files.

    Zero files scanned and zero violations are the same exit code otherwise —
    the failure #4487 exists to prevent.
    """
    files = check._swift_files()

    assert len(files) >= 36, "the view-mode tree collapsed; the scan is blind"
    assert not any(
        part in {".build", "Pods", "DerivedData"} for f in files for part in f.parts
    )
    assert check.violations() == []


def test_it_reports_blind_rather_than_clean_when_the_roots_are_empty(tmp_path, monkeypatch):
    """A present-but-empty tree must exit 2, never 0."""
    empty = tmp_path / "fichero" / "fichero" / "Views" / "Library" / "ViewModes"
    empty.mkdir(parents=True)
    monkeypatch.setattr(check, "VIEW_MODES", empty)
    monkeypatch.setattr(check, "LIBRARY_VIEWS", empty.parent)

    with pytest.raises(SystemExit) as excinfo:
        check.main()

    assert excinfo.value.code == 2
