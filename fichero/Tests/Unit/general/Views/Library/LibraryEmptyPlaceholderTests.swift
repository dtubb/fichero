@testable import Fichero
import Foundation
import Testing

/// #4235 — "the UI waits for data before showing anything".
///
/// The library content area rendered `emptyState` ("No Documents") whenever it
/// held no rows, with no way to tell "this folder IS empty" from "its contents
/// have not arrived yet". So clicking a folder, and dropping a folder onto the
/// app, both flashed the empty state and then relaid out when the data landed —
/// the dead interval the issue is about.
///
/// The precedence is pure so it is testable without a rendered view or a live
/// engine; the view just picks a subview from the answer.
@Suite("Library empty-content placeholder (#4235)")
struct LibraryEmptyPlaceholderTests {

    private func placeholder(
        fetching: Bool = false,
        importing: Bool = false,
        filtering: Bool = false
    ) -> LibraryEmptyPlaceholder {
        LibraryView.emptyCollectionPlaceholder(
            isFetchingContents: fetching,
            isPreparingImport: importing,
            hasFilterText: filtering
        )
    }

    // MARK: - The two cases the issue names

    @Test("selecting a folder shows a loading placeholder, not 'No Documents'")
    func folderSelectionShowsLoading() {
        #expect(placeholder(fetching: true) == .loadingContents)
    }

    /// The window before the engine has a task at all — staging, the folder
    /// grant and the create call all precede `activeIngest`.
    @Test("a registered drop is acknowledged before there is an ingest task")
    func dropIsAcknowledgedImmediately() {
        #expect(placeholder(importing: true) == .importing)
    }

    // MARK: - The case that must NOT change

    @Test("a genuinely empty folder still says it is empty")
    func idleEmptyStaysEmpty() {
        #expect(placeholder() == .empty)
    }

    /// A filter that matches nothing is a real, final answer about rows the app
    /// already has. Hiding it behind a spinner would strand the user with no
    /// "Clear Filter" escape route — the trap `emptyState` exists to avoid.
    @Test("a filter with no matches is never hidden behind a spinner")
    func filterResultOutranksInFlightWork() {
        #expect(placeholder(filtering: true) == .empty)
        #expect(placeholder(fetching: true, filtering: true) == .empty)
        #expect(placeholder(importing: true, filtering: true) == .empty)
    }

    // MARK: - Precedence between the two in-flight states

    /// An import outranks a fetch: it is the thing the user just did, and it is
    /// the reason the fetch will come back non-empty.
    @Test("an import in progress outranks a children fetch")
    func importOutranksFetch() {
        #expect(placeholder(fetching: true, importing: true) == .importing)
    }

    @Test("every placeholder is one of the three states")
    func exhaustive() {
        for fetching in [false, true] {
            for importing in [false, true] {
                for filtering in [false, true] {
                    let result = placeholder(fetching: fetching, importing: importing, filtering: filtering)
                    #expect([.empty, .loadingContents, .importing].contains(result))
                }
            }
        }
    }
}
