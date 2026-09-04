import CoreGraphics
import OSLog
import SwiftUI

private let scopeLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "WorkflowScope"
)

// The workflow bar's RUN SCOPE (Daniel, 2026-08-29): the bar follows the
// selection the user can SEE, wherever it is. The ladder — Preview marquee >
// inspector region selection > inspector artifact selection > browser
// selection > detail document — is a pure function in `WorkflowBarPolicy`;
// this file only snapshots the live seams and acts on the resolved scope.
// Kept out of ContentView+WorkflowBar for the same type-checker-budget reason
// that file exists at all.
extension ContentView {

    /// Everything the scope ladder reads, snapshotted. The browser rung still
    /// reads the same accessor every other launch surface reads (#4523).
    var workflowBarSelectionSnapshot: WorkflowBarPolicy.SelectionSnapshot {
        let marquee = windowState.previewMarquees
        let regions = FocusedRegionSelection.shared
        let artifactFocus = FocusedArtifact.shared
        return WorkflowBarPolicy.SelectionSnapshot(
            marqueeDocumentId: marquee.documentId,
            marqueeRect: marquee.firstReadingOrderRect,
            marqueeDocumentName: marquee.documentName,
            regionIds: regions.regionDocumentIds,
            regionParentDocumentId: regions.parentDocumentId,
            regionParentName: regions.parentDocumentName,
            artifactId: artifactFocus.id,
            artifactDocumentId: artifactFocus.documentId,
            artifactDisplayName: artifactFocus.artifact?.artifactTypeDisplayName,
            artifactType: artifactFocus.artifact?.artifactType,
            artifactStepName: artifactFocus.artifact?.stepName,
            artifactDocumentName: artifactFocus.documentName,
            artifactPinned: artifactFocus.pinnedForRun,
            browserSelection: effectiveWorkflowRunSelection,
            detailDocumentId: detailDocument?.id,
            detailDocumentName: detailDocument.map { DocumentTitle.displayName(for: $0) },
            detailArtifacts: detailArtifactChoices
        )
    }

    /// The inspected document's artifacts, as the menu's plain values. Read
    /// off the ArtifactStore the inspector already loaded — the menu adds no
    /// fetch of its own, and simply offers nothing extra when the store is
    /// pointed somewhere else (the by-TYPE rows still work).
    var detailArtifactChoices: [WorkflowBarPolicy.ArtifactChoice] {
        guard let detailId = detailDocument?.id,
              artifactStore.currentDocumentId == detailId else { return [] }
        return artifactStore.items
            .filter { $0.documentId == detailId }
            .map {
                WorkflowBarPolicy.ArtifactChoice(
                    id: $0.id,
                    artifactType: $0.artifactType,
                    displayName: $0.artifactTypeDisplayName,
                    provider: $0.provider,
                    model: $0.model,
                    stepName: $0.stepName,
                    createdAt: $0.createdAt
                )
            }
    }

    /// The resolved scope — the ONE decision every bar consumer (chip label,
    /// target count, run dispatch, vision preference) projects from. An
    /// explicit override from the subject chip's menu outranks the ladder
    /// while what it names is still visible.
    var workflowBarRunScope: WorkflowBarPolicy.RunScope {
        WorkflowBarPolicy.resolveRunScope(
            workflowBarSelectionSnapshot, override: workflowScopeOverride
        )
    }

    /// The subject chip's menu, fed by the ladder: Automatic, every rung
    /// resolvable right now, and the inspected document's artifacts by type.
    var workflowBarScopeOptions: [WorkflowBarPolicy.ScopeOption] {
        WorkflowBarPolicy.scopeMenuOptions(from: workflowBarSelectionSnapshot)
    }

    /// Write (or clear, with nil) the explicit scope override.
    @MainActor
    func selectWorkflowScope(_ scope: WorkflowBarPolicy.RunScope?) {
        workflowScopeOverride = scope
    }

    /// The document ids a chain run acts on, frozen at ▶-press. Nil means
    /// the run cannot start (nothing to act on, or the marquee could not be
    /// materialized — already reported to the user).
    @MainActor
    func frozenChainTargets(for scope: WorkflowBarPolicy.RunScope) async -> [String]? {
        var targets = scope.documentIds
        guard !targets.isEmpty else { return nil }
        if case .marqueeSelection(let parentId, _, _) = scope {
            // The engine takes crops as node CONFIG, never run inputs, so an
            // unpersisted rect cannot run directly — ▶ materializes EVERY
            // drawn marquee as its own region child (`image.crop_child`,
            // reversible), in reading order — the diary-entry ruling: several
            // marquees, several nodes. Honest, not hidden: the children
            // appear under their page like any other region node.
            let rects = windowState.previewMarquees.readingOrderCGRects
            var childIds: [String] = []
            for rect in rects {
                guard let childId = await materializeMarqueeRegion(
                    parentId: parentId, normalizedRect: rect
                ) else {
                    importError = "Could not create a region node for the selection."
                    return nil
                }
                childIds.append(childId)
            }
            guard !childIds.isEmpty else {
                importError = "Could not create a region node for the selection."
                return nil
            }
            // The selections became nodes; keeping them armed would scope
            // the NEXT run to rects that now exist twice.
            windowState.previewMarquees.clear()
            targets = childIds
        }
        return targets
    }

    /// Turn one ephemeral marquee into a persisted region child and return
    /// its id, or nil when it cannot be done honestly (no pixel size to
    /// denormalize against, or the engine refused).
    ///
    /// `image.crop_child` takes PIXEL coordinates and normalizes server-side;
    /// the marquee seam carries the source's pixel size for exactly this.
    @MainActor
    func materializeMarqueeRegion(parentId: String, normalizedRect: CGRect) async -> String? {
        let marquee = windowState.previewMarquees
        guard let pixelSize = marquee.imagePixelSize,
              pixelSize.width > 0, pixelSize.height > 0 else {
            scopeLogger.error("marquee run: no pixel size to denormalize \(parentId)")
            return nil
        }
        let left = max(0, Int((normalizedRect.minX * pixelSize.width).rounded(.down)))
        let top = max(0, Int((normalizedRect.minY * pixelSize.height).rounded(.down)))
        let width = max(1, Int((normalizedRect.width * pixelSize.width).rounded()))
        let height = max(1, Int((normalizedRect.height * pixelSize.height).rounded()))
        do {
            let service = ImageEditingService(apiClient: apiClient)
            let childId = try await service.cropChild(
                documentId: parentId,
                left: left, top: top, width: width, height: height
            )
            scopeLogger.info("marquee run: materialized region \(childId) of \(parentId)")
            // Clearing the seam is the CALLER's job, after the whole set is
            // materialized — clear() here would nil the pixel size mid-loop.
            return childId
        } catch {
            scopeLogger.error("marquee run: crop_child failed: \(error.localizedDescription)")
            return nil
        }
    }
}
