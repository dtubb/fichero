@testable import Fichero
import Foundation
import Testing

/// #4377: the Mac multi-select grammar as a table.
///
/// Every rule is a row: `(ordered ids, existing selection, anchor, modifiers,
/// clicked id) → (new selection, new anchor, new cursor)`. The table is the
/// deliverable — the library and the inspector used to implement these rules
/// twice, differently, and the library's copy silently did NOTHING whenever
/// its anchor had gone stale. A rule that is not a row here is a rule nobody
/// is holding.
struct SelectionGrammarTests {
    private typealias Modifiers = SelectionGrammar.Modifiers

    /// Five rows, in visual order. Deliberately more than three so a range can
    /// have a genuine middle.
    private static let ids = ["a", "b", "c", "d", "e"]

    /// One row of the grammar table.
    private struct ClickCase {
        let rule: String
        var ids: [String] = SelectionGrammarTests.ids
        let selection: Set<String>
        let anchor: String?
        let modifiers: Modifiers
        let clicked: String
        let expectedSelection: Set<String>
        let expectedAnchor: String?
        let expectedCursor: String?
    }

    private static let clickTable: [ClickCase] = [
        // — plain click: select one, set the anchor —
        ClickCase(
            rule: "plain click on an empty selection selects one and anchors it",
            selection: [], anchor: nil, modifiers: [], clicked: "c",
            expectedSelection: ["c"], expectedAnchor: "c", expectedCursor: "c"
        ),
        ClickCase(
            rule: "plain click REPLACES an existing multi-selection",
            selection: ["a", "b"], anchor: "a", modifiers: [], clicked: "c",
            expectedSelection: ["c"], expectedAnchor: "c", expectedCursor: "c"
        ),

        // — ⌘-click: toggle one, anchor moves to it —
        ClickCase(
            rule: "command-click ADDS one and moves the anchor to it",
            selection: ["a"], anchor: "a", modifiers: [.command], clicked: "c",
            expectedSelection: ["a", "c"], expectedAnchor: "c", expectedCursor: "c"
        ),
        ClickCase(
            rule: "command-click REMOVES a selected row without collapsing the rest",
            selection: ["a", "b", "c"], anchor: "a", modifiers: [.command], clicked: "b",
            expectedSelection: ["a", "c"], expectedAnchor: "b", expectedCursor: "b"
        ),
        ClickCase(
            rule: "command-click toggling OFF still moves the anchor — you extend from where you acted",
            selection: ["a", "b"], anchor: "b", modifiers: [.command], clicked: "a",
            expectedSelection: ["b"], expectedAnchor: "a", expectedCursor: "a"
        ),

        // — ⇧-click: contiguous range from the anchor, anchor unchanged —
        ClickCase(
            rule: "shift-click selects the contiguous range from the anchor, forwards",
            selection: ["b"], anchor: "b", modifiers: [.shift], clicked: "d",
            expectedSelection: ["b", "c", "d"], expectedAnchor: "b", expectedCursor: "d"
        ),
        ClickCase(
            rule: "shift-click ranges BACKWARDS from the anchor too",
            selection: ["c"], anchor: "c", modifiers: [.shift], clicked: "a",
            expectedSelection: ["a", "b", "c"], expectedAnchor: "c", expectedCursor: "a"
        ),
        ClickCase(
            rule: "a repeated shift-click re-extends from the SAME anchor, shrinking the range",
            selection: ["b", "c", "d"], anchor: "b", modifiers: [.shift], clicked: "c",
            expectedSelection: ["b", "c"], expectedAnchor: "b", expectedCursor: "c"
        ),
        ClickCase(
            rule: "shift-click on the anchor itself selects just the anchor",
            selection: ["b", "c", "d"], anchor: "b", modifiers: [.shift], clicked: "b",
            expectedSelection: ["b"], expectedAnchor: "b", expectedCursor: "b"
        ),

        // — ⇧ after ⌘: extends from the COMMAND-CLICKED anchor —
        ClickCase(
            rule: "shift-click after a command-click extends from the command-clicked anchor",
            selection: ["a", "d"], anchor: "d", modifiers: [.shift], clicked: "b",
            expectedSelection: ["b", "c", "d"], expectedAnchor: "d", expectedCursor: "b"
        ),

        // — ⇧⌘: add a range to a discontiguous selection —
        ClickCase(
            rule: "command-shift-click UNIONS the range into the existing selection",
            selection: ["a"], anchor: "c", modifiers: [.shift, .command], clicked: "e",
            expectedSelection: ["a", "c", "d", "e"], expectedAnchor: "c", expectedCursor: "e"
        ),

        // — the #4377 regressions: a shift-click must NEVER be a no-op —
        ClickCase(
            rule: "shift-click with NO anchor selects the clicked row instead of doing nothing",
            selection: [], anchor: nil, modifiers: [.shift], clicked: "d",
            expectedSelection: ["d"], expectedAnchor: "d", expectedCursor: "d"
        ),
        ClickCase(
            rule: "shift-click with a STALE anchor extends from the topmost selected row",
            selection: ["a", "b"], anchor: "gone-after-a-refilter", modifiers: [.shift], clicked: "d",
            expectedSelection: ["a", "b", "c", "d"], expectedAnchor: "a", expectedCursor: "d"
        ),
        ClickCase(
            rule: "shift-click with a stale anchor AND no selection falls back to the clicked row",
            selection: [], anchor: "gone", modifiers: [.shift], clicked: "d",
            expectedSelection: ["d"], expectedAnchor: "d", expectedCursor: "d"
        ),
        ClickCase(
            rule: "shift-click on a row outside this ordered list selects it rather than no-oping",
            selection: ["a"], anchor: "a", modifiers: [.shift], clicked: "deep-column-child",
            expectedSelection: ["deep-column-child"],
            expectedAnchor: "deep-column-child",
            expectedCursor: "deep-column-child"
        ),

        // — a one-row and an empty list must not trap —
        ClickCase(
            rule: "a single-row list shift-clicks to itself",
            ids: ["only"], selection: [], anchor: nil, modifiers: [.shift], clicked: "only",
            expectedSelection: ["only"], expectedAnchor: "only", expectedCursor: "only"
        ),
    ]

    @Test("the click grammar table")
    func clickGrammarTable() {
        for testCase in Self.clickTable {
            let result = SelectionGrammar.click(
                id: testCase.clicked,
                in: testCase.ids,
                selection: testCase.selection,
                anchor: testCase.anchor,
                modifiers: testCase.modifiers
            )
            #expect(result.selection == testCase.expectedSelection, "\(testCase.rule) — selection")
            #expect(result.anchor == testCase.expectedAnchor, "\(testCase.rule) — anchor")
            #expect(result.cursor == testCase.expectedCursor, "\(testCase.rule) — cursor")
        }
    }

    /// The specific defect, stated on its own so it cannot be lost in the table:
    /// the old library implementation `return`ed without touching the selection
    /// whenever the anchor was not found. Every shift-click now selects
    /// something.
    @Test("no shift-click is ever a silent no-op")
    func shiftClickIsNeverANoOp() {
        let anchors: [String?] = [nil, "a", "c", "not-in-this-list"]
        let selections: [Set<String>] = [[], ["a"], ["b", "d"], Set(Self.ids)]
        for anchor in anchors {
            for selection in selections {
                for clicked in Self.ids + ["outside-the-list"] {
                    let result = SelectionGrammar.click(
                        id: clicked,
                        in: Self.ids,
                        selection: selection,
                        anchor: anchor,
                        modifiers: [.shift]
                    )
                    #expect(!result.selection.isEmpty, "anchor \(anchor ?? "nil"), clicked \(clicked)")
                    #expect(result.cursor == clicked)
                    #expect(result.anchor != nil)
                }
            }
        }
    }

    // MARK: - Anchor resolution

    /// Never `Set.first`: hash order would make the same gesture build a
    /// different range on different runs. Resolution is by VISUAL index.
    @Test("a stale anchor resolves to the topmost selected row, deterministically")
    func staleAnchorResolvesByVisualOrder() {
        // Insert in an order that has nothing to do with visual order.
        let selection: Set<String> = ["e", "c", "b"]
        for _ in 0..<50 {
            let resolved = SelectionGrammar.resolvedAnchor(
                anchor: "stale",
                selection: selection,
                ids: Self.ids,
                fallingBackTo: "d"
            )
            #expect(resolved == "b")
        }
    }

    @Test("a live anchor wins over the topmost selected row")
    func liveAnchorWins() {
        let resolved = SelectionGrammar.resolvedAnchor(
            anchor: "d",
            selection: ["a", "b"],
            ids: Self.ids,
            fallingBackTo: "e"
        )
        #expect(resolved == "d")
    }

    @Test("with nothing to fall back on, the acted-on row is the anchor")
    func fallbackIsTheActedOnRow() {
        let resolved = SelectionGrammar.resolvedAnchor(
            anchor: nil,
            selection: [],
            ids: Self.ids,
            fallingBackTo: "c"
        )
        #expect(resolved == "c")
    }

    // MARK: - Keyboard extend

    @Test("shift-arrow extends from the anchor and moves only the cursor")
    func shiftArrowExtends() {
        let result = SelectionGrammar.extend(
            to: "c",
            in: Self.ids,
            selection: ["b"],
            anchor: "b",
            extendingRange: true
        )
        #expect(result.selection == ["b", "c"])
        #expect(result.anchor == "b")
        #expect(result.cursor == "c")
    }

    /// The rule that makes ⇧↓ ⇧↓ ⇧↑ behave: because the anchor never moves,
    /// reversing direction SHRINKS the range instead of growing it the other
    /// way.
    @Test("reversing a shift-arrow shrinks the range rather than growing it")
    func shiftArrowShrinks() {
        let grown = SelectionGrammar.extend(
            to: "d", in: Self.ids, selection: ["b"], anchor: "b", extendingRange: true
        )
        #expect(grown.selection == ["b", "c", "d"])

        let shrunk = SelectionGrammar.extend(
            to: "c", in: Self.ids, selection: grown.selection, anchor: grown.anchor, extendingRange: true
        )
        #expect(shrunk.selection == ["b", "c"])
        #expect(shrunk.anchor == "b")
        #expect(shrunk.cursor == "c")
    }

    @Test("a plain arrow replaces the selection and re-anchors")
    func plainArrowReplaces() {
        let result = SelectionGrammar.extend(
            to: "d",
            in: Self.ids,
            selection: ["a", "b", "c"],
            anchor: "a",
            extendingRange: false
        )
        #expect(result.selection == ["d"])
        #expect(result.anchor == "d")
        #expect(result.cursor == "d")
    }

    @Test("shift-arrow with a stale anchor extends from the topmost selected row")
    func shiftArrowRecoversAStaleAnchor() {
        let result = SelectionGrammar.extend(
            to: "d",
            in: Self.ids,
            selection: ["b", "c"],
            anchor: "vanished",
            extendingRange: true
        )
        #expect(result.selection == ["b", "c", "d"])
        #expect(result.anchor == "b")
        #expect(result.cursor == "d")
    }

    /// Mouse and keyboard must agree: the same anchor state and the same target
    /// produce the same range whichever device asked for it.
    @Test("shift-click and shift-arrow build the same range from the same state")
    func mouseAndKeyboardAgree() {
        for target in Self.ids {
            let clicked = SelectionGrammar.click(
                id: target, in: Self.ids, selection: ["b"], anchor: "b", modifiers: [.shift]
            )
            let arrowed = SelectionGrammar.extend(
                to: target, in: Self.ids, selection: ["b"], anchor: "b", extendingRange: true
            )
            #expect(clicked.selection == arrowed.selection, "target \(target)")
            #expect(clicked.anchor == arrowed.anchor, "target \(target)")
            #expect(clicked.cursor == arrowed.cursor, "target \(target)")
        }
    }

    // MARK: - Select All (#4376) and clear

    @Test("select all takes every visible row and anchors at the top")
    func selectAllAnchorsAtTheTop() {
        let result = SelectionGrammar.selectAll(in: Self.ids)
        #expect(result.selection == Set(Self.ids))
        #expect(result.anchor == "a")
        #expect(result.cursor == "e")
    }

    /// The #4376 ↔ #4377 interaction the assignment calls out: after ⌘A a
    /// following ⇧-click must narrow the selection from the top, which only
    /// works because select-all left a usable anchor behind.
    @Test("a shift-click after select all narrows from the first row")
    func shiftClickAfterSelectAllNarrows() {
        let all = SelectionGrammar.selectAll(in: Self.ids)
        let narrowed = SelectionGrammar.click(
            id: "c",
            in: Self.ids,
            selection: all.selection,
            anchor: all.anchor,
            modifiers: [.shift]
        )
        #expect(narrowed.selection == ["a", "b", "c"])
        #expect(narrowed.anchor == "a")
    }

    @Test("select all over an empty list selects nothing and anchors nowhere")
    func selectAllOfNothing() {
        let result = SelectionGrammar.selectAll(in: [])
        #expect(result.selection.isEmpty)
        #expect(result.anchor == nil)
        #expect(result.cursor == nil)
    }

    @Test("clear empties the selection and forgets the anchor")
    func clearForgetsEverything() {
        let result = SelectionGrammar.clear()
        #expect(result.selection.isEmpty)
        #expect(result.anchor == nil)
        #expect(result.cursor == nil)
    }

    // MARK: - Selection is a set of ids, not of row indices

    /// #4377 requires the selection to survive a re-sort. It does so trivially
    /// because it is a set of ids — but the ANCHOR must survive too, which is
    /// what the resolution chain is for: re-order the list and the same anchor
    /// still names the same row.
    @Test("a re-sort keeps the selection and the anchor meaningful")
    func selectionSurvivesAReSort() {
        let resorted = ["e", "d", "c", "b", "a"]
        let result = SelectionGrammar.click(
            id: "a",
            in: resorted,
            selection: ["c"],
            anchor: "c",
            modifiers: [.shift]
        )
        // Visually c → a is now c, b, a.
        #expect(result.selection == ["a", "b", "c"])
        #expect(result.anchor == "c")
    }

    // MARK: - The inspector reads the same rules

    /// There must not be a second implementation of this grammar. The
    /// inspector's entity list keeps its own entry point (different modifier
    /// type, no cursor) but must produce the grammar's answer.
    @Test("the inspector entity reducer agrees with the grammar")
    func inspectorReducerAgreesWithTheGrammar() {
        let cases: [(InspectorEntitySelectionModifiers, Modifiers)] = [
            ([], []),
            ([.command], [.command]),
            ([.shift], [.shift]),
            ([.shift, .command], [.shift, .command]),
        ]
        for (inspectorModifiers, grammarModifiers) in cases {
            let reduced = InspectorEntityBulkSelection.reduceTap(
                tappedId: "d",
                orderedIds: Self.ids,
                selection: ["a", "b"],
                anchor: "b",
                modifiers: inspectorModifiers
            )
            let grammar = SelectionGrammar.click(
                id: "d",
                in: Self.ids,
                selection: ["a", "b"],
                anchor: "b",
                modifiers: grammarModifiers
            )
            #expect(reduced.selection == grammar.selection)
            #expect(reduced.anchor == grammar.anchor)
        }
    }
}
