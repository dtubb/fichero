import FicheroAPIClient
import Foundation
import OSLog

extension AnnotationService {
    /// Max bytes to collect for a crop image / text (safety bound).
    static let maxCropImageBytes = 20_000_000
    static let maxCropTextBytes = 5_000_000

    /// Fetch cropped text/image bytes for an annotation's source span or region.
    /// The crop routes now return `image/png` bytes (image/PDF bbox) or a
    /// `text/plain` substring (#2105/#3442), so decode the typed body.
    @discardableResult
    func cropAnnotation(id: String) async -> Data? {
        syncLibraryPath()
        do {
            let response = try await client.api.getCropApiAnnotationsAnnotationIdCropGet(.init(
                path: .init(annotationId: id),
            ))
            guard case .ok(let okResponse) = response else {
                error = "Could not crop annotation"
                return nil
            }
            error = nil
            switch okResponse.body {
            case .png(let body):
                return try await Data(collecting: body, upTo: Self.maxCropImageBytes)
            case .plainText(let body):
                return try await Data(collecting: body, upTo: Self.maxCropTextBytes)
            case .json:
                // The crop routes always return PNG or text; `application/json`
                // is only the advertised FastAPI default and never sent.
                return nil
            }
        } catch {
            logger.warning("Failed to crop annotation: \(error.localizedDescription, privacy: .public)")
            self.error = "Could not crop annotation"
            return nil
        }
    }

    /// Fetch the cropped source region for ANY bbox/char anchor (#2105) — a
    /// claim, entity mention, annotation, or face — WITHOUT persisting an
    /// annotation. Returns the rendered PNG as an image, or the verbatim text
    /// substring. Powers `SourceSnippet` / the provenance popover.
    func cropRegion(_ request: SourceCropRequest) async throws -> SourceCrop? {
        syncLibraryPath()
        let body = Components.Schemas.EphemeralCropRequest(
            documentId: request.documentId,
            bbox: request.bbox,
            charStart: request.charStart,
            charEnd: request.charEnd,
            pageIndex: request.pageIndex,
            pageLabel: request.pageLabel
        )
        let response = try await client.api.cropEphemeralApiAnnotationsCropPost(
            .init(body: .json(body))
        )
        guard case .ok(let okResponse) = response else { return nil }
        switch okResponse.body {
        case .png(let httpBody):
            let data = try await Data(collecting: httpBody, upTo: Self.maxCropImageBytes)
            return PlatformImage(data: data).map { .image($0) }
        case .plainText(let httpBody):
            let data = try await Data(collecting: httpBody, upTo: Self.maxCropTextBytes)
            return String(data: data, encoding: .utf8).map { .text($0) }
        case .json:
            // Advertised FastAPI default only; the route always returns PNG/text.
            return nil
        }
    }
}
