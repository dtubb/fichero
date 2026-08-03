import FicheroAPIClient
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

        /// WHAT the ids are, not just which ids they are (#4414).
        ///
        /// `docIds` alone cannot distinguish "the user picked this one folder,
        /// expand it" from "the user picked these 47 documents" — both are a
        /// list of strings. That ambiguity is the #4396 shape: the client
        /// decided what a folder meant and the server had to trust it.
        ///
        /// The generated `SelectionKind` is used rather than a hand-rolled
        /// mirror, deliberately: a vocabulary the client can misspell is one it
        /// will eventually misspell, and `check_openapi_shadow_types.py`
        /// forbids the duplicate anyway.
        let kind: Components.Schemas.SelectionKind

        /// The declared selection to send on the wire, or nil when there is
        /// nothing to run on.
        ///
        /// Nil rather than an empty selection because the server rejects an
        /// empty one outright — "an empty selection is not a scope, it is a
        /// missing argument". Sending it would turn "nothing selected" into a
        /// 422 instead of the caller's own no-op guard.
        var selection: Components.Schemas.WorkflowSelection? {
            docIds.isEmpty ? nil : .init(kind: kind, ids: docIds)
        }
    }

    /// An explicit set of documents the user picked. The ids ARE the scope, so
    /// there is nothing left for the server to expand or the client to get
    /// wrong.
    ///
    /// Used by the three call sites that resolve their targets before they get
    /// here (sidebar, content view, library batch). They cannot honestly claim
    /// `.folder`: by the time they call, a folder has already been expanded
    /// client-side into its descendants, and `kind=folder` with 47 ids is
    /// exactly the request the server now refuses.
    static func documents(_ ids: [String]) -> Components.Schemas.WorkflowSelection? {
        ids.isEmpty ? nil : .init(kind: .documents, ids: ids)
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
                describedScope: "\(selection.count) selected \(noun)",
                kind: .documents
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
                    describedScope: "everything in this folder",
                    // ONE container id, declared as a container. This is the
                    // half of #4396 that becomes structural: the server now
                    // expands the folder because the request SAYS it is a
                    // folder, rather than because the client sent a folder id
                    // in a field that names documents.
                    kind: .collection
                )
            }
        case .currentSelection:
            break
        }

        if let fallbackDocumentId {
            return Resolution(
                docIds: [fallbackDocumentId],
                widensBeyondSelection: false,
                describedScope: "1 document",
                kind: .documents
            )
        }

        return Resolution(
            docIds: [],
            widensBeyondSelection: false,
            describedScope: "nothing",
            kind: .documents
        )
    }
}
