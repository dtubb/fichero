@testable import Fichero
import Foundation
import Testing

/// #4348: an artifact save fires an event, `scheduleReload()` runs, the engine
/// dies mid-fetch — and a correct list of artifacts was replaced by "nothing
/// here" under an error banner.
///
/// The catch block returned early only for cancellations, so a **transport**
/// failure fell through to `items = []`. Nothing was destroyed server-side; the
/// app simply stopped being able to ask and reported that as absence. Reporting
/// absence when the truth is ignorance is the lie #4283 fixed for the library.
///
/// The fix is not the deletion of that line. Both stores assign their new scope
/// BEFORE awaiting the fetch, so unconditionally keeping the rows would leave
/// document A's artifacts under document B's heading after a failed switch —
/// a false attribution, which is worse than a false emptiness because it looks
/// right. So the rows survive only while they still describe the scope on
/// screen, and that is what this suite pins.
struct StaleDataPolicyTests {

    // MARK: - The defect, stated directly

    /// Daniel's case: rows are loaded and correct, the engine dies, the reload
    /// fails with a transport error. The rows must stay.
    @Test("a transport failure on the loaded scope keeps the rows")
    func transportFailureKeepsTheRows() {
        let policy = StaleDataPolicy.onFailure(
            isCancellation: false,
            loadedScope: "doc-marshall",
            requestedScope: "doc-marshall"
        )
        #expect(policy == .keepStale)
        #expect(policy != .clear, "clearing is what turned a correct list into 'nothing here'")
    }

    /// The rule generalised: for a scope that has loaded once, no failure of any
    /// kind may empty it. This is the assertion that makes the regression
    /// structurally impossible rather than merely fixed.
    @Test("no failure can ever empty a scope that has already loaded")
    func aLoadedScopeIsNeverEmptied() {
        for scope in ["doc-1", "doc-2|true", ""] {
            let policy = StaleDataPolicy.onFailure(
                isCancellation: false,
                loadedScope: scope,
                requestedScope: scope
            )
            #expect(policy != .clear, Comment(rawValue: scope))
        }
    }

    // MARK: - Cancellation is still handled separately

    /// A cancellation is a supersede, not a failure: a newer request already
    /// owns the store, so touching ANY state — including the error — would
    /// stamp on it.
    @Test("a cancellation touches nothing, whatever the scope")
    func cancellationTouchesNothing() {
        for loaded in [nil, "doc-1", "doc-2"] as [String?] {
            let policy = StaleDataPolicy.onFailure(
                isCancellation: true,
                loadedScope: loaded,
                requestedScope: "doc-1"
            )
            #expect(policy == .ignore, Comment(rawValue: loaded ?? "nil"))
        }
    }

    // MARK: - The trap the one-line fix would have opened

    /// The reason this is a policy and not a deletion. The store sets its new
    /// scope before awaiting, so on a failed switch the rows in memory belong
    /// to the PREVIOUS document. Keeping them would label one document's
    /// artifacts as another's.
    @Test("rows belonging to another scope are cleared, not shown")
    func rowsFromAnotherScopeAreCleared() {
        let policy = StaleDataPolicy.onFailure(
            isCancellation: false,
            loadedScope: "doc-A",
            requestedScope: "doc-B"
        )
        #expect(policy == .clear)
        #expect(policy != .keepStale, "showing doc-A's artifacts under doc-B is a worse lie than empty")
    }

    /// Nothing has ever loaded, so there is nothing true to preserve. Empty is
    /// the honest state — accompanied by the error, which the stores set on
    /// every non-ignore path.
    @Test("a first-ever load that fails has nothing to keep")
    func firstLoadFailureHasNothingToKeep() {
        #expect(
            StaleDataPolicy.onFailure(
                isCancellation: false, loadedScope: nil, requestedScope: "doc-1"
            ) == .clear
        )
    }

    /// `includeDescendants` changes which rows are correct for the same
    /// document, so it is part of scope identity — otherwise the Content tab's
    /// rows could persist into the Artifacts tab's narrower scope.
    @Test("the same document at a different depth is a different scope")
    func descendantDepthIsPartOfScopeIdentity() {
        #expect(
            StaleDataPolicy.onFailure(
                isCancellation: false, loadedScope: "doc-1|true", requestedScope: "doc-1|false"
            ) == .clear
        )
    }

    // MARK: - Structural: the wipe is gone from both stores

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// Source with comment lines removed.
    ///
    /// A structural test that greps raw source cannot tell code from prose, so
    /// a comment *explaining* a defect reads as the defect still being present.
    /// The comments below deliberately name `!items.isEmpty` to record why the
    /// guard changed — which is exactly the text the assertion looks for.
    private static func codeOnly(_ source: String) -> String {
        source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    /// Both stores must route their catch through the shared policy. Anchored
    /// on the call form, so a comment merely naming `StaleDataPolicy` does not
    /// satisfy it.
    @Test("both reported stores decide through the one shared policy")
    func bothStoresUseTheSharedPolicy() throws {
        for file in ["Models/ArtifactStore.swift", "Models/InterpretationStore.swift"] {
            let source = try Self.appSource(file)
            #expect(source.contains("StaleDataPolicy.onFailure("), Comment(rawValue: file))
            #expect(source.contains("case .keepStale:"), Comment(rawValue: file))
            #expect(source.contains("loadedScope = nil"), Comment(rawValue: file))
        }
    }

    /// The idempotence guard had to move with the fix. `!items.isEmpty` meant
    /// "already loaded" only while a failure emptied the list; now that rows
    /// survive a failure, a scope whose fetch failed would never be retried.
    @Test("scope idempotence guards on what loaded, not on emptiness")
    func idempotenceGuardsOnLoadedScope() throws {
        for file in ["Models/ArtifactStore.swift", "Models/InterpretationStore.swift"] {
            let source = try Self.codeOnly(Self.appSource(file))
            let setScope = source.components(separatedBy: "func setScope(")[1]
            let body = setScope.components(separatedBy: "await reload()")[0]
            #expect(!body.contains("!items.isEmpty"), Comment(rawValue: file))
            #expect(body.contains("loadedScope =="), Comment(rawValue: file))
        }
    }

    /// `loadedScope` records SUCCESS. If it were assigned before or regardless
    /// of the fetch it would always equal the requested scope, and every
    /// failure would read as `keepStale` — including the cross-document one.
    @Test("the loaded scope is recorded only after a successful fetch")
    func loadedScopeIsRecordedOnlyOnSuccess() throws {
        for file in ["Models/ArtifactStore.swift", "Models/InterpretationStore.swift"] {
            let source = try Self.appSource(file)
            let reload = source.components(separatedBy: "func reload() async {")[1]
            let doBlock = reload.components(separatedBy: "} catch {")[0]
            #expect(doBlock.contains("loadedScope ="), Comment(rawValue: "\(file): not set on success"))
            let assignIndex = doBlock.range(of: "loadedScope =")
            let fetchIndex = doBlock.range(of: "try await")
            #expect(assignIndex != nil && fetchIndex != nil)
            if let assignIndex, let fetchIndex {
                #expect(
                    fetchIndex.lowerBound < assignIndex.lowerBound,
                    Comment(rawValue: "\(file): scope recorded before the fetch could fail"))
            }
        }
    }
}
