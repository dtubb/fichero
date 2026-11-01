import FicheroAPIClient
import Foundation
import Observation

/// Loads the engine's one compare answer for a page (`GET /api/documents/{page_id}/compare-readers`) into `CompareViewModel`, and
/// makes one line's reading the one that counts (`POST /api/segments/{id}/readings/choice`, `wide.compare.pick-per-line`). The
/// engine does the matching and the agreement; this holds the answer and the words when it cannot be had.
@MainActor @Observable
final class CompareReadersStore {
    private let client: FicheroClient
    let pageId: String
    /// The stage whose try is compared (`?try_stage=`): the compare view opens from a try's sample page, so it shows that try.
    let tryStage: String?
    private(set) var model: CompareViewModel?
    private(set) var image: (width: Int, height: Int)?
    /// The image the boxes are drawn on (`frame`): the edited image when the page has saved edits.
    private(set) var frame: Components.Schemas.CompareFrame?
    private(set) var failure: String?

    /// The iPhone opens on Overlay, the Mac and iPad side by side.
    private let platform: CompareViewModel.Platform

    init(client: FicheroClient, pageId: String, tryStage: String? = nil, platform: CompareViewModel.Platform) {
        self.client = client
        self.tryStage = tryStage
        self.platform = platform
        self.pageId = pageId
    }

    func load() async {
        do {
            switch try await client.api.getCompareReadersApiDocumentsPageIdCompareReadersGet(
                path: .init(pageId: pageId), query: .init(tryStage: tryStage)) {
            case .ok(let success):
                let answer = try success.body.json
                let mode = model?.mode
                model = CompareViewModel(answer: answer, platform: platform)
                if let mode { model?.mode = mode }
                frame = answer.frame
                if let width = answer.imageWidth, let height = answer.imageHeight { image = (width, height) }
                failure = nil
            default:
                failure = "Could not compare the readers on this page."
            }
        } catch {
            if error.isCancellationError { return }
            failure = "Could not compare the readers on this page: \(error.localizedDescription)"
        }
    }

    /// The line's reading by `readerId` becomes the one that counts; the answer is read again. A refusal is said, never dropped.
    func pick(readerId: String, onLine order: Int) async {
        guard let pick = model?.pick(readerId: readerId, onLine: order) else { return }
        do {
            switch try await client.api.chooseSegmentReadingApiSegmentsSegmentIdReadingsChoicePost(
                path: .init(segmentId: pick.segmentId),
                body: .json(.init(kind: "transcription", representationId: pick.representationId,
                                  expectedCountingId: pick.expectedCountingId))) {
            case .ok:
                await load()
            case .undocumented(statusCode: 409, _):
                await load()
                failure = "That line has changed since you looked at it. The readings are shown again."
            default:
                failure = "Could not use that reading."
            }
        } catch {
            if error.isCancellationError { return }
            failure = "Could not use that reading: \(error.localizedDescription)"
        }
    }

    func setOnlyDiffering(_ only: Bool) { model?.onlyDiffering = only }
    func set(mode: CompareViewModel.Mode) { model?.mode = mode }
    func toggle(reader id: String) { model?.toggle(reader: id) }
    func moveHandle(to position: Double) { model?.moveHandle(to: position) }
}
