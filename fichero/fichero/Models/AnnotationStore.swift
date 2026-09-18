import Foundation
import Observation
import OSLog

/// Observable domain store for document annotations (#1883, mirrors `EntityStore`).
///
/// The single endpoint accessor for the annotation list a view renders. A view
/// never calls `AnnotationService` directly: it observes `annotations` and
/// dispatches the named actions below. Each action performs the typed write and
/// then refreshes the current scope — today via an explicit reload, and via
/// `apply(_:)` once the per-library change-stream starts emitting `annotation.*`
/// events. Swapping reload for push is then a no-op at every call site.
///
/// Annotations are scoped via `AnnotationScope` (document / page / folder).
/// One instance per library (registered on `LibraryReference`), shared across
/// that library's windows.
@MainActor
@Observable
final class AnnotationStore: ObservableDomainStore {
    // ─── Published domain state (views read these directly) ───
    private(set) var annotations: [DocumentAnnotation] = []
    private(set) var isLoading = false
    private(set) var loadError: String?
    private(set) var loadedScope: AnnotationScope?

    /// Monotonic counter bumped on every applied `annotation.*` change event.
    /// Views that maintain bespoke annotation loads observe this token and
    /// resync when it changes. Mirrors `ClaimStore.changeToken`.
    private(set) var changeToken: Int = 0

    // ─── Transport: the EXISTING AnnotationService wrapper, unchanged ───
    private let annotationService: AnnotationService
    private let log = Logger(subsystem: "app.fichero.fichero", category: "AnnotationStore")

    init(annotationService: AnnotationService) {
        self.annotationService = annotationService
    }

    // MARK: - Load (the store, not the view, owns fetching)

    /// Load annotations for the given scope. Idempotent against the same
    /// already-populated scope unless `force` is set.
    func loadAnnotations(for scope: AnnotationScope, force: Bool = false) async {
        if !force, loadedScope == scope, !annotations.isEmpty { return }
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        switch scope {
        case .document(let id): await annotationService.load(documentId: id)
        case .page(let id): await annotationService.load(pageId: id)
        case .folder(let id): await annotationService.load(folderId: id)
        }
        annotations = annotationService.annotations
        loadError = annotationService.error
        loadedScope = scope
        log.debug("Loaded \(self.annotations.count, privacy: .public) annotations")
    }

    /// Re-fetch the current scope (post-mutation / reconnect resync).
    func reload() async {
        guard let scope = loadedScope else { return }
        await loadAnnotations(for: scope, force: true)
    }

    // MARK: - Named actions (map 1:1 to the audited action layer, #1848)

    /// Create a note annotation and refresh the list. Mirrors AnnotationService.addNote.
    @discardableResult
    func addNote(
        scope: AnnotationScope,
        text: String,
        pageLabel: String? = nil,
        bbox: [Double]? = nil,
        // The rendition the rect was MEASURED on, or nil for the node's own
        // image. Same frame identity `OCRGeometry.renditionId` carries for
        // region boxes (2026-09-03): a mark whose frame is unknown is a mark
        // that will be drawn over the wrong pixels sooner or later.
        renditionId: String? = nil,
        charStart: Int? = nil,
        charEnd: Int? = nil,
        pageIndex: Int? = nil,
        kind: AnnotationKind = .note,
        color: String? = nil,
        rating: Int? = nil,
        tags: [String] = [],
        linkedClaimIds: [String] = []
    ) async -> DocumentAnnotation? {
        let result = await annotationService.addNote(
            scope: scope,
            text: text,
            pageLabel: pageLabel,
            bbox: bbox,
            renditionId: renditionId,
            charStart: charStart,
            charEnd: charEnd,
            pageIndex: pageIndex,
            kind: kind,
            color: color,
            rating: rating,
            tags: tags,
            linkedClaimIds: linkedClaimIds
        )
        if let result { annotations.insert(result, at: 0) }
        return result
    }

    /// Fetch the latest server copy for one annotation and merge it into the
    /// list in place (#4824 — `AnnotationService.getAnnotation` already
    /// splices its own array correctly; the store used to throw that away by
    /// reassigning `annotations = annotationService.annotations` wholesale).
    @discardableResult
    func getAnnotation(id: String) async -> DocumentAnnotation? {
        let result = await annotationService.getAnnotation(id: id)
        if let result {
            if let idx = annotations.firstIndex(where: { $0.id == result.id }) {
                annotations[idx] = result
            } else {
                annotations.insert(result, at: 0)
            }
        }
        return result
    }

    /// Patch an annotation's text and update the in-memory copy in place.
    @discardableResult
    func updateText(id: String, text: String) async -> DocumentAnnotation? {
        let result = await annotationService.updateText(id: id, text: text)
        if let result, let idx = annotations.firstIndex(where: { $0.id == id }) {
            annotations[idx] = result
        }
        return result
    }

    /// Delete an annotation and remove it from the list in place.
    @discardableResult
    func delete(id: String) async -> Bool {
        let success = await annotationService.delete(id: id)
        if success { annotations.removeAll { $0.id == id } }
        return success
    }

    /// Fetch cropped bytes for an annotation's source span or region.
    @discardableResult
    func cropAnnotation(id: String) async -> Data? {
        await annotationService.cropAnnotation(id: id)
    }

    /// Fetch the cropped source region (image or text) for any bbox/char anchor
    /// (#2105) — powers SourceSnippet / the provenance popover.
    func cropRegion(_ request: SourceCropRequest) async throws -> SourceCrop? {
        try await annotationService.cropRegion(request)
    }

    /// Promote a highlight/note to a KnowledgeClaim, then merge the updated
    /// copy (its `linkedClaimIds` now set) into the list in place. The
    /// promote endpoint itself returns no annotation body, so a follow-up
    /// `getAnnotation` fetch (a single, scoped request — not a list reload)
    /// supplies the item to splice.
    @discardableResult
    func promoteToClaim(id: String) async -> Bool {
        let success = await annotationService.promoteToClaim(id: id)
        if success, let updated = await annotationService.getAnnotation(id: id) {
            if let idx = annotations.firstIndex(where: { $0.id == updated.id }) {
                annotations[idx] = updated
            } else {
                annotations.insert(updated, at: 0)
            }
        }
        return success
    }

    // MARK: - Search passthrough (keeps call sites unchanged)

    static func matchesSearch(_ annotation: DocumentAnnotation, query: String) -> Bool {
        AnnotationService.matchesSearch(annotation, query: query)
    }

    // MARK: - ChangeEventConsumer (called by LibraryChangeStream, NOT by views)

    nonisolated var changeDomain: String { "annotation" }

    func apply(_ event: ChangeEvent) {
        guard eventTouchesLoadedScope(event) else { return }
        changeToken &+= 1
        switch event.verb {
        case "created", "updated", "deleted":
            scheduleReload()
        default:
            break
        }
    }

    /// Holds the shared 300ms trailing-reload debouncer (#1973). `scheduleReload()`
    /// (called above for create/update/delete) and `resync()` are provided by the
    /// `ObservableDomainStore` extension — no per-store copies.
    let reloadDebouncer = ReloadDebouncer()

    private func eventTouchesLoadedScope(_ event: ChangeEvent) -> Bool {
        guard let loadedScope else { return false }
        let ids = Set(event.documentIds)
        if ids.isEmpty { return true }
        switch loadedScope {
        case .document(let id), .page(let id), .folder(let id):
            return ids.contains(id)
        }
    }
}
