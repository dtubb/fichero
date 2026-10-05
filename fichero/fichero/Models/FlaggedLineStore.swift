import Foundation
import Observation

/// The one owner of which lines the teacher-line check flagged (#5446), keyed by page: every list that
/// shows lines (the Segments pane's list, strip and grid, the Order list) and the Inspector read their
/// marks here. A person's Confirm clears one line in place; a `check.*` change event re-reads the page
/// it names.
@MainActor
@Observable
final class FlaggedLineStore {
    /// Page id -> segment id -> its flag.
    private(set) var flagsByDocument: [String: [String: FlaggedLines.Line]] = [:]
    /// Finished runs, read once: a finished run's flagged lines do not change.
    private(set) var runs: [String: FlaggedLines.Run] = [:]
    private(set) var loadErrorsByDocumentId: [String: String] = [:]
    /// Why the last Confirm did not land; nil after one did.
    private(set) var confirmNote: String?

    private let transport: FlaggedLineTransport
    /// Pages with a re-read already on its way: a run writes one verdict (one event) per flagged line.
    private var pendingReloads: Set<String> = []
    /// Runs still underway, watched until they finish so their flags show without another event.
    private var watchedRuns: Set<String> = []
    /// How long a burst of events, or a run's next look, waits.
    var settle: Duration = .seconds(2)

    init(transport: FlaggedLineTransport) {
        self.transport = transport
    }

    /// One store per `SegmentService`, the idiom `SegmentStore.shared(for:)` uses: the instance the
    /// library registers with the change stream is the one the lists read.
    @MainActor private static var registry: [ObjectIdentifier: FlaggedLineStore] = [:]

    static func shared(for service: SegmentService) -> FlaggedLineStore {
        let key = ObjectIdentifier(service)
        if let existing = registry[key] { return existing }
        let store = FlaggedLineStore(transport: CheckService(client: service.client))
        registry[key] = store
        return store
    }

    /// Read one page's flags: the reading verdicts, then each run that rejected a line here. Replaces
    /// ONLY this page's entry. Idempotent once read unless `force`.
    func load(documentId: String, force: Bool = false) async {
        if !force, flagsByDocument[documentId] != nil { return }
        do {
            let decoder = JSONDecoder()
            let verdicts = try decoder.decode(FlaggedLines.VerdictList.self, from: try await transport.readingVerdicts(documentId: documentId)).items
            for runId in FlaggedLines.runIds(verdicts, documentId: documentId) where runs[runId] == nil {
                // A run that is not the teacher-line check (no `flagged` list) or cannot be read flags nothing.
                guard let data = try? await transport.run(id: runId),
                      let run = try? decoder.decode(FlaggedLines.Run.self, from: data) else { continue }
                if run.isUnderway { watch(runId, documentId: documentId) } else { runs[runId] = run }
            }
            flagsByDocument[documentId] = FlaggedLines.flagged(verdicts: verdicts, runs: runs, documentId: documentId)
            loadErrorsByDocumentId[documentId] = nil
        } catch {
            if error.isCancellationError { return }
            loadErrorsByDocumentId[documentId] = error.localizedDescription
        }
    }

    /// A run still underway when its page was read: looked at again until it finishes, then the page re-read.
    private func watch(_ runId: String, documentId: String) {
        guard watchedRuns.insert(runId).inserted else { return }
        Task { [weak self] in
            while let self {
                try? await Task.sleep(for: self.settle)
                guard let data = try? await self.transport.run(id: runId),
                      let run = try? JSONDecoder().decode(FlaggedLines.Run.self, from: data) else { break }
                if !run.isUnderway { break }
            }
            self?.watchedRuns.remove(runId)
            await self?.load(documentId: documentId, force: true)
        }
    }

    /// A page's re-read after a change, once per burst of events.
    private func reloadSoon(_ documentId: String) {
        guard pendingReloads.insert(documentId).inserted else { return }
        Task { [weak self] in
            if let settle = self?.settle { try? await Task.sleep(for: settle) }
            self?.pendingReloads.remove(documentId)
            await self?.load(documentId: documentId, force: true)
        }
    }

    func flag(segmentId: String, documentId: String) -> FlaggedLines.Line? {
        flagsByDocument[documentId]?[segmentId]
    }

    /// How many lines on the page are flagged now.
    func flaggedCount(documentId: String) -> Int {
        flagsByDocument[documentId]?.count ?? 0
    }

    /// The counts of the run that flagged a line, in words ("3 passed, 1 closer to a neighbour, …").
    func runWords(_ line: FlaggedLines.Line) -> String? {
        runs[line.runId].map { FlaggedLines.countsWords($0.counts) }
    }

    /// A person's Confirm (`check.verdict`, trust `person`) on the reading the check rejected: the line
    /// is no longer flagged and goes back into training sets. Clears that one line in place.
    func confirm(segmentId: String, documentId: String) async {
        guard let line = flag(segmentId: segmentId, documentId: documentId) else { return }
        do {
            try await transport.confirm(readingId: line.readingId, segmentId: segmentId)
            flagsByDocument[documentId]?[segmentId] = nil
            confirmNote = nil
        } catch {
            confirmNote = "The line could not be confirmed: \(error.localizedDescription)"
        }
    }
}

extension FlaggedLineStore: ChangeEventConsumer {
    /// `check.verdict`: a run's reject or anyone's confirm, naming the page it is on.
    nonisolated var changeDomains: Set<String> { ["check"] }

    func apply(_ event: ChangeEvent) {
        for documentId in event.documentIds where flagsByDocument[documentId] != nil {
            reloadSoon(documentId)
        }
    }

    /// After a reconnect every page read is read again: events missed while down are unknowable.
    func resync() async {
        for documentId in flagsByDocument.keys {
            await load(documentId: documentId, force: true)
        }
    }
}
