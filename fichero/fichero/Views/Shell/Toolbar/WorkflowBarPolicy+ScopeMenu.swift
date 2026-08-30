import Foundation

// The subject token's MENU (Daniel, 2026-08-29 evening, from the live
// sentence bar): the chip that NAMES the scope is clickable to CHANGE it —
// switch from the selected page to one of its artifacts, or back to the
// browser selection. Choosing writes an explicit override that outranks the
// automatic ladder until cleared; "Automatic" restores the ladder. All pure
// policy here — the token itself lives in `WorkflowBar+ChainRail`.
extension WorkflowBarPolicy {

    /// One entry in the subject chip's menu.
    struct ScopeOption: Identifiable, Equatable {
        let id: String
        let label: String
        /// nil = Automatic — clear the override and follow the ladder.
        let scope: RunScope?
    }

    /// Resolution with an explicit override. The override wins while the
    /// thing it names is still on screen; a stale override (its selection
    /// gone, its document left) silently yields back to the ladder rather
    /// than scoping a run to something invisible.
    static func resolveRunScope(
        _ snapshot: SelectionSnapshot,
        override chosen: RunScope?
    ) -> RunScope {
        if let chosen, overrideStillVisible(chosen, in: snapshot) {
            return chosen
        }
        return resolveRunScope(snapshot)
    }

    /// Per-rung visibility for an override — each case is checked against
    /// the live seam it was minted from.
    static func overrideStillVisible(
        _ chosen: RunScope,
        in snapshot: SelectionSnapshot
    ) -> Bool {
        switch chosen {
        case .marqueeSelection(let documentId, let rect, _):
            return snapshot.marqueeDocumentId == documentId && snapshot.marqueeRect == rect
        case .regions(let ids, _):
            return snapshot.regionIds == ids
        case .artifact(let documentId, let artifactId, _, _, _, _):
            if let artifactId {
                return snapshot.artifactId == artifactId
                    && snapshot.artifactDocumentId == documentId
            }
            // Chosen by TYPE: valid while its document is still the one
            // being inspected.
            return snapshot.detailDocumentId == documentId
        case .documents(let ids):
            return snapshot.browserSelection == ids
        case .detailDocument(let id, _):
            return snapshot.detailDocumentId == id
        case .nothing:
            return false
        }
    }

    /// The artifact types the menu offers explicitly — the `artifacts_source`
    /// vocabulary (transcription, transcription_review, translation).
    static let artifactScopeTypes = ["transcription", "transcription_review", "translation"]

    /// "transcription_review" → "Transcription Review".
    static func artifactTypeDisplayName(_ type: String) -> String {
        switch type {
        case "transcription": return "Transcription"
        case "transcription_review": return "Transcription Review"
        case "translation": return "Translation"
        default:
            return type.split(separator: "_").map(\.capitalized).joined(separator: " ")
        }
    }

    /// The subject menu: Automatic first, then every rung the ladder could
    /// resolve RIGHT NOW, then the inspected document's artifacts by type so
    /// a run can be aimed at an artifact explicitly. Every option is labeled
    /// with the same naming the chip itself uses.
    static func scopeMenuOptions(
        from snapshot: SelectionSnapshot,
        artifactTypes: [String] = artifactScopeTypes
    ) -> [ScopeOption] {
        var options = [ScopeOption(id: "automatic", label: "Automatic", scope: nil)]
        func add(_ id: String, _ scope: RunScope, label: String? = nil) {
            guard let text = label ?? scopeDetail(scope) ?? targetLabel(scope.target) else { return }
            options.append(ScopeOption(id: id, label: text, scope: scope))
        }

        if let marqueeId = snapshot.marqueeDocumentId, let rect = snapshot.marqueeRect,
           rect.width > 0, rect.height > 0, marqueeId == snapshot.detailDocumentId {
            add("marquee", .marqueeSelection(
                documentId: marqueeId, rect: rect,
                documentName: snapshot.marqueeDocumentName ?? snapshot.detailDocumentName
            ))
        }
        if !snapshot.regionIds.isEmpty,
           snapshot.regionParentDocumentId == nil
            || snapshot.regionParentDocumentId == snapshot.detailDocumentId {
            add("regions", .regions(
                ids: snapshot.regionIds, parentName: snapshot.regionParentName
            ))
        }
        // The FOCUSED artifact — offered without the ladder's multi-select
        // guard, because picking it from the menu IS the deliberate choice
        // that guard exists to protect.
        if let artifactId = snapshot.artifactId,
           let documentId = snapshot.artifactDocumentId,
           documentId == snapshot.detailDocumentId {
            add("artifact", .artifact(
                documentId: documentId, artifactId: artifactId,
                displayName: snapshot.artifactDisplayName ?? "Artifact",
                documentName: snapshot.artifactDocumentName,
                artifactType: snapshot.artifactType,
                stepName: snapshot.artifactStepName
            ))
        }
        if !snapshot.browserSelection.isEmpty {
            add("documents", .documents(ids: snapshot.browserSelection))
        }
        if let detailId = snapshot.detailDocumentId,
           snapshot.browserSelection != [detailId] {
            add("detail", .detailDocument(id: detailId, name: snapshot.detailDocumentName),
                label: snapshot.detailDocumentName ?? "This document")
        }
        // Aim at an artifact by TYPE (transcription, review, translation) —
        // the artifacts_source targets, offered even before one is focused.
        if let detailId = snapshot.detailDocumentId {
            for type in artifactTypes {
                add("artifact-type-\(type)", .artifact(
                    documentId: detailId, artifactId: nil,
                    displayName: artifactTypeDisplayName(type),
                    documentName: snapshot.detailDocumentName,
                    artifactType: type, stepName: nil
                ))
            }
        }
        return options
    }
}
