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
        let marquee = PreviewMarqueeSelection.shared
        let regions = FocusedRegionSelection.shared
        let artifactFocus = FocusedArtifact.shared
        return WorkflowBarPolicy.SelectionSnapshot(
            marqueeDocumentId: marquee.documentId,
            marqueeRect: marquee.normalizedRect,
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
            browserSelection: effectiveWorkflowRunSelection,
            detailDocumentId: detailDocument?.id,
            detailDocumentName: detailDocument.map { DocumentTitle.displayName(for: $0) }
        )
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
        if case .marqueeSelection(let parentId, let rect, _) = scope {
            // The engine takes crops as node CONFIG, never run inputs, so an
            // unpersisted rect cannot run directly — ▶ materializes it as a
            // real region child (`image.crop_child`, reversible) and runs on
            // that. Honest, not hidden: the child appears under its page
            // like any other region node.
            guard let childId = await materializeMarqueeRegion(
                parentId: parentId, normalizedRect: rect
            ) else {
                importError = "Could not create a region node for the selection."
                return nil
            }
            targets = [childId]
        }
        return targets
    }

    /// Turn the ephemeral marquee into a persisted region child and return
    /// its id, or nil when it cannot be done honestly (no pixel size to
    /// denormalize against, or the engine refused).
    ///
    /// `image.crop_child` takes PIXEL coordinates and normalizes server-side;
    /// the marquee seam carries the source's pixel size for exactly this.
    @MainActor
    func materializeMarqueeRegion(parentId: String, normalizedRect: CGRect) async -> String? {
        let marquee = PreviewMarqueeSelection.shared
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
            // The selection became a node; keeping the marquee armed would
            // scope the NEXT run to a rect that now exists twice.
            marquee.clear()
            return childId
        } catch {
            scopeLogger.error("marquee run: crop_child failed: \(error.localizedDescription)")
            return nil
        }
    }
}
