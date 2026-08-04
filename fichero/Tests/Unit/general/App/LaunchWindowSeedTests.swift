@testable import Fichero
import XCTest

/// #4017 — macOS launch showed "Create a new library or open an existing one"
/// before it would show the app.
///
/// `LibraryWindow.init` seeded `WindowState(libraryId: UUID())` — a fresh random
/// id that `LibraryManager.getLibrary(id:)` can never resolve. So
/// `windowState.library` was nil on the first frame of every launch, and the
/// window rendered `noLibraryView`. iOS seeded `globalLibraryId` and had no such
/// screen.
///
/// Two platforms seeding one window differently, with nothing forcing them to
/// agree — which is why only one of them had the wall in front of it.
/// `@MainActor` because `WindowState` is: constructing one and reading
/// `library` are both main-actor work, and the launch path this describes runs
/// there. Hopping per-assertion instead would let the test observe a state the
/// app never sees.
@MainActor
final class LaunchWindowSeedTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertFalse(source.isEmpty, "\(relativePath) is empty — this guard measures nothing")
        return source
    }

    // MARK: - The behaviour

    /// The seeded id must be one that actually resolves.
    ///
    /// A random UUID satisfies "a window has a library id" perfectly and
    /// resolves to nothing — the gap between having an id and having a LIBRARY
    /// is the entire bug.
    func testTheGlobalLibraryIdIsStableAndNotRandom() {
        XCTAssertEqual(
            LibraryManager.globalLibraryId,
            LibraryManager.globalLibraryId,
            "the seed must be a fixed id; a fresh UUID per call is what produced the prompt"
        )
    }

    func testAWindowSeededWithTheGlobalIdCarriesThatId() {
        let state = WindowState(libraryId: LibraryManager.globalLibraryId)

        XCTAssertEqual(state.libraryId, LibraryManager.globalLibraryId)
    }

    /// The negative case, stated so the distinction is on the record: a random
    /// id is not merely "a different library", it is NO library.
    func testARandomlySeededWindowResolvesToNoLibrary() {
        let state = WindowState(libraryId: UUID())

        XCTAssertNil(
            state.library,
            "a random id resolves to nothing — this is what rendered noLibraryView"
        )
    }

    // MARK: - The two platforms must agree

    /// Structural, because the defect was a DIVERGENCE rather than a wrong
    /// value: each file was locally reasonable and they disagreed.
    func testMacAndIOSSeedTheWindowTheSameWay() throws {
        let mac = try Self.appSource("App/LibraryWindow.swift")
        let ios = try Self.appSource("FicheroApp_iOS.swift")

        XCTAssertTrue(
            mac.contains("WindowState(libraryId: LibraryManager.globalLibraryId)"),
            "macOS must seed the global library, as iOS does"
        )
        XCTAssertTrue(
            ios.contains("WindowState(libraryId: LibraryManager.globalLibraryId)"),
            "iOS is the reference — if this fails, check which platform moved"
        )
    }

    // MARK: - First-run presents only over a VERIFIED-empty library (#4017b)

    private func inbox() -> Document {
        Document(docType: .folder, name: "Inbox")
    }

    private func realDocument() -> Document {
        Document(docType: .file, name: "1893 diary.pdf")
    }

    /// The requirement that makes this gate better than the flag it replaces:
    /// NOT LOADED is not EMPTY. Onboarding during load would be the same bug
    /// wearing a better gate — an absence read as an answer.
    func testAnUnloadedLibraryIsNeverTreatedAsEmpty() {
        XCTAssertFalse(libraryIsLoadedAndEmpty(isLoaded: false, rootCollections: []))
        XCTAssertFalse(libraryIsLoadedAndEmpty(isLoaded: false, rootCollections: [inbox()]))
        XCTAssertFalse(
            libraryIsLoadedAndEmpty(isLoaded: false, rootCollections: [realDocument()]),
            "an unloaded library says nothing about its contents, whatever happens to be cached"
        )
    }

    /// The case that would have made this a silent no-op.
    ///
    /// `ensureInboxFolder` runs on every successful load, so a loaded library
    /// ALWAYS has at least the Inbox and `collections.isEmpty` is never true.
    /// Gating on emptiness-by-count would mean the sheet never presents at all
    /// — a fix that reads as done and does nothing.
    func testAFreshLibraryWithOnlyItsInboxCountsAsEmpty() {
        XCTAssertTrue(
            libraryIsLoadedAndEmpty(isLoaded: true, rootCollections: [inbox()]),
            "every loaded library has an Inbox; requiring zero collections never fires"
        )
    }

    func testALibraryWithRealContentIsNotEmpty() {
        XCTAssertFalse(
            libraryIsLoadedAndEmpty(isLoaded: true, rootCollections: [inbox(), realDocument()])
        )
        XCTAssertFalse(libraryIsLoadedAndEmpty(isLoaded: true, rootCollections: [realDocument()]))
    }

    /// A genuinely empty library — loaded, and nothing at all — still counts.
    /// `allSatisfy` is vacuously true on an empty array, which is the right
    /// answer here only BECAUSE `isLoaded` was already checked above it.
    func testALoadedLibraryWithNothingAtAllCountsAsEmpty() {
        XCTAssertTrue(libraryIsLoadedAndEmpty(isLoaded: true, rootCollections: []))
    }

    /// Only the ROOT Inbox is ignored. A folder called "Inbox" nested inside
    /// something is real user content that happens to share a name.
    func testANestedFolderNamedInboxIsRealContent() {
        var nested = Document(docType: .folder, name: "Inbox")
        nested.parentId = "some-parent"

        XCTAssertFalse(libraryIsLoadedAndEmpty(isLoaded: true, rootCollections: [nested]))
    }

    /// The sheet must actually consult this. A predicate nothing calls is the
    /// #4473 shape, and it would leave the flag-only gate live.
    func testTheFirstRunSheetIsGatedOnIt() throws {
        let window = try Self.appSource("App/LibraryWindow.swift")

        XCTAssertTrue(window.contains("libraryIsLoadedAndEmpty("))
        XCTAssertTrue(
            window.contains("loadedLibraryIds.contains(windowState.libraryId)"),
            "loaded-ness must come from the verified set, not be inferred"
        )
    }

    // MARK: - Could this pass while the app still shows the prompt?

    /// The honest answer to that question was YES, until this test.
    ///
    /// The tests above assert the SEED. They say nothing about the assignments
    /// that follow it, so a later path assigning an id that resolves to nothing
    /// would bring the prompt straight back with all of them still green — the
    /// #4473 shape, in my own work.
    ///
    /// So this asserts the launch sequence's actual invariant: `libraryId` is
    /// only ever written to the global id, or through `assignLibrary`, and
    /// every `assignLibrary` call site is guarded by a `getLibrary(id:) != nil`
    /// check. That is what makes `noLibraryView` unreachable rather than merely
    /// un-rendered today.
    func testEveryWriteToTheWindowsLibraryIdIsGuaranteedToResolve() throws {
        let actions = try Self.appSource("App/LibraryWindow+Actions.swift")

        // Every guarded assignment funnels through this one setter...
        XCTAssertTrue(
            actions.contains("func assignLibrary(id: UUID)"),
            "the single assignment path must exist"
        )
        // ...and each of its callers checks the library resolves first.
        for guardExpr in [
            "libraryManager.getLibrary(id: pendingId) != nil",
            "libraryManager.getLibrary(id: restoredId) != nil",
            "libraryManager.getLibrary(id: currentId) != nil"
        ] {
            XCTAssertTrue(
                actions.contains(guardExpr),
                "an unguarded assignLibrary call can reintroduce the prompt: missing \(guardExpr)"
            )
        }

        // The only DIRECT write outside that path targets the global id, which
        // always resolves — LibraryManager inserts Global during its own init
        // and the one `removeAll` of it re-inserts the same id in the next
        // statement (a swap, not a removal), so it is never absent.
        // `windowState.libraryId ==` is a COMPARISON, not an assignment, and my
        // first version of this filter counted one as a write and failed on
        // correct code. Same over-broad-match mistake as the #4095 badge test:
        // right about the symptom, wrong about the boundary.
        let directWrites = actions
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { $0.contains("windowState.libraryId =") && !$0.contains("windowState.libraryId ==") }

        for write in directWrites {
            XCTAssertTrue(
                write.contains("LibraryManager.globalLibraryId") || write.contains("= id"),
                "direct write to libraryId that may not resolve: \(write)"
            )
        }
        XCTAssertFalse(directWrites.isEmpty, "found no assignments at all — this guard went blind")
    }

    /// `noLibraryView` still EXISTS as a fallback, and that is fine — but if it
    /// is ever reachable again on launch, this issue is back. Pinned so the
    /// fallback cannot quietly become the normal path a second time.
    func testTheCreateOrOpenPromptIsAFallbackNotTheLaunchState() throws {
        let window = try Self.appSource("App/LibraryWindow.swift")

        XCTAssertTrue(window.contains("noLibraryView"), "the fallback may exist")
        XCTAssertTrue(
            window.contains("WindowState(libraryId: LibraryManager.globalLibraryId)"),
            "but launch must seed a library that resolves, so the fallback is not what launch shows"
        )
    }

    /// The specific regression: `UUID()` as a seed must not come back.
    ///
    /// Narrow on purpose. `UUID()` is legitimate almost everywhere, so this
    /// bans it only in the window-seed expression rather than in the file.
    func testTheWindowIsNeverSeededWithAFreshUUID() throws {
        let mac = try Self.appSource("App/LibraryWindow.swift")

        XCTAssertFalse(
            mac.contains("WindowState(libraryId: UUID())"),
            "a random seed resolves to no library and renders the create/open prompt (#4017)"
        )
    }
}
