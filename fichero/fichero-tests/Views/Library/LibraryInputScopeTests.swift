@testable import Fichero
import Foundation
import Testing

/// #4412, first row of the input-grammar table: the row keyboard grammar was
/// applied to EVERY view mode.
///
/// `withKeyboardShortcuts` wraps `libraryContent` as a whole, so arrows,
/// type-ahead, Return-to-open and Space-to-preview were live on the canvas and
/// in 3D. An arrow key there moved the LIST selection while the user was
/// looking at a spatial arrangement — the app changed state behind their back,
/// with no visible cause, and they found out later.
///
/// That is worse than the feature being absent: a missing key does nothing and
/// says so. These tests pin which modes may service row semantics.
struct LibraryInputScopeTests {

    // MARK: - The defect, stated directly

    /// The reported harm: spatial modes must not answer row-ordinal keys.
    @Test("spatial modes do not service the row keyboard grammar")
    func spatialModesDoNotServiceRowKeys() {
        #expect(!LibraryView.servicesRowKeyboardGrammar(.canvas))
        #expect(!LibraryView.servicesRowKeyboardGrammar(.space))
    }

    /// The modes with an ordered list of rows keep it — arrows and type-ahead
    /// mean something there, and removing a key that WORKS is its own bug.
    @Test("ordered modes keep the row grammar")
    func orderedModesKeepTheRowGrammar() {
        for mode in [ViewDisplayMode.icon, .list, .table, .columns] {
            #expect(LibraryView.servicesRowKeyboardGrammar(mode), Comment(rawValue: "\(mode)"))
        }
    }

    /// Every mode answers, and the answer is stable — a mode that is neither
    /// clearly ordered nor clearly spatial must still have been DECIDED, not
    /// left to inherit whatever the wrapper happened to do.
    @Test("every display mode has an explicit answer")
    func everyModeHasAnExplicitAnswer() {
        for mode in ViewDisplayMode.allCases {
            let first = LibraryView.servicesRowKeyboardGrammar(mode)
            #expect(LibraryView.servicesRowKeyboardGrammar(mode) == first,
                    Comment(rawValue: "\(mode) is not deterministic"))
        }
    }

    /// The property that keeps this from regressing as modes are added: the
    /// spatial set and the row-grammar set cannot overlap. A future mode that
    /// is spatial must not also claim row semantics.
    @Test("no mode is both spatial and row-keyed")
    func noModeIsBothSpatialAndRowKeyed() {
        for mode in ViewDisplayMode.allCases where mode != .workspace {
            let spatial = LibraryView.usesSpatialProjection(mode)
            let rowKeyed = LibraryView.servicesRowKeyboardGrammar(mode)
            #expect(!(spatial && rowKeyed), Comment(rawValue: "\(mode) claims both"))
        }
    }

    // MARK: - What is deliberately NOT scoped away

    /// Delete and the focused menu actions stay in every mode. They act on the
    /// SELECTION, which is shared across modes and meaningful on a canvas —
    /// only the row-ORDINAL handlers are meaningless there.
    @Test("delete and focused actions survive in spatial modes")
    func deleteAndFocusedActionsSurvive() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/Views/Library/LibraryView+KeyboardShortcuts.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")

        // Bounded to the else BLOCK, not "everything after it": the private
        // `applyArrowKeyHandlers` / `applyPrimaryKeyHandlers` definitions live
        // further down the same file, so an unbounded split finds them and
        // reports the opposite of the truth.
        let elseBranch = source
            .components(separatedBy: "} else {")[1]
            .components(separatedBy: "\n    }")[0]
        #expect(elseBranch.contains("applyDeleteConfirmation"))
        #expect(elseBranch.contains("applyFocusedActions"))
        // The row-ordinal handlers are the ones that must NOT be there.
        #expect(!elseBranch.contains("applyArrowKeyHandlers"))
        #expect(!elseBranch.contains("applyPrimaryKeyHandlers"))
    }
}
