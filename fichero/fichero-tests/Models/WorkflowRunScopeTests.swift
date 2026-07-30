@testable import Fichero
import Foundation
import Testing

/// #4396 (P0): running Catalogue on one selected PDF ran it over the whole
/// folder, silently curating archival material nobody chose.
///
/// The reported cause — `runWorkflowOnCollection` — was not it: that function
/// had **no callers**. The real path was
/// `WorkflowEditor.resolveSelectedDocumentIds()`, which for a workflow authored
/// `inputSource == .collection` returned the FOLDER id and never consulted the
/// selection. `.collection` is the default in `Workflow.init`, in
/// `WorkflowDefinition.init`, and in the decoder's `?? .collection`, so that is
/// the normal case, not an edge one.
///
/// These are the request-boundary assertions: the ids that would be sent as
/// `selected_doc_ids` must match what the UI claimed, and no path may silently
/// widen scope.
struct WorkflowRunScopeTests {

    private func resolve(
        inputSource: WorkflowInputSource,
        selection: [String] = [],
        collectionId: String? = nil,
        fallbackDocumentId: String? = nil
    ) -> WorkflowRunScope.Resolution {
        WorkflowRunScope.resolve(
            inputSource: inputSource,
            selection: selection,
            collectionId: collectionId,
            fallbackDocumentId: fallbackDocumentId
        )
    }

    // MARK: - The P0, stated directly

    /// Daniel's exact case: one PDF selected, a collection-authored workflow.
    /// It must send that one id, not the folder.
    @Test("a collection-authored workflow with one document selected sends that document")
    func collectionWorkflowHonoursASingleSelection() {
        let scope = resolve(
            inputSource: .collection,
            selection: ["pdf-1"],
            collectionId: "folder-top",
            fallbackDocumentId: "pdf-1"
        )
        #expect(scope.docIds == ["pdf-1"])
        #expect(scope.docIds != ["folder-top"])
        #expect(!scope.widensBeyondSelection)
    }

    /// The rule generalised: a selection wins for BOTH input sources. The
    /// authored preference can no longer override an explicit instruction.
    @Test("a selection always wins, whatever the workflow was authored to prefer")
    func selectionAlwaysWins() {
        for inputSource in WorkflowInputSource.allCases {
            let scope = resolve(
                inputSource: inputSource,
                selection: ["a", "b"],
                collectionId: "folder",
                fallbackDocumentId: "z"
            )
            #expect(scope.docIds == ["a", "b"], "\(inputSource)")
            #expect(!scope.widensBeyondSelection, "\(inputSource)")
        }
    }

    /// The selection is sent verbatim — not reordered, not deduped into
    /// something else, not expanded. What the UI claimed is what goes out.
    @Test("the selection is sent verbatim")
    func selectionIsSentVerbatim() {
        let selection = ["doc-3", "doc-1", "doc-2"]
        let scope = resolve(inputSource: .collection, selection: selection, collectionId: "folder")
        #expect(scope.docIds == selection)
    }

    // MARK: - No path may silently widen scope

    /// The guard the issue asks for: any resolution that reaches beyond the
    /// user's explicit picks must SAY so, so a caller can confirm before
    /// running. A widening run that reports `false` here is the bug returning.
    @Test("a run only ever widens when nothing was selected")
    func wideningIsOnlyPossibleWithoutASelection() {
        for inputSource in WorkflowInputSource.allCases {
            for collectionId in [nil, "folder"] as [String?] {
                for fallback in [nil, "doc"] as [String?] {
                    let withSelection = resolve(
                        inputSource: inputSource,
                        selection: ["chosen"],
                        collectionId: collectionId,
                        fallbackDocumentId: fallback
                    )
                    #expect(!withSelection.widensBeyondSelection)
                    #expect(withSelection.docIds == ["chosen"])
                }
            }
        }
    }

    /// With nothing selected, a collection workflow legitimately runs the
    /// folder — but it is flagged as widening so the caller must state the
    /// scope and offer a cancel first (#4396 rule 3).
    @Test("an unselected collection run is flagged as widening and named")
    func unselectedCollectionRunIsFlagged() {
        let scope = resolve(inputSource: .collection, collectionId: "folder-top")
        #expect(scope.docIds == ["folder-top"])
        #expect(scope.widensBeyondSelection)
        #expect(scope.describedScope == "everything in this folder")
    }

    /// A `.currentSelection` workflow with nothing selected must NOT fall back
    /// to the folder — that would be the same bug wearing the other label.
    @Test("a current-selection workflow never falls back to the collection")
    func currentSelectionNeverFallsBackToTheFolder() {
        let scope = resolve(inputSource: .currentSelection, collectionId: "folder-top")
        #expect(scope.docIds.isEmpty)
        #expect(!scope.widensBeyondSelection)
        #expect(!scope.docIds.contains("folder-top"))
    }

    @Test("with no selection and no collection, a previewed document is the scope")
    func previewedDocumentIsTheFallback() {
        for inputSource in WorkflowInputSource.allCases {
            let scope = resolve(inputSource: inputSource, fallbackDocumentId: "previewed")
            #expect(scope.docIds == ["previewed"], "\(inputSource)")
            #expect(!scope.widensBeyondSelection, "\(inputSource)")
        }
    }

    @Test("with nothing at all, nothing is sent")
    func nothingResolvesToNothing() {
        for inputSource in WorkflowInputSource.allCases {
            let scope = resolve(inputSource: inputSource)
            #expect(scope.docIds.isEmpty, "\(inputSource)")
            #expect(!scope.widensBeyondSelection, "\(inputSource)")
        }
    }

    // MARK: - The UI's claim matches the request

    /// #4396 rule 3: the scope has to be stateable BEFORE the run, so the
    /// description must be non-empty and must agree with the id count it
    /// describes.
    @Test("the described scope matches the ids actually sent")
    func describedScopeMatchesTheRequest() {
        let one = resolve(inputSource: .collection, selection: ["a"])
        #expect(one.describedScope == "1 selected document")
        #expect(one.docIds.count == 1)

        let many = resolve(inputSource: .collection, selection: ["a", "b", "c"])
        #expect(many.describedScope == "3 selected documents")
        #expect(many.docIds.count == 3)

        for scope in [one, many, resolve(inputSource: .collection, collectionId: "f")] {
            #expect(!scope.describedScope.isEmpty)
        }
    }

    // MARK: - Structural: the widening path is gone, and the default is known

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// `runWorkflowOnCollection` took every `.file` in the current collection
    /// and never consulted the selection. It had no callers — but a
    /// scope-widening path with no trigger is a loaded gun, so it is deleted
    /// rather than left for the next person who wants "run on this folder".
    @Test("the selection-ignoring collection run path is gone")
    func theCollectionRunPathIsDeleted() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentView+WorkflowActions.swift")
        #expect(!source.contains("func runWorkflowOnCollection"))
        #expect(!source.contains("filter { $0.docType == .file }"))
    }

    /// The editor's run path must go through the one scope resolver, not its
    /// own switch over `inputSource`.
    @Test("the workflow editor resolves scope through WorkflowRunScope")
    func editorUsesTheSharedResolver() throws {
        let source = try Self.appSource("Views/Workflow/Editor/WorkflowEditor+Actions.swift")
        #expect(source.contains("WorkflowRunScope.resolve("))
        #expect(!source.contains("func resolveSelectedDocumentIds"))
        // The old shape: a bare `[collectionId]` return from an inputSource switch.
        #expect(!source.contains("return [collectionId]"))
    }

    /// Recorded because it is what makes this the normal case rather than an
    /// edge one: an omitted `input_source` decodes as `.collection`.
    @Test("input source defaults to collection, which is why this was the common path")
    func inputSourceDefaultsToCollection() throws {
        let types = try Self.appSource("Models/WorkflowTypes.swift")
        #expect(types.contains("?? .collection"))
    }
}
