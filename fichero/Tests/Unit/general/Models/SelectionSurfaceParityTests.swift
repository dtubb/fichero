@testable import Fichero
import FicheroAPIClient
import Foundation
import SwiftUI
import Testing

/// #4436: every library surface must answer the same gesture the same way.
///
/// `SelectionGrammarTests` is the table of RULES. This is the table of
/// SURFACES: for each gesture, the grammar's answer is computed once and every
/// surface that implements that gesture is required to match it. The four modes
/// each had their own copy and they disagreed about the anchor — a suite that
/// only tested the grammar would have been green throughout, because the
/// grammar was never the thing that was wrong.
///
/// A fifth mode fails here as soon as it is added, because `everySurface` below
/// is the enumeration, and each surface is exercised through its own real entry
/// point rather than through the grammar directly. A mode that reimplements the
/// rules cannot pass by importing the type.
@MainActor
struct SelectionSurfaceParityTests {
    private typealias Modifiers = SelectionGrammar.Modifiers

    /// The canvas surfaces speak node ids and have no ordered list, so the
    /// shared vocabulary is orderless ids that survive both spaces.
    private static let ids = ["doc:a", "doc:b", "doc:c", "doc:d"]

    // MARK: - Surfaces under test

    /// One surface, reduced to what every surface has: apply a click, then
    /// report the selection and the anchor it left behind.
    private struct Surface {
        let name: String
        /// (existing selection, existing anchor, clicked id, modifiers)
        /// -> (selection, anchor)
        let click: (Set<String>, String?, String, Modifiers) -> (Set<String>, String?)
    }

    /// The grammar itself — the reference answer every surface is compared to.
    private static func reference(
        _ selection: Set<String>, _ anchor: String?, _ id: String, _ modifiers: Modifiers
    ) -> (Set<String>, String?) {
        let result = SelectionGrammar.click(
            id: id, in: [], selection: selection, anchor: anchor, modifiers: modifiers
        )
        return (result.selection, result.anchor)
    }

    /// The RealityKit canvas, driven through `CanvasInteractionController`.
    private static func canvasController(
        _ selection: Set<String>, _ anchor: String?, _ id: String, _ modifiers: Modifiers
    ) -> (Set<String>, String?) {
        let box = SelectionBox(selection)
        let controller = CanvasInteractionController(
            layoutStore: NullLayoutStore(),
            itemStore: NullItemStore(),
            scopeId: "scope",
            selection: box.binding
        )
        // Seed the anchor the way the surface really acquires one — by having
        // acted on that row — rather than by poking private state.
        if let anchor {
            controller.select(anchor, modifiers: selection.contains(anchor) ? [] : .command)
            box.value = selection
        }
        controller.select(id, modifiers: modifiers)
        return (box.value, controller.selectionAnchor)
    }

    /// The legacy renderers, driven through `CanvasTapSelection`.
    private static func legacyCanvas(
        _ selection: Set<String>, _ anchor: String?, _ id: String, _ modifiers: Modifiers
    ) -> (Set<String>, String?) {
        var live = selection
        var liveAnchor = anchor
        CanvasTapSelection.tap(id, selection: &live, anchor: &liveAnchor, modifiers: modifiers)
        return (live, liveAnchor)
    }

    /// The native `Table`, which does the click itself and then reconciles.
    /// Its "click" is simulated by applying the grammar's SET (what AppKit
    /// would produce — AppKit implements the same rules) and then asking
    /// `reconcile` to recover the anchor from the set change PLUS the
    /// modifiers that were down (#4531) — exactly the information the real
    /// `onChange` has, which reads `NSEvent.modifierFlags` at that moment.
    private static func tableReconcile(
        _ selection: Set<String>, _ anchor: String?, _ id: String, _ modifiers: Modifiers
    ) -> (Set<String>, String?) {
        let appKitResult = SelectionGrammar.click(
            id: id, in: ids, selection: selection, anchor: anchor, modifiers: modifiers
        )
        let reconciled = SelectionGrammar.reconcile(
            from: selection, to: appKitResult.selection, anchor: anchor, in: ids,
            modifiers: modifiers
        )
        return (reconciled.selection, reconciled.anchor)
    }

    private static let everySurface: [Surface] = [
        Surface(name: "SelectionGrammar (list, icon, columns, entities)", click: reference),
        Surface(name: "CanvasInteractionController (canvas 2D / space 3D)", click: canvasController),
        Surface(name: "CanvasTapSelection (legacy canvas renderers)", click: legacyCanvas),
        Surface(name: "Table + SelectionGrammar.reconcile", click: tableReconcile)
    ]

    // MARK: - The gestures every surface must agree on

    private struct Gesture {
        let name: String
        let selection: Set<String>
        let anchor: String?
        let clicked: String
        let modifiers: Modifiers
    }

    private static let gestures: [Gesture] = [
        Gesture(name: "plain click on an unselected row replaces",
                selection: ["doc:a"], anchor: "doc:a", clicked: "doc:c", modifiers: []),
        Gesture(name: "plain click on the already-selected row keeps just it",
                selection: ["doc:a", "doc:b"], anchor: "doc:a", clicked: "doc:a", modifiers: []),
        Gesture(name: "⌘-click ADDS to the selection",
                selection: ["doc:a"], anchor: "doc:a", clicked: "doc:c", modifiers: .command),
        Gesture(name: "⌘-click on a selected row DESELECTS it and keeps the rest",
                selection: ["doc:a", "doc:b", "doc:c"], anchor: "doc:a",
                clicked: "doc:c", modifiers: .command),
        Gesture(name: "⌘-click builds a discontiguous set",
                selection: ["doc:a", "doc:c"], anchor: "doc:c", clicked: "doc:d", modifiers: .command),
        Gesture(name: "⌘-click with nothing selected selects one",
                selection: [], anchor: nil, clicked: "doc:b", modifiers: .command)
    ]

    @Test("Every surface answers the same click the same way")
    func surfacesAgreeOnClick() {
        for gesture in Self.gestures {
            let (expectedSelection, expectedAnchor) = Self.reference(
                gesture.selection, gesture.anchor, gesture.clicked, gesture.modifiers
            )
            for surface in Self.everySurface {
                let (selection, anchor) = surface.click(
                    gesture.selection, gesture.anchor, gesture.clicked, gesture.modifiers
                )
                #expect(
                    selection == expectedSelection,
                    "\(surface.name) disagreed about the SELECTION for: \(gesture.name)"
                )
                #expect(
                    anchor == expectedAnchor,
                    "\(surface.name) disagreed about the ANCHOR for: \(gesture.name)"
                )
            }
        }
    }

    /// Rule 1, isolated, because it is the one a second implementation always
    /// gets wrong: the anchor follows a ⌘-click that DESELECTED the row.
    /// Deriving the anchor from the resulting selection alone cannot express
    /// it — the acted-on row is not in that set.
    @Test("A ⌘-click that deselects still moves the anchor, on every surface")
    func deselectingClickMovesTheAnchorEverywhere() {
        for surface in Self.everySurface {
            let (selection, anchor) = surface.click(
                ["doc:a", "doc:b", "doc:c"], "doc:a", "doc:c", .command
            )

            #expect(selection == ["doc:a", "doc:b"], "\(surface.name)")
            #expect(anchor == "doc:c", "\(surface.name) left the anchor where the user was NOT")
        }
    }

    /// The old "one place a surface may differ" CLOSED with #4531: the Table's
    /// reconcile now receives the modifiers, so ⌘-deselecting down to exactly
    /// one row anchors on the acted (deselected) row like every other surface
    /// — its predecessor test said "the documented divergence closed — delete
    /// this test", and it was.
    ///
    /// What remains pinned is the CONTEXT-FREE compromise: a caller with no
    /// gesture information (modifiers omitted) still resolves the ambiguous
    /// down-to-one delta toward the plain click, anchoring on the survivor —
    /// a visible, selected row, which is the #4377 property.
    @Test("Without gesture context, down-to-one still resolves toward the plain click")
    func contextFreeReconcileResolvesTowardThePlainClick() {
        let result = SelectionGrammar.reconcile(
            from: ["doc:a", "doc:c"], to: ["doc:a"], anchor: "doc:a", in: Self.ids
        )

        #expect(result.selection == ["doc:a"])
        #expect(result.anchor == "doc:a")
        #expect(result.selection.contains(result.anchor ?? ""))

        // And WITH the ⌘ context, the same delta anchors on the acted row —
        // the rule-1 answer the modifier makes expressible.
        let commanded = SelectionGrammar.reconcile(
            from: ["doc:a", "doc:c"], to: ["doc:a"], anchor: "doc:a", in: Self.ids,
            modifiers: .command
        )
        #expect(commanded.anchor == "doc:c")
    }

    // MARK: - Marquee

    @Test("A plain marquee replaces; ⇧ and ⌘ ADD, as in Finder")
    func marqueeModifiers() {
        let existing: Set<String> = ["doc:a"]

        #expect(
            SelectionGrammar.marquee(ids: ["doc:c", "doc:d"], selection: existing, modifiers: [])
                .selection == ["doc:c", "doc:d"]
        )
        #expect(
            SelectionGrammar.marquee(ids: ["doc:c"], selection: existing, modifiers: .shift)
                .selection == ["doc:a", "doc:c"]
        )
        #expect(
            SelectionGrammar.marquee(ids: ["doc:c"], selection: existing, modifiers: .command)
                .selection == ["doc:a", "doc:c"]
        )
    }

    @Test("A plain marquee that caught nothing clears — the same as an empty-space click")
    func emptyMarqueeClears() {
        let result = SelectionGrammar.marquee(ids: [], selection: ["doc:a"], modifiers: [])

        #expect(result == SelectionGrammar.clear())
    }

    @Test("A marquee leaves a DETERMINISTIC anchor, never Set hash order")
    func marqueeAnchorIsDeterministic() {
        let ids: Set<String> = ["doc:d", "doc:b", "doc:a", "doc:c"]

        // Ten runs: `Set.first` varies across launches, `.min()` cannot.
        let anchors = (0..<10).map { _ in
            SelectionGrammar.marquee(ids: ids, selection: [], modifiers: []).anchor
        }

        #expect(Set(anchors) == ["doc:a"])
    }

    @Test("The canvas marquee publishes the WHOLE set and remembers an anchor (#4409)")
    func canvasMarqueePublishesEverything() {
        let box = SelectionBox([])
        let controller = CanvasInteractionController(
            layoutStore: NullLayoutStore(), itemStore: NullItemStore(),
            scopeId: "scope", selection: box.binding
        )

        controller.selectMany(["doc:a", "doc:b", "doc:c"])

        #expect(box.value == ["doc:a", "doc:b", "doc:c"])
        // The anchor was never set by the old `selectMany`, so a ⌘-click after
        // a marquee had nothing to extend from.
        #expect(controller.selectionAnchor == "doc:a")
    }

    // MARK: - The canvas must READ the shared selection, not just write it

    /// The defect that made "four implementations" cost something: the
    /// controller wrote the binding on every gesture and never read it, so a
    /// selection made in ANY other mode was invisible to it.
    @Test("⌘-clicking on the canvas extends a selection made in another mode")
    func canvasStartsFromTheSharedSelection() {
        // Three rows selected in list mode, then the user switches to canvas.
        let box = SelectionBox(["doc:a", "doc:b", "doc:c"])
        let controller = CanvasInteractionController(
            layoutStore: NullLayoutStore(), itemStore: NullItemStore(),
            scopeId: "scope", selection: box.binding
        )

        controller.select("doc:d", modifiers: .command)

        #expect(box.value == ["doc:a", "doc:b", "doc:c", "doc:d"])
    }

    /// The shared binding cannot represent a STANDALONE CANVAS ITEM — those ids
    /// have no `doc:` prefix, so `librarySelection(forCanvasNodeIds:)` drops
    /// them. Reading the binding alone would therefore make ⌘-clicking two
    /// notes together impossible, which is why the controller merges the ids
    /// the round trip cannot carry.
    @Test("⌘-clicking two canvas items together still works, though the binding drops them")
    func canvasItemsSurviveTheBindingRoundTrip() {
        let box = SelectionBox([])
        let controller = CanvasInteractionController(
            layoutStore: NullLayoutStore(), itemStore: NullItemStore(),
            scopeId: "scope", selection: box.binding
        )

        controller.select("item-1")
        controller.select("item-2", modifiers: .command)

        #expect(controller.selectionSet == ["item-1", "item-2"])
    }

    @Test("Grabbing an already-selected card does not collapse the selection")
    func dragKeepsAMultiSelection() {
        let box = SelectionBox(["doc:a", "doc:b"])
        let controller = CanvasInteractionController(
            layoutStore: NullLayoutStore(), itemStore: NullItemStore(),
            scopeId: "scope", selection: box.binding
        )

        controller.beginDrag("doc:b")

        #expect(box.value == ["doc:a", "doc:b"])
    }

    @Test("Grabbing an UNSELECTED card selects just it")
    func dragOnAnUnselectedCardSelectsIt() {
        let box = SelectionBox(["doc:a"])
        let controller = CanvasInteractionController(
            layoutStore: NullLayoutStore(), itemStore: NullItemStore(),
            scopeId: "scope", selection: box.binding
        )

        controller.beginDrag("doc:c")

        #expect(box.value == ["doc:c"])
    }

    // MARK: - reconcile: the Table's half of the contract

    @Test("Emptying the selection clears the anchor and cursor rather than leaving them stale")
    func reconcileClearsWhenNothingIsSelected() {
        let result = SelectionGrammar.reconcile(
            from: ["doc:a"], to: [], anchor: "doc:a", in: Self.ids
        )

        // The old table handler returned early here, leaving both fields
        // pointing at a row that was no longer selected.
        #expect(result == SelectionGrammar.clear())
    }

    @Test("A many-row change holds the anchor still and moves only the cursor (rule 2)")
    func reconcileHoldsTheAnchorForARange() {
        // ⇧-click from a down to c, then re-extended to d: the anchor must not
        // move, or reversing direction mid-extend can never shrink.
        let grown = SelectionGrammar.reconcile(
            from: ["doc:a"], to: ["doc:a", "doc:b", "doc:c"], anchor: "doc:a", in: Self.ids
        )
        #expect(grown.anchor == "doc:a")
        #expect(grown.cursor == "doc:c")

        // Shrinking by more than one row is unambiguously a range operation —
        // a single-row change would be indistinguishable from a ⌘-deselect,
        // which rule 1 claims first.
        let shrunk = SelectionGrammar.reconcile(
            from: ["doc:a", "doc:b", "doc:c", "doc:d"], to: ["doc:a", "doc:b"],
            anchor: "doc:a", in: Self.ids
        )
        #expect(shrunk.anchor == "doc:a")
        #expect(shrunk.cursor == "doc:b")
    }

    @Test("An anchor that left the selection is replaced by the topmost VISIBLE row")
    func reconcileRecoversAStaleAnchor() {
        let result = SelectionGrammar.reconcile(
            from: ["doc:a", "doc:d"], to: ["doc:b", "doc:c", "doc:d"], anchor: "doc:a", in: Self.ids
        )

        // Never `Set.first` — that is hash order, which would make the same
        // gesture extend differently on different runs.
        #expect(result.anchor == "doc:b")
    }

    // MARK: - The ordered list each surface hands the grammar (#4377)
    //
    // The gestures above all pass a list that matches what is rendered. The two
    // gaps that survived #4436 were not about which grammar call a surface
    // made — both surfaces called the right one — but about the LIST and the
    // ORDER OF OPERATIONS around it. So these test the arguments, which is the
    // part `check_selection_grammar.py` structurally cannot see.

    /// The Table renders an expandable outline. Its child rows carry
    /// `"<doc>:artifact:<id>"` ids that appear in NO document list, so handing
    /// the grammar `filteredDocuments` means handing it a list in which the
    /// selected row does not exist.
    private static let outlineRows = [
        "doc:a", "doc:a:artifact:1", "doc:a:artifact:2", "doc:b", "doc:c"
    ]
    private static let documentRowsOnly = ["doc:a", "doc:b", "doc:c"]

    @Test("↓ from a selected CHILD row steps to the next visible row, not to the top")
    func arrowsResolveAChildRowAgainstTheVisibleOutline() {
        // What the arrow path does first: resolve the cursor to an index.
        let againstVisibleRows = LibraryKeyboardCursor.index(
            cursor: "doc:a:artifact:1",
            anchor: "doc:a:artifact:1",
            selection: ["doc:a:artifact:1"],
            ids: Self.outlineRows
        )
        #expect(againstVisibleRows == 1)
        // ...so ↓ lands on the NEXT row the user can see.
        #expect(Self.outlineRows[(againstVisibleRows ?? 0) + 1] == "doc:a:artifact:2")

        // The defect, pinned: against the document list the same child row
        // resolves to NOTHING. `handleArrowKey` reads that nil as "nothing is
        // selected yet" and selects ids[0] — the user is thrown to the top of
        // the library by pressing ↓.
        #expect(
            LibraryKeyboardCursor.index(
                cursor: "doc:a:artifact:1",
                anchor: "doc:a:artifact:1",
                selection: ["doc:a:artifact:1"],
                ids: Self.documentRowsOnly
            ) == nil,
            "if this resolves, the two lists have converged and this test is obsolete"
        )
    }

    @Test("⇧-extending across disclosed child rows shrinks, which needs the visible order")
    func reconcileHoldsTheAnchorAcrossChildRows() {
        // ⇧↓ ⇧↓ grew a range from the parent through both artifact rows; ⇧↑
        // then shrinks it BY ONE ROW — the delta a gesture-blind reconcile
        // cannot tell from a ⌘-deselect, which is why the ⇧ that was down is
        // passed (#4531). Rule 2: the anchor must not have moved, and the
        // cursor must be the row the range now ENDS on.
        let shrunk = SelectionGrammar.reconcile(
            from: ["doc:a", "doc:a:artifact:1", "doc:a:artifact:2"],
            to: ["doc:a", "doc:a:artifact:1"],
            anchor: "doc:a",
            in: Self.outlineRows,
            modifiers: .shift
        )

        #expect(shrunk.anchor == "doc:a")
        #expect(shrunk.cursor == "doc:a:artifact:1")
    }

    @Test("Against the document list the same shrink cannot find its cursor at all")
    func reconcileDegradesWhenGivenTheWrongList() {
        // Same gesture, wrong list: no child row indexes, so the cursor
        // degrades to the rows the list CAN see. Deterministic — and not the
        // visual order it is supposed to be reasoning about.
        let degraded = SelectionGrammar.reconcile(
            from: ["doc:a", "doc:a:artifact:1", "doc:a:artifact:2"],
            to: ["doc:a", "doc:a:artifact:1"],
            anchor: "doc:a",
            in: Self.documentRowsOnly,
            modifiers: .shift
        )

        #expect(degraded.cursor == "doc:a")
        #expect(
            degraded.cursor != "doc:a:artifact:1",
            "the wrong-list degradation closed — the lists converged, delete this test"
        )
    }

    // The flatten itself — that disclosed children appear in place, only while
    // their parent is expanded — is already pinned by
    // `LibraryOutlineVisibleIdsTests` (#4198). It is not restated here. What
    // was missing was never the flatten; it was that only ⌘A CALLED it, while
    // the arrows and the anchor reconciler used the document list.

    // MARK: - Columns: navigation is a plain-click behaviour

    /// A ⇧- or ⌘-click is BUILDING a selection. `handleTap` already refuses to
    /// drill in for those; the columns wrapper used to descend or truncate the
    /// column path one call EARLIER, going around that guard — so ⌘-clicking a
    /// folder to add it to a selection also opened it, and ⇧-clicking a
    /// document closed every deeper column.
    ///
    /// Scoped to OPENING and CLOSING. Which column is active still follows a
    /// modified click, because a row renders its selection only while its
    /// column is active — freezing that would make ⌘-click look like a no-op.
    @Test("Only a PLAIN columns click opens or closes columns")
    func columnsOpenAndCloseOnPlainClickOnly() {
        #expect(LibraryView.columnTapOpensOrClosesColumns(modifiers: []))
        #expect(!LibraryView.columnTapOpensOrClosesColumns(modifiers: .command))
        #expect(!LibraryView.columnTapOpensOrClosesColumns(modifiers: .shift))
        #expect(!LibraryView.columnTapOpensOrClosesColumns(modifiers: [.shift, .command]))
    }

    /// The grammar has exactly one way to say "land on this one row", so the
    /// three callers that used to hand-fill a `Result` cannot drift apart.
    @Test("select(_:) is the plain-click result, by construction")
    func selectMatchesAPlainClick() {
        let selected = SelectionGrammar.select("doc:c")
        let plainClick = SelectionGrammar.click(
            id: "doc:c", in: Self.ids, selection: ["doc:a"], anchor: "doc:a", modifiers: []
        )

        #expect(selected == plainClick)
    }
}

// MARK: - Minimal seams

/// A settable box behind a `Binding`, standing in for `LibraryView.selection`.
@MainActor
private final class SelectionBox {
    var value: Set<String>

    init(_ value: Set<String>) { self.value = value }

    var binding: Binding<Set<String>> {
        Binding(get: { self.value }, set: { self.value = $0 })
    }
}

@MainActor
private final class NullLayoutStore: CanvasLayoutPersisting {
    var loadError: String?
    func layout(for scopeId: String) -> [CanvasItemLayout] { [] }
    func saveLayout(folderId: String, items: [CanvasItemLayout]) async -> Bool { true }
}

@MainActor
private final class NullItemStore: CanvasItemMutating {
    var loadError: String?
    func items(for scopeId: String) -> [CanvasItemDisplay] { [] }
    func createItem(
        folderId: String,
        kind: Components.Schemas.CanvasItemKind,
        text: String?,
        sourceItemId: String?,
        targetItemId: String?
    ) async -> CanvasItemDisplay? { nil }
    // swiftlint:disable:next function_parameter_count
    func updateItem(
        folderId: String,
        itemId: String,
        kind: Components.Schemas.CanvasItemKind?,
        text: String?,
        sourceItemId: String?,
        targetItemId: String?
    ) async -> Bool { true }
    func deleteItem(folderId: String, itemId: String) async -> Bool { true }
}
