@testable import Fichero
import Foundation
import Testing

/// Source guards for the per-row work that made list-mode scrolling feel slow
/// (Daniel, 2026-09-01).
///
/// Every finding here is a value that does not depend on the row being drawn,
/// recomputed inside the `ForEach` anyway. That is not something a unit test can
/// observe from a pure function — it is a fact about where an expression sits —
/// so the guard reads the source, the same instrument
/// `LibraryActivityAgreementTests` uses for the rule it pins.
@Suite("List rows do no per-row work that belongs to the pass")
@MainActor  // reaches LibraryActivityIndicator's View statics (#4201)
struct ListRowPerRowWorkTests {

    private static func appSource(_ relativePath: String) throws -> String {
        let source = try AppSource.text(relativePath)
        #expect(!source.isEmpty, "\(relativePath) is empty — this guard measures nothing")
        return source
    }

    /// The icon grid's 2026-08-31 fix, which list mode never got: the raw
    /// `@AppStorage` string must not be re-split into a `Set` per document.
    @Test("row-wide settings are resolved once per pass, not per row")
    func rowChromeIsHoisted() throws {
        let list = try Self.appSource("Views/Library/ViewModes/List/LibraryView+ListView.swift")

        // Exactly ONE derivation of each, in `listRowChrome`.
        #expect(
            list.components(separatedBy: "LibraryRowAttribute.set(from: rowAttributesRaw)").count - 1 == 1,
            """
            the attribute CSV is being parsed more than once. It does not depend \
            on the row — hoist it into `listRowChrome` and thread it down.
            """
        )
        #expect(
            list.components(separatedBy: "entityTypes: listVisibleEntityTypes").count - 1 == 1,
            """
            `listVisibleEntityTypes` is being derived more than once. It reads \
            @AppStorage (a UserDefaults read) and builds two Sets — once per \
            pass, never per row.
            """
        )
        #expect(list.contains("struct ListRowChrome"))
        #expect(list.contains("private func documentRow(_ doc: Document, _ chrome: ListRowChrome)"))
    }

    /// The O(N²) first pass: `childActivityCounts` is memoised per PARENT id,
    /// so a folder of N rows is N cache misses, each scanning every document.
    /// A row that cannot hold children must not ask.
    @Test("only containers ask the store for child activity")
    func leafRowsSkipTheChildScan() throws {
        let indicator = try Self.appSource("Views/Library/LibraryActivityIndicator.swift")
        #expect(
            indicator.contains("guard document.isNavigableContainer else"),
            """
            the leaf fast path is gone. Every list row then pays a \
            `childActivityCounts` cache miss — O(all documents) each — on the \
            first pass after any store revision, which is every refresh and \
            every live-delivery splice.
            """
        )
        // Both entry points must share one resolution, or the indicator and the
        // call site that decides whether to mount it can disagree.
        #expect(indicator.contains("static func activity(for document: Document, in store: DocumentStore)"))
        #expect(
            indicator.components(separatedBy: "childActivityCounts(of:").count - 1 == 1,
            "more than one place asks the store — they will drift"
        )
    }

    /// A leaf row must read no `DocumentStore` property at all: `MailStyleRow`
    /// takes the store from the environment and it is `@Observable`, so
    /// touching one of its properties enrols every visible row as a dependent
    /// and any store change re-runs every row's body regardless of `.equatable()`.
    @Test("the shared resolver is the only store read on the row path")
    func rowsDoNotReadTheStoreDirectly() throws {
        let components = try Self.appSource("Views/Library/LibraryViewComponents.swift")
        #expect(
            !components.contains("documentStore.childActivityCounts"),
            "the row went back to asking the store itself instead of through the resolver"
        )
        #expect(components.contains("LibraryActivityIndicator.isIdle(document, in: documentStore)"))
    }

    /// Three calls to the same title ladder per row, for one string.
    @Test("the row resolves its display name once")
    func displayNameResolvedOnce() throws {
        let components = try Self.appSource("Views/Library/LibraryViewComponents.swift")
        let mailRow = try #require(
            components.range(of: "struct MailStyleRow: View {")
        ).upperBound
        let end = try #require(
            components.range(of: "// MARK: - Document Thumbnail", range: mailRow ..< components.endIndex)
        ).lowerBound
        let body = String(components[mailRow ..< end])
        #expect(
            body.components(separatedBy: "DocumentTitle.displayName(for: document)").count - 1 == 1,
            "MailStyleRow is resolving its title more than once per row"
        )
    }
}
