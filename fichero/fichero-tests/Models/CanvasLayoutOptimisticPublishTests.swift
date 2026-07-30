@testable import Fichero
import Foundation
import Testing

/// #4410: dragging an item in the 3D view reset its position.
///
/// `saveLayout` assigned `layouts[folderId]` only from the SERVER echo, so the
/// store held the pre-drag position for the whole round trip. Meanwhile
/// `dispatch` ran `dragEnded` in an unawaited `Task`, and `.onEnded` mutated
/// `@State` immediately — invalidating the view, running `RealityView`'s
/// `update:`, and reconciling the scene from a store that had not been told
/// anything had moved.
///
/// Whether the stale value landed depended on which of two schedulers won, so
/// the defect was intermittent and every individual component read as correct.
///
/// The fix is not to reorder the readers. It is that the write went out and the
/// local model never heard about it — so the store publishes the new value
/// before the network call, and no reader has to know a window exists.
///
/// These tests pin the ordering rules the source has to keep, since the race
/// itself cannot be reproduced deterministically in a unit test.
struct CanvasLayoutOptimisticPublishTests {

    private static func storeSource() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/Models/CanvasLayoutStore.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// The body of `saveLayout`, with comment lines removed.
    ///
    /// Stripping is load-bearing here, not tidiness: the comments in that
    /// function deliberately explain the ordering rule and therefore contain
    /// the words "await" and "optimistic". A raw search finds the explanation
    /// before the code and reports the opposite of the truth.
    private static func saveLayoutBody() throws -> String {
        let source = try storeSource()
        let body = source.components(separatedBy: "func saveLayout(")[1]
            .components(separatedBy: "\n    /// Undo an optimistic publish")[0]
        return body
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    // MARK: - The invariant

    /// The one that makes the race impossible rather than unlikely: the store
    /// takes the new value BEFORE any `await`. If that holds, no reader can
    /// ever observe a stale layout, whatever order things run in.
    @Test("the store publishes the new layout before any network await")
    func publishHappensBeforeAnyAwait() throws {
        let body = try Self.saveLayoutBody()

        let publish = try #require(body.range(of: "layouts[folderId] = items"))
        let firstAwait = try #require(body.range(of: "await"))

        #expect(
            publish.lowerBound < firstAwait.lowerBound,
            "an optimistic publish after the await is not optimistic — it is the bug"
        )
    }

    /// The old shape, gone: the echo was the ONLY assignment, so the store was
    /// stale for the whole request.
    @Test("the echo is no longer the only thing that writes the store")
    func echoIsNotTheOnlyWrite() throws {
        let body = try Self.saveLayoutBody()
        let writes = body.components(separatedBy: "layouts[folderId] =").count - 1
        #expect(writes >= 2, "expected an optimistic write AND a reconciling echo")
    }

    // MARK: - The echo reconciles rather than asserts

    /// The server may legitimately return something different — clamping,
    /// snapping, another client's edit — so its answer is applied, not assumed
    /// to match what was sent.
    @Test("the server echo is still applied when it lands")
    func echoStillReconciles() throws {
        let body = try Self.saveLayoutBody()
        #expect(body.contains("CanvasItemLayout.init(schema:)"))
        #expect(body.contains("saveSequence[folderId] == sequence"))
    }

    /// Two quick drags: the later position must win. Without a sequence guard
    /// the FIRST echo to arrive overwrites the newer local value, and the drag
    /// the user actually finished on is the one that disappears.
    @Test("a stale echo cannot overwrite a newer save")
    func staleEchoCannotOverwrite() throws {
        let source = try Self.storeSource()
        #expect(source.contains("private var saveSequence: [String: Int]"))

        let body = try Self.saveLayoutBody()
        let claim = try #require(body.range(of: "saveSequence[folderId] = sequence"))
        let guardCheck = try #require(body.range(of: "if saveSequence[folderId] == sequence"))
        #expect(claim.lowerBound < guardCheck.lowerBound, "a save must claim its number before checking it")
    }

    // MARK: - Failure is loud, never silent

    /// An optimistic value left in place after a failed save looks saved and
    /// silently disagrees with the server. Every failure path restores AND
    /// reports.
    @Test("every failure path rolls back and sets an error")
    func failuresRollBackAndReport() throws {
        let body = try Self.saveLayoutBody()

        for branch in ["case .unprocessableContent", "case .undocumented", "} catch {"] {
            let tail = body.components(separatedBy: branch)[1]
            let untilNext = tail.components(separatedBy: "case .")[0]
            #expect(untilNext.contains("rollBack("), Comment(rawValue: "\(branch) does not roll back"))
            #expect(untilNext.contains("loadError ="), Comment(rawValue: "\(branch) rolls back silently"))
        }
    }

    /// A cancellation is a supersede, not a failure: a newer save already holds
    /// the store, and rolling back would drag the card out from under it.
    @Test("a superseded save does not roll back")
    func supersededSaveDoesNotRollBack() throws {
        let body = try Self.saveLayoutBody()
        let catchBlock = body.components(separatedBy: "} catch {")[1]
        let beforeRollback = catchBlock.components(separatedBy: "rollBack(")[0]
        #expect(beforeRollback.contains("isCancellationError"))
        #expect(beforeRollback.contains("return false"), "the cancellation path must return before rolling back")
    }

    /// Rollback is itself sequence-guarded, or a slow failure would undo a
    /// newer successful drag.
    @Test("rollback skips when a newer save owns the store")
    func rollbackIsSequenceGuarded() throws {
        let source = try Self.storeSource()
        let rollback = source.components(separatedBy: "private func rollBack(")[1]
        #expect(rollback.contains("guard saveSequence[folderId] == sequence else { return }"))
    }
}
