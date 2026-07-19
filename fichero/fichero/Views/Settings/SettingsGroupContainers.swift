import SwiftUI

// MARK: - Consolidated Settings Groups (#3396)

/// A sub-section within a consolidated settings tab. `label` names its segment.
private protocol SettingsGroupSection: Identifiable, Hashable {
    var label: String { get }
}

/// Shared chrome for a consolidated settings tab: a segmented sub-picker over the
/// available sub-sections (hidden when only one is available), then the selected
/// section's EXISTING settings view — every reused pane is unchanged (#3396). The
/// selection is clamped to what's available so a default that a platform/flag
/// hides (e.g. the macOS-only Engine/Devices panes on iOS) never shows blank.
private struct SettingsGroupContainer<Section: SettingsGroupSection, Content: View>: View {
    let sections: [Section]
    @Binding var rawSelection: Section
    @ViewBuilder let content: (Section) -> Content

    private var effective: Section {
        sections.contains(rawSelection) ? rawSelection : (sections.first ?? rawSelection)
    }

    var body: some View {
        VStack(spacing: 0) {
            if sections.count > 1 {
                Picker("", selection: Binding(get: { effective }, set: { rawSelection = $0 })) {
                    ForEach(sections) { Text($0.label).tag($0) }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .padding()
                Divider()
            }
            content(effective)
        }
    }
}

private enum EngineGroupSection: String, CaseIterable, SettingsGroupSection {
    case engine = "Engine"
    case backend = "Backend"
    var id: String { rawValue }
    var label: String { rawValue }
}

/// Engine tab (#3396): folds the former Backend tab in as a sub-section. Reuses
/// EngineSettingsView + BackendSettingsView unchanged.
struct EngineGroupSettingsView: View {
    @State private var selection: EngineGroupSection = .engine

    private var availableSections: [EngineGroupSection] {
        // Engine + Backend are real capabilities; their existence no longer hangs
        // off per-feature migration flags (#3811/#3776). The sidebar row gate
        // (`SettingsView.showsTesterSettingsPane`) decides reachability per build.
        var sections: [EngineGroupSection] = []
        #if canImport(AppKit)
        sections.append(.engine)
        #endif
        sections.append(.backend)
        return sections
    }

    var body: some View {
        SettingsGroupContainer(sections: availableSections, rawSelection: $selection) { section in
            switch section {
            case .engine:
                #if canImport(AppKit)
                EngineSettingsView()
                #endif
            case .backend:
                BackendSettingsView()
            }
        }
    }
}

private enum SharingSection: String, CaseIterable, SettingsGroupSection {
    case people = "People"
    case devices = "Devices"
    case capture = "Capture"
    var id: String { rawValue }
    var label: String { rawValue }
}

/// Library Access tab (#3396): who/what can reach a library — the former Connect
/// (device pairing / QR), Users (people/roles), and Capture (capture permissions)
/// tabs, consolidated. Reuses each pane unchanged.
struct SharingSettingsView: View {
    @State private var selection: SharingSection = .people

    private var availableSections: [SharingSection] {
        // People / Devices (pairing + QR) / Capture are all real, keepable
        // capabilities (#3776) — the user's control is the sharing toggle inside
        // Devices, not whether the pane is compiled in. Their existence no longer
        // hangs off per-feature migration flags, which is what made the QR vanish
        // for beta testers (#3811). The sidebar row gate
        // (`SettingsView.showsLibraryAccessSettings`) decides reachability per build.
        var sections: [SharingSection] = [.people]
        #if canImport(AppKit)
        sections.append(.devices)
        #endif
        sections.append(.capture)
        return sections
    }

    var body: some View {
        SettingsGroupContainer(sections: availableSections, rawSelection: $selection) { section in
            switch section {
            case .people:
                UsersSettingsView()
            case .devices:
                #if canImport(AppKit)
                ShareSettingsView()
                #endif
            case .capture:
                CaptureSettingsView()
            }
        }
    }
}
