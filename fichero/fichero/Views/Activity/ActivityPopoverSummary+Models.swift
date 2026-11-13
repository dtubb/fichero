import FicheroAPIClient
import Foundation

// The models the engine itself holds in memory, beside the Mac's own readings (#6129; ported with the engine's `models_held`).

extension ActivityPopoverSummary {
    /// The Mac's readings, the models the engine itself holds, and the app's processor use.
    static func macReadings(_ machine: Components.Schemas.MachineState?, processCpuPercent: Double?, cpuCount: Int) -> [MacReading] {
        let mac = machine.map(readings) ?? []
        let held = heldReading(machine?.modelsHeld ?? [])
        let cpu = processCpuPercent.map { [cpuReading($0, cpuCount: cpuCount)] } ?? []
        return mac + held + cpu
    }

    /// One reading for the models the engine holds: the total of the sizes it knows (else how many), and in its help each
    /// model with its size, the engine's names as sent. None when the engine holds none.
    static func heldReading(_ held: [Components.Schemas.HeldModel]) -> [MacReading] {
        guard !held.isEmpty else { return [] }
        let known = held.compactMap(\.memoryBytes)
        let total = known.reduce(0, +)
        let value = known.isEmpty ? "\(held.count) model\(held.count == 1 ? "" : "s")" : gigabytes(total)
        let lines = held.map { model in
            model.memoryBytes.map { "\(model.name): \(gigabytes($0))" } ?? model.name
        }
        return [MacReading(id: "models", symbol: "square.stack.3d.up", value: value,
                           help: "Models Fichero holds in memory: " + lines.joined(separator: " · "))]
    }

    private static func gigabytes(_ bytes: Int) -> String {
        String(format: "%.1f GB", Double(bytes) / 1_073_741_824)
    }

    /// What is working right now, from the engine's one summary (`activity.popover.same-summary`, #5852): "Recipe ›
    /// Stage › Workflow" and "7 of 20 pages · 2 of 8 folders", the same words the window's live block has.
    struct Block: Equatable, Identifiable {
        let id: String
        let title: String
        let counts: String
        /// What a waiting block waits for; nil while it works.
        let waiting: String?
        /// The model by its own name and where it runs, the engine's words as sent ("Kraken · on this Mac"); nil with neither.
        var subtitle: String?
        /// "about 12 min left", from the engine's own pace; nil until a page is done.
        var timeLeft: String?
        /// "$0.40" so far, at the right edge; nil when the run has cost nothing.
        var cost: String?
    }
}

extension ActivityPopoverSummary {
    /// The work lines the popover names at most (`activity.popover.at-most-five`, owner 2026-11-13); the rest are Activity's.
    static let workShown = 5

    /// How many of each work list the popover draws, in order (live blocks, runs in hand, background kinds, running
    /// items), at most `limit` lines in all, and how many it leaves to the Activity monitor.
    struct WorkCap: Equatable {
        let blocks: Int
        let runs: Int
        let background: Int
        let running: Int
        let hidden: Int

        init(blocks: Int, runs: Int, background: Int, running: Int, limit: Int = ActivityPopoverSummary.workShown) {
            var left = max(limit, 0)
            func take(_ count: Int) -> Int {
                let taken = min(max(count, 0), left)
                left -= taken
                return taken
            }
            self.blocks = take(blocks)
            self.runs = take(runs)
            self.background = take(background)
            self.running = take(running)
            hidden = max(blocks, 0) + max(runs, 0) + max(background, 0) + max(running, 0)
                - (self.blocks + self.runs + self.background + self.running)
        }

        /// "3 more in Activity"; nil when nothing is left out.
        var moreLine: String? { hidden > 0 ? "\(hidden) more in Activity" : nil }
    }
}
