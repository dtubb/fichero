import Foundation

/// A backend-work status update folded onto the per-library activity/change
/// stream (#2279). Decoded from a `backend.work.*` frame's `change_metadata`.
///
/// `runId` is the backend task id — stable across a task's started → progress →
/// terminal updates, so the UI can update one indicator in place rather than
/// stacking rows.
struct BackendWorkStatus: Identifiable, Equatable {
    enum Phase: String {
        case started, progress, completed, failed, cancelled

        /// True once the task has finished (any outcome) — the live indicator
        /// clears on the phase it was showing.
        var isTerminal: Bool { self == .completed || self == .failed || self == .cancelled }
    }

    let runId: String
    let phase: Phase
    let taskType: String
    let taskName: String
    let status: String
    let message: String
    let current: Int
    let total: Int
    /// 0…100; parsed as a Double because the engine emits it stringified and it
    /// may carry a fraction.
    let percent: Double
    let timestamp: String

    var id: String { runId }
    var isTerminal: Bool { phase.isTerminal }

    /// Integer percent for display.
    var displayPercent: Int { Int(percent.rounded()) }
}

/// A "library opened" signal — e.g. the `fichero` CLI (or the backend) opened a
/// library out of band (#2279). Informational; the UI surfaces it subtly.
struct LibraryOpenedSignal: Equatable {
    let libraryName: String
    let source: String
    let timestamp: String
}

/// One decoded backend/library signal off the activity/change stream (#2279).
///
/// Pure and transport-free so the decode rule is unit-testable. The frontend
/// receives these as folded activity frames whose flattened metadata
/// (`ActivityResponse.metadataStrings`) carries `change_type` plus
/// `change_metadata` — a JSON string of the emitting event's own metadata
/// (`{task_name, percent, …}` or `{library_name, source}`).
enum BackendActivityEvent: Equatable {
    case work(BackendWorkStatus)
    case libraryOpened(LibraryOpenedSignal)

    /// Build from a flattened activity-frame metadata dict. Returns `nil` for any
    /// frame that isn't a `backend.work.*` / `library.opened` signal, so the
    /// caller falls through to its existing activity/change handling.
    init?(activityMetadata metadata: [String: String]) {
        guard let changeType = metadata["change_type"], !changeType.isEmpty else { return nil }
        let timestamp = metadata["ts"] ?? ""
        let inner = Self.decodeChangeMetadata(metadata["change_metadata"])

        if changeType == "library.opened" {
            self = .libraryOpened(LibraryOpenedSignal(
                libraryName: inner["library_name"] ?? "",
                source: inner["source"] ?? "",
                timestamp: timestamp
            ))
        } else if changeType.hasPrefix("backend.work.") {
            let phaseRaw = String(changeType.dropFirst("backend.work.".count))
            guard let phase = BackendWorkStatus.Phase(rawValue: phaseRaw) else { return nil }
            self = .work(BackendWorkStatus(
                runId: metadata["run_id"] ?? "",
                phase: phase,
                taskType: inner["task_type"] ?? "",
                taskName: inner["task_name"] ?? "",
                status: inner["status"] ?? "",
                message: inner["message"] ?? "",
                current: Int(inner["current"] ?? "") ?? 0,
                total: Int(inner["total"] ?? "") ?? 0,
                percent: Double(inner["percent"] ?? "") ?? 0,
                timestamp: timestamp
            ))
        } else {
            return nil
        }
    }

    /// Decode the `change_metadata` JSON string into a flat string dict. The
    /// engine stringifies every value already, so a shallow `String(describing:)`
    /// on each is lossless; a malformed/absent payload yields an empty dict.
    private static func decodeChangeMetadata(_ raw: String?) -> [String: String] {
        guard let raw, let data = raw.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return [:] }
        return object.mapValues { value in
            if let string = value as? String { return string }
            return String(describing: value)
        }
    }
}
