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
    private(set) var model: CompareViewModel?
    private(set) var image: (width: Int, height: Int)?
    private(set) var failure: String?

    init(client: FicheroClient, pageId: String) {
        self.client = client
        self.pageId = pageId
    }

    func load(platform: CompareViewModel.Platform = .mac) async {
        do {
            switch try await client.api.getCompareReadersApiDocumentsPageIdCompareReadersGet(path: .init(pageId: pageId)) {
            case .ok(let success):
                let answer = try success.body.json
                let mode = model?.mode
                model = CompareViewModel(answer: answer, platform: platform)
                if let mode { model?.mode = mode }
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

    /// The line's reading by `readerId` becomes the one that counts; the answer is read again.
    func pick(readerId: String, onLine order: Int) async {
        guard let line = model?.lines.first(where: { $0.order == order }), let segment = line.segmentId,
              let reading = line.readings.first(where: { $0.readerId == readerId }), let representation = reading.representationId else { return }
        do {
            _ = try await client.api.chooseSegmentReadingApiSegmentsSegmentIdReadingsChoicePost(
                path: .init(segmentId: segment),
                body: .json(.init(kind: "transcription", representationId: representation, expectedCountingId: line.countingReaderId)))
            await load()
        } catch {
            if error.isCancellationError { return }
            failure = "Could not use that reading: \(error.localizedDescription)"
        }
    }

    func setOnlyDiffering(_ on: Bool) { model?.onlyDiffering = on }
    func set(mode: CompareViewModel.Mode) { model?.mode = mode }
    func toggle(reader id: String) { model?.toggle(reader: id) }
    func moveHandle(to position: Double) { model?.moveHandle(to: position) }
}
