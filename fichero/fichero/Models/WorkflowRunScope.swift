import Foundation

/// What a workflow run is scoped to, decided in ONE place (#4396).
///
/// The P0: running Catalogue on a single selected PDF ran it over the entire
/// folder. The cause was not `runWorkflowOnCollection` — that function has no
/// callers at all. It was `WorkflowEditor.resolveSelectedDocumentIds()`:
///
///     case .collection:
///         if let collectionId = documentStore.selectedCollection?.id {
///             return [collectionId]        // <- the selection is never consulted
///         }
///
/// A workflow authored with `inputSource == .collection` sent the FOLDER id as
/// `selected_doc_ids`, and the engine faithfully expanded it. Worse, that is
/// the *default*: `.collection` is the default in `Workflow.init`, in
/// `WorkflowDefinition.init`, and in the decoder's
/// `decodeIfPresent(...) ?? .collection`. So any workflow whose `input_source`
/// the engine omits behaves this way. It is the normal case, not an edge one.
///
/// Catalogue writes entities and claims into the knowledge graph, so a widened
/// run does not just cost LLM calls — it curates real archival material the
/// user never chose, durably.
///
/// The rule this type encodes: **a selection is an instruction.** If the user
/// has selected documents, the run applies to that selection, whatever the
/// workflow was authored to prefer. A collection-wide run is only what happens
/// when there is nothing selected to honour.
enum WorkflowRunScope {

    /// The resolved scope, plus what the UI must be able to say about it
    /// BEFORE the request goes out.
    struct Resolution: Equatable {
        /// Exactly the ids to send as `selected_doc_ids`.
        let docIds: [String]

        /// True when this run reaches beyond what the user explicitly picked —
        /// today, only the collection-id case. The caller must state the scope
        /// and let the user cancel before running (#4396 rule 3). Never true
        /// when a selection was honoured, because then the scope IS the
        /// selection.
        let widensBeyondSelection: Bool

        /// The scope in words, for the confirmation and the run record. The
        /// point of #4396 is that a run's scope is stated up front rather than
        /// discovered from its effects.
        let describedScope: String
    }

    /// - Parameters:
    ///   - inputSource: what the workflow was AUTHORED to prefer. It can no
    ///     longer override an explicit selection; it only decides what happens
    ///     when there is no selection.
    ///   - selection: the ids the user has actually selected.
    ///   - collectionId: the current collection/folder, when there is one.
    ///   - fallbackDocumentId: the single previewed document, used when
    ///     nothing is selected and there is no collection.
    static func resolve(
        inputSource: WorkflowInputSource,
        selection: [String],
        collectionId: String?,
        fallbackDocumentId: String?
    ) -> Resolution {
        // Selection wins, full stop — for BOTH input sources. This single
        // branch is the fix: it used to be reachable only for
        // `.currentSelection`, so a `.collection` workflow silently substituted
        // the folder for what the user picked.
        if !selection.isEmpty {
            let noun = selection.count == 1 ? "document" : "documents"
            return Resolution(
                docIds: selection,
                widensBeyondSelection: false,
                describedScope: "\(selection.count) selected \(noun)"
            )
        }

        switch inputSource {
        case .collection:
            if let collectionId {
                // Nothing is selected, so the folder is the honest scope — but
                // it is a WIDENING run and the caller has to say so first.
                return Resolution(
                    docIds: [collectionId],
                    widensBeyondSelection: true,
                    describedScope: "everything in this folder"
                )
            }
        case .currentSelection:
            break
        }

        if let fallbackDocumentId {
            return Resolution(
                docIds: [fallbackDocumentId],
                widensBeyondSelection: false,
                describedScope: "1 document"
            )
        }

        return Resolution(docIds: [], widensBeyondSelection: false, describedScope: "nothing")
    }
}
