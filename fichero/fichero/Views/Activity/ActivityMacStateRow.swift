import FicheroAPIClient
import SwiftUI

/// This Mac's state as one compact row of symbols with short values
/// (`activity.popover.mac-state-row`, #5635): each says its full reading in
/// its help and to accessibility; only a problem is tinted.
struct ActivityMacStateRow: View {
    let readings: [ActivityPopoverSummary.MacReading]

    var body: some View {
        HStack(spacing: 12) {
            ForEach(readings) { reading in
                HStack(spacing: 3) {
                    Image(systemName: reading.symbol)
                    Text(reading.value).monospacedDigit()
                }
                .font(.caption)
                .foregroundStyle(reading.isProblem ? AnyShapeStyle(.orange) : AnyShapeStyle(.secondary))
                .help(reading.help)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(reading.help)
                .accessibilityIdentifier("activity.popover.macState.\(reading.id)")
            }
        }
        .fixedSize()
        .accessibilityElement(children: .contain)
        .accessibilityLabel("This Mac")
        .accessibilityIdentifier("activity.popover.macState")
    }
}

#Preview("This Mac: all well, then hot with memory tight") {
    VStack(alignment: .leading, spacing: 12) {
        ActivityMacStateRow(readings: ActivityPopoverSummary(
            jobs: [], paused: false,
            machine: Components.Schemas.MachineState(memoryPressure: .normal, thermalState: .nominal, onBattery: false,
                                                     inUse: false, whyWait: nil),
            processCpuPercent: 2, cpuCount: 8
        ).macReadings)
        ActivityMacStateRow(readings: ActivityPopoverSummary(
            jobs: [], paused: false,
            machine: Components.Schemas.MachineState(memoryPressure: .critical, thermalState: .serious, onBattery: true,
                                                     inUse: true, whyWait: "the Mac is hot"),
            processCpuPercent: 412, cpuCount: 8
        ).macReadings)
    }
    .padding()
}
