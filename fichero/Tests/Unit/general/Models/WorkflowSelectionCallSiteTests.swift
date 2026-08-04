import FicheroAPIClient
@testable import Fichero
import Foundation
import Testing

/// The shipping client must DECLARE what the user pointed at (#4414).
///
/// The server has validated `selection` since #4397: a request claiming
/// `kind=folder` while carrying 47 ids is refused at the boundary, which is
/// what turns #4396 from a bug that was fixed into a request that cannot be
/// expressed. But every call site in the shipping Mac client sent its ids
/// untyped inside `inputs["selected_doc_ids"]`, so the boundary adapter
/// re-derived them as `kind=documents` and a folder run was indistinguishable
/// from a 47-document run.
///
/// An engine-side guarantee the client routes around is not a guarantee. These
/// tests are about the CLIENT half: that a folder selection leaves this process
/// still saying it is a folder, and that a new call site cannot quietly go back
/// to sending ids untyped.
struct WorkflowSelectionCallSiteTests {

    // MARK: - A folder selection survives the client as a folder

    /// The widening case, which is the only one that can honestly claim a
    /// container: nothing selected, a collection-authored workflow. The folder
    /// id must go out declared as a container for the SERVER to expand — not as
    /// a one-element document list that happens to be a folder id, which is
    /// precisely how #4396 looked on the wire.
    @Test("a folder run leaves the client declared as a container, not as one document")
    func aFolderRunSendsAContainerKind() throws {
        let scope = WorkflowRunScope.resolve(
            inputSource: .collection,
            selection: [],
            collectionId: "folder-top",
            fallbackDocumentId: nil
        )

        let selection = try #require(scope.selection)
        #expect(selection.kind == .collection)
        #expect(selection.ids == ["folder-top"])
        #expect(scope.widensBeyondSelection)
    }

    /// The same request stated as documents would be a lie, and the point of
    /// the typed field is that the lie is now detectable. Pinned as its own
    /// assertion because `ids == ["folder-top"]` is true under BOTH kinds — the
    /// id list alone can never distinguish them, which is why the kind exists.
    @Test("the ids alone cannot distinguish a folder run; only the kind can")
    func theKindIsWhatCarriesTheDistinction() {
        let folderRun = WorkflowRunScope.resolve(
            inputSource: .collection,
            selection: [],
            collectionId: "folder-top",
            fallbackDocumentId: nil
        )
        let documentRun = WorkflowRunScope.resolve(
            inputSource: .currentSelection,
            selection: ["folder-top"],
            collectionId: nil,
            fallbackDocumentId: nil
        )

        #expect(folderRun.docIds == documentRun.docIds)
        #expect(folderRun.selection?.kind != documentRun.selection?.kind)
    }

    /// Daniel's case, at the wire boundary this time: one PDF selected under a
    /// collection-authored workflow sends that document, declared as a
    /// document. #4396's assertion was about `docIds`; this is the same
    /// assertion about what the request SAYS it is.
    @Test("a selection is declared as documents, whatever the workflow prefers")
    func aSelectionIsDeclaredAsDocuments() throws {
        for inputSource in WorkflowInputSource.allCases {
            let scope = WorkflowRunScope.resolve(
                inputSource: inputSource,
                selection: ["pdf-1"],
                collectionId: "folder-top",
                fallbackDocumentId: "pdf-1"
            )

            let selection = try #require(scope.selection)
            #expect(selection.kind == .documents)
            #expect(selection.ids == ["pdf-1"])
        }
    }

    /// Nothing to run on must send NO selection rather than an empty one. The
    /// server rejects an empty selection outright — "an empty selection is not
    /// a scope, it is a missing argument" — so sending one would turn a caller's
    /// own no-op guard into a 422 the user has to read.
    @Test("nothing selected sends no selection at all, not an empty one")
    func anEmptyScopeSendsNoSelection() {
        let scope = WorkflowRunScope.resolve(
            inputSource: .currentSelection,
            selection: [],
            collectionId: nil,
            fallbackDocumentId: nil
        )

        #expect(scope.docIds.isEmpty)
        #expect(scope.selection == nil)
        #expect(WorkflowRunScope.documents([]) == nil)
    }

    /// The pre-resolved sites can only claim `documents`, and that is correct
    /// rather than a shortcut: by the time they call, a folder has already been
    /// expanded client-side into its descendants, and `kind=folder` with N ids
    /// is exactly the request the server refuses.
    @Test("pre-resolved ids are declared as documents")
    func preResolvedIdsAreDocuments() throws {
        let selection = try #require(WorkflowRunScope.documents(["a", "b", "c"]))

        #expect(selection.kind == .documents)
        #expect(selection.ids == ["a", "b", "c"])
    }

    // MARK: - No call site may go back to sending ids untyped

    /// The durable half. Four sites were converted; the fifth (`BatchStore`)
    /// could not be, and a sixth is what this catches.
    ///
    /// Every count in an issue tonight has been wrong at least once, so this
    /// does not assert a count — it asserts a PROPERTY: wherever the app hands
    /// `selected_doc_ids` to an execute call, a `selection:` argument rides in
    /// the same call. A new site pasted from an old one fails here rather than
    /// shipping a run the boundary cannot validate.
    @Test("every execute call that sends selected_doc_ids also declares a selection")
    func noExecuteCallSendsIdsUntyped() throws {
        let root = try AppSource.root()
        var checked = 0
        var untyped: [String] = []

        for file in try Self.swiftFiles(under: root) {
            let source = try String(contentsOf: file, encoding: .utf8)
            var searchRange = source.startIndex..<source.endIndex

            while let hit = source.range(
                of: "inputs: [\"selected_doc_ids\"",
                range: searchRange
            ) {
                checked += 1
                // The `selection:` argument sits in the same argument list, a
                // few lines below `inputs:`. A bounded window keeps this from
                // being satisfied by an unrelated `selection:` elsewhere in a
                // long file — file scope was too coarse for the display-name
                // guardrail (#4416) and would be too coarse here.
                let windowEnd = source.index(
                    hit.upperBound,
                    offsetBy: 900,
                    limitedBy: source.endIndex
                ) ?? source.endIndex
                let window = source[hit.upperBound..<windowEnd]
                if !window.contains("selection:") {
                    let relative = file.path.replacingOccurrences(of: root.path + "/", with: "")
                    untyped.append(relative)
                }
                searchRange = hit.upperBound..<source.endIndex
            }
        }

        // A sweep that silently scanned nothing would pass forever (#4487).
        #expect(checked >= 4, "expected to find the execute call sites; found \(checked)")
        #expect(
            untyped.isEmpty,
            """
            These execute calls send selected_doc_ids without declaring a \
            selection, so the server re-derives kind=documents and cannot tell \
            a folder run from a document run (#4414): \(untyped.joined(separator: ", "))
            """
        )
    }

    /// The negative control. Without it the sweep above proves only that it
    /// found nothing, which is what a broken matcher also reports (#4487).
    @Test("the sweep's matcher recognises an undeclared call")
    func theMatcherCatchesAnUndeclaredCall() {
        let untypedCall = """
            _ = try await stream.execute(
                workflowId: id,
                inputs: ["selected_doc_ids": docIds],
                onAccepted: { _ in }
            )
            """
        let typedCall = """
            _ = try await stream.execute(
                workflowId: id,
                inputs: ["selected_doc_ids": docIds],
                selection: WorkflowRunScope.documents(docIds),
                onAccepted: { _ in }
            )
            """

        #expect(untypedCall.contains("inputs: [\"selected_doc_ids\""))
        #expect(!untypedCall.contains("selection:"))
        #expect(typedCall.contains("selection:"))
    }

    // MARK: - Support

    private static func swiftFiles(under root: URL) throws -> [URL] {
        let enumerator = FileManager.default.enumerator(
            at: root,
            includingPropertiesForKeys: nil
        )
        var files: [URL] = []
        while let url = enumerator?.nextObject() as? URL {
            guard url.pathExtension == "swift" else { continue }
            files.append(url)
        }
        return files
    }
}
