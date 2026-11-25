import Foundation
import Observation

/// Which lines are marked out of date, and which re-read failed, for the views that show a line.
@MainActor
@Observable
final class SegmentRereadState {
    static let shared = SegmentRereadState()

    /// Lines whose words came from a paid cloud model and whose shape changed since.
    private(set) var stale: Set<String> = []
    /// A re-read that could not be queued, with the engine's words.
    private(set) var failed: [String: String] = [:]

    func markStale(_ ids: [String]) { stale.formUnion(ids); ids.forEach { failed[$0] = nil } }
    func markFailed(_ ids: [String], _ words: String) { ids.forEach { failed[$0] = words } }
    func clear(_ ids: [String]) { stale.subtract(ids); ids.forEach { failed[$0] = nil } }
}
