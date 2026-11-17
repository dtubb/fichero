import FicheroAPIClient
import Foundation

/// This Mac, measured (`activity.resources.everything-measured`): nil where nothing measures it.
struct ActivityThisMac: Equatable, Sendable {
    struct Lane: Equatable, Sendable {
        let lane: String
        var busy: Int
        let width: Int
    }

    var memoryUsedBytes: Int?
    var memoryTotalBytes: Int?
    var processorPercent: Double?
    var lanes: [Lane] = []

    init(memoryUsedBytes: Int? = nil, memoryTotalBytes: Int? = nil, processorPercent: Double? = nil,
         lanes: [Lane] = []) {
        self.memoryUsedBytes = memoryUsedBytes; self.memoryTotalBytes = memoryTotalBytes
        self.processorPercent = processorPercent; self.lanes = lanes
    }

    init(_ mac: Components.Schemas.ThisMac) {
        self.init(memoryUsedBytes: mac.memoryUsedBytes, memoryTotalBytes: mac.memoryTotalBytes,
                  processorPercent: mac.processorPercent,
                  lanes: (mac.lanes ?? []).map { Lane(lane: $0.lane, busy: $0.busy, width: $0.width) })
    }

    /// "12 of 16 GB · 25%": memory used of its total and the processor's load, "—" for what nothing measures.
    var words: String {
        let memory: String
        if let used = memoryUsedBytes, let total = memoryTotalBytes {
            let usedWords = ByteCountFormatter.string(fromByteCount: Int64(used), countStyle: .memory)
            memory = "\(usedWords) of \(ByteCountFormatter.string(fromByteCount: Int64(total), countStyle: .memory))"
        } else {
            memory = "—"
        }
        return "\(memory) · \(processorPercent.map { "\(Int($0.rounded()))%" } ?? "—")"
    }

    /// "network 2 of 4 · local-ml 1 of 1": the lanes with work in them; "No lane busy" when none.
    var lanesWords: String {
        let busy = lanes.filter { $0.busy > 0 }.map { "\($0.lane) \($0.busy) of \($0.width)" }
        return busy.isEmpty ? "No lane busy" : busy.joined(separator: " · ")
    }

    /// Several projects' answers as one: the Mac's own figures once, each lane's work added.
    static func merged(_ macs: [ActivityThisMac]) -> ActivityThisMac? {
        guard var total = macs.first else { return nil }
        for other in macs.dropFirst() {
            for lane in other.lanes {
                if let index = total.lanes.firstIndex(where: { $0.lane == lane.lane }) {
                    total.lanes[index].busy += lane.busy
                } else {
                    total.lanes.append(lane)
                }
            }
        }
        return total
    }
}
