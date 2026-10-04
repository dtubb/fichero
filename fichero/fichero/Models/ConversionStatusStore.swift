import FicheroAPIClient
import Foundation
import Observation
import OSLog

// MARK: - Converting a library's older results: the status the window shows (#5222 part 3)

/// What `GET /api/conversion/status` says, as plain values, so the wording is testable
/// without an engine or a window.
struct ConversionSnapshot: Equatable {
    struct NotConverted: Equatable { let documentId: String; let reason: String }
    struct KeptAsItWas: Equatable { let artifactType: String; let count: Int; let reason: String }

    var running = false
    var runId: String?
    var verdict: String?
    var seconds: Double?
    var pagesConverted = 0
    var pagesSkipped = 0
    var pagesNotConverted: [NotConverted] = []
    var pagesRemaining = 0
    var snapshotPath: String?
    var diskRequiredBytes: Int?
    var diskAvailableBytes: Int?
    var leftAsTheyWere: [KeptAsItWas] = []
    var seen = false
}

/// The wording, file scope so Swift Testing calls it off-main. The spec's rule
/// (`segments-and-geometry.md`, "Converting a whole project"): a report for each project,
/// shown ONCE and kept; the engine releases the run's snapshot when it is seen.
enum ConversionNoticeText {
    /// How far along a running conversion is, 0...1, or nil when nothing is running.
    static func progress(_ status: ConversionSnapshot) -> Double? {
        guard status.running else { return nil }
        let done = status.pagesConverted + status.pagesSkipped + status.pagesNotConverted.count
        let total = done + status.pagesRemaining
        return total > 0 ? Double(done) / Double(total) : 0
    }

    /// The window's one line, or nil when there is nothing to say (no run ever needed, nothing
    /// to do, or a finished run whose report was already seen).
    static func line(_ status: ConversionSnapshot) -> String? {
        if status.running {
            let done = status.pagesConverted + status.pagesSkipped + status.pagesNotConverted.count
            return "Bringing this library's older results into the page model: \(done) of "
                + "\(done + status.pagesRemaining) pages. You can keep working."
        }
        guard status.runId != nil, !status.seen, let verdict = status.verdict else { return nil }
        switch verdict {
        case "completed":
            var line = "Brought \(pages(status.pagesConverted)) into the page model"
            if !status.pagesNotConverted.isEmpty {
                line += "; \(pages(status.pagesNotConverted.count)) could not be and read as before"
            }
            return line + "."
        case "refused_disk":
            var line = "Older results were not brought into the page model: the disk is too full"
            if let need = status.diskRequiredBytes {
                line += " (it needs \(bytes(need))"
                if let have = status.diskAvailableBytes { line += ", \(bytes(have)) free" }
                line += ")"
            }
            return line + ". It will try again the next time this library opens."
        case "refused_snapshot":
            return "Older results were not brought into the page model: no safe snapshot could be made "
                + "first. It will try again the next time this library opens."
        case "failed":
            return "Bringing older results into the page model stopped before it finished. "
                + "Nothing is half done; it will carry on the next time this library opens."
        default:
            return nil
        }
    }

    /// The report a person opens from the line: what converted, what could not and why, what
    /// was left as it was, where the snapshot is, how long it took.
    static func report(_ status: ConversionSnapshot) -> String {
        var lines: [String] = []
        lines.append("Pages brought into the page model: \(status.pagesConverted).")
        if status.pagesSkipped > 0 {
            lines.append("Pages already done when the run reached them: \(status.pagesSkipped).")
        }
        if !status.pagesNotConverted.isEmpty {
            lines.append("Pages that could not be (they read exactly as before):")
            lines += status.pagesNotConverted.map { "  • \($0.documentId): \($0.reason)" }
        }
        for left in status.leftAsTheyWere {
            lines.append("Left as they were: \(left.count) \(left.artifactType) result(s). \(left.reason)")
        }
        if status.pagesRemaining > 0 {
            lines.append("Still to do: \(pages(status.pagesRemaining)), at the next open.")
        }
        if let snapshot = status.snapshotPath {
            lines.append("The snapshot taken first is kept at \(snapshot) until you close this report.")
        }
        if let seconds = status.seconds {
            lines.append("It took \(Int(seconds.rounded())) seconds.")
        }
        return lines.joined(separator: "\n")
    }

    private static func pages(_ count: Int) -> String { count == 1 ? "1 page" : "\(count) pages" }

    private static func bytes(_ count: Int) -> String {
        ByteCountFormatter.string(fromByteCount: Int64(count), countStyle: .file)
    }
}

/// The one reader of the conversion status for a library (observable data layer: the view
/// observes, the store calls the engine). One per library, shared by its windows.
@MainActor
@Observable
final class ConversionStatusStore {
    private(set) var status = ConversionSnapshot()
    /// Hidden for this session by the window's close button; the report is still unseen.
    var hiddenForSession = false
    private let client: FicheroClient
    private let log = Logger(subsystem: "app.fichero.fichero", category: "ConversionStatus")

    init(client: FicheroClient) {
        self.client = client
    }

    func refresh() async {
        do {
            let response = try await client.api.conversionStatusApiConversionStatusGet()
            if case .ok(let ok) = response {
                status = Self.snapshot(try ok.body.json)
            }
        } catch {
            // Best-effort: the line is a courtesy, never a blocker. Logged, not shown.
            if !error.isCancellationError {
                log.error("Conversion status unavailable: \(error.localizedDescription, privacy: .public)")
            }
        }
    }

    /// The person closed the report: the run is seen, which releases its snapshot.
    func markSeen() async {
        guard let runId = status.runId else { return }
        do {
            _ = try await client.api.conversionSeenApiConversionRunIdSeenPost(path: .init(runId: runId))
            status.seen = true
        } catch {
            log.error("Could not mark conversion \(runId, privacy: .public) seen: \(error.localizedDescription, privacy: .public)")
        }
    }

    static func snapshot(_ status: Components.Schemas.ConversionStatus) -> ConversionSnapshot {
        ConversionSnapshot(
            running: status.running,
            runId: status.runId,
            verdict: status.verdict,
            seconds: status.seconds,
            pagesConverted: status.pagesConverted ?? 0,
            pagesSkipped: status.pagesSkipped ?? 0,
            pagesNotConverted: (status.pagesNotConverted ?? []).map { .init(documentId: $0.documentId, reason: $0.reason) },
            pagesRemaining: status.pagesRemaining ?? 0,
            snapshotPath: status.snapshotPath,
            diskRequiredBytes: status.diskRequiredBytes,
            diskAvailableBytes: status.diskAvailableBytes,
            leftAsTheyWere: (status.leftAsTheyWere ?? []).map {
                .init(artifactType: $0.artifactType, count: $0.count, reason: $0.reason)
            },
            seen: status.seen ?? false
        )
    }
}

