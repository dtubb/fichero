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
        let value = known.isEmpty ? "\(held.count)" : gigabytes(total)
        let lines = held.map { model in
            model.memoryBytes.map { "\(model.name): \(gigabytes($0))" } ?? model.name
        }
        return [MacReading(id: "models", symbol: "square.stack.3d.up", value: value,
                           help: "Models Fichero holds in memory: " + lines.joined(separator: " · "))]
    }

    private static func gigabytes(_ bytes: Int) -> String {
        String(format: "%.1f GB", Double(bytes) / 1_073_741_824)
    }
}
