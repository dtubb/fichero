@testable import Fichero
import Foundation
import Testing

/// The inspector's own Lists (#4502).
///
/// Daniel asked whether the inspector's SwiftUI Lists had been reviewed for drag
/// and drop, keyboard, multi-select and iPad. They had not. The inventory at
/// `agent-work/status/2026-08-03-inspector-list-inventory.md` is the full
/// answer; these are the parts that can fail.
struct InspectorListContractTests {

    // MARK: - A List inside a ScrollView renders at zero height

    /// `SourceInfoView` wraps its children in a `ScrollView`, and a SwiftUI
    /// `List` collapses to zero height inside one. This is not a theory: the
    /// sibling `DocumentInspectorInfoTab` carries a doc comment naming it as
    /// #2107 and was rewritten to plain stacks for exactly this reason. The
    /// metadata tab was the same shape and never got the treatment, so its body
    /// rendered at zero height while the Info block above it looked fine.
    @Test("the metadata tab is not a List, because its host is a ScrollView")
    func theMetadataTabIsNotAList() throws {
        let source = try AppSource.text("Views/Inspector/Source/DocumentInspectorMetadataTab.swift")

        #expect(!source.contains("List(selection:"))
        #expect(!source.contains(".listStyle("))
    }

    /// The rule behind the fix, stated where a NEW tab can trip it. Anything
    /// `SourceInfoView` hosts inherits its `ScrollView`, so none of them may be
    /// a `List` — and the next person to add a tab there will not have read
    /// #2107.
    @Test("nothing SourceInfoView hosts may be a List")
    func nothingInsideSourceInfoViewIsAList() throws {
        let host = try AppSource.text("Views/Inspector/Source/SourceSectionView.swift")
        #expect(host.contains("ScrollView"), "the premise changed; re-check this rule")

        // The views SourceInfoView composes, by name.
        let hosted = [
            "Views/Inspector/Source/Info/DocumentInspectorInfoTab.swift",
            "Views/Inspector/Source/DocumentInspectorMetadataTab.swift"
        ]
        for path in hosted {
            // Comments stripped, same as metadataRowsAreButtons below: the
            // Info tab's Aug 3 refactors explain the List(selection:) they
            // REMOVED, and the ban must fire on a List, not on its obituary.
            let source = Self.code(of: try AppSource.text(path))
            #expect(
                !source.contains("List(selection:"),
                "\(path) is a List inside SourceInfoView's ScrollView — it will render at zero height (#2107)"
            )
        }
    }

    /// The replacement must not import the problem it replaced. The Info tab
    /// drives its rows with a bare `.onTapGesture` on a stack, which is not
    /// focusable, not keyboard-reachable, not announced as a button, and not a
    /// real touch target on iPad. The metadata rows use `Button` instead.
    @Test("metadata rows are buttons, not bare tap gestures")
    func metadataRowsAreButtons() throws {
        let source = try AppSource.text("Views/Inspector/Source/DocumentInspectorMetadataTab.swift")

        #expect(source.contains(".buttonStyle(.plain)"))
        // Comments stripped first. The file's own doc comment explains why it
        // does NOT use `.onTapGesture`, and matching raw source would fail on
        // that prose — a guardrail firing on its own explanation is the
        // vacuous shape from the other direction.
        #expect(!Self.code(of: source).contains(".onTapGesture"))
    }

    /// Source with `//` line comments removed, so a rule about CODE is not
    /// satisfied or broken by what a comment happens to say.
    private static func code(of source: String) -> String {
        source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> Substring in
                guard let marker = line.range(of: "//") else { return line }
                return line[line.startIndex..<marker.lowerBound]
            }
            .joined(separator: "\n")
    }

    // MARK: - A link that cannot be followed is not rendered as a control

    /// A note's backlinks and forward links were an `HStack` of an icon and a
    /// `Text` — no button, no tap, no context menu. The cross-references were
    /// displayed and could not be followed, in the surface whose purpose is
    /// following them. #4421 calls that an affordance that does nothing.
    @Test("a linked note can be opened")
    func aLinkedNoteCanBeOpened() throws {
        let source = try AppSource.text("Views/Inspector/Notes/NoteDetailView.swift")

        #expect(source.contains("var onOpenLink: ((String) -> Void)?"))
        #expect(source.contains("Button { onOpenLink(id) }"))
    }

    /// And where it CANNOT be followed it stays plain text rather than becoming
    /// a dead button. The torn-off note window has no list to select in, so it
    /// passes no handler — the standing rule is to render the thing absent, not
    /// broken.
    @Test("the torn-off window leaves links inert rather than offering a dead button")
    func theTornOffWindowPassesNoHandler() throws {
        let pane = try AppSource.text("Views/Inspector/Notes/NotesInspectorPane.swift")

        // The docked pane wires it; the window call site does not.
        #expect(pane.contains("onOpenLink: { noteId in focused.id = noteId }"))
        #expect(pane.contains("NoteDetailView(item: shownItem)"))
    }

    // MARK: - Where the inspector SHOULD differ from the library

    /// Recorded so a later uniformity sweep does not "fix" a correct difference
    /// into a bug. The Related tab's rows navigate; there is no batch action for
    /// a multi-selection to feed, and the file says so at its declaration.
    @Test("the Related tab stays single-selection, deliberately")
    func theRelatedTabIsDeliberatelySingleSelection() throws {
        let source = try AppSource.text("Views/Inspector/Document/DocumentInspectorRelatedTab.swift")

        #expect(source.contains("selectedDocumentId"))
        #expect(!source.contains("Set<String>"))
        // The reasoning has to survive too — an undocumented single-selection
        // is indistinguishable from an oversight, which is question 3 in the
        // inventory for the lists that lack it.
        #expect(source.lowercased().contains("multi-select"))
    }

    /// No inspector list is user-orderable, and that is correct rather than
    /// missing: every one of them shows a DERIVED order (newest-first, by run,
    /// by kind, sorted keys). `.onMove` would be a lie about what the list is,
    /// and there would be no user order to persist.
    @Test("no inspector list offers reorder")
    func noInspectorListOffersReorder() throws {
        let root = try AppSource.root().appendingPathComponent("Views/Inspector")
        var checked = 0

        let enumerator = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil)
        while let url = enumerator?.nextObject() as? URL {
            guard url.pathExtension == "swift" else { continue }
            checked += 1
            let source = try String(contentsOf: url, encoding: .utf8)
            #expect(
                !source.contains(".onMove("),
                "\(url.lastPathComponent) added reorder — inspector lists show a derived order (#4502)"
            )
        }

        // A sweep that scanned nothing would pass forever (#4487).
        #expect(checked > 50, "expected the inspector tree; scanned \(checked) files")
    }
}
