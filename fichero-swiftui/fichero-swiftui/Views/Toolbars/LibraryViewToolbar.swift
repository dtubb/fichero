import SwiftUI

/// Toolbar for Library view with column configuration and sort menu
/// View mode picker moved to MainToolbar for universal access
struct LibraryViewToolbar: View {
    @Binding var viewMode: LibraryLayout  // Still needed to show column config only for table view
    let showColumnConfig: Bool

    // Display mode for conditional controls
    let displayMode: ViewDisplayMode

    // Sort controls
    @Binding var sortFieldRaw: String
    @Binding var sortAscending: Bool

    // Zoom controls (icon + map views)
    @Binding var iconViewScale: Double
    @Binding var mapCanvasScale: CGFloat

    // Column visibility toggles
    @Binding var showName: Bool
    @Binding var showStatus: Bool
    @Binding var showProgress: Bool
    @Binding var showOutput: Bool
    @Binding var showFileType: Bool
    @Binding var showPath: Bool
    @Binding var showCreatedDate: Bool
    @Binding var showModifiedDate: Bool
    @Binding var showSize: Bool

    let onResetColumns: () -> Void

    private var sortField: LibrarySortField {
        LibrarySortField(rawValue: sortFieldRaw) ?? .name
    }

    var body: some View {
        HStack(spacing: 8) {
            // Sort menu (always visible)
            Menu {
                ForEach(LibrarySortField.allCases) { field in
                    Button {
                        if sortField == field {
                            sortAscending.toggle()
                        } else {
                            sortFieldRaw = field.rawValue
                            sortAscending = true
                        }
                    } label: {
                        HStack {
                            Label(field.rawValue, systemImage: field.icon)
                            if sortField == field {
                                Image(systemName: sortAscending ? "chevron.up" : "chevron.down")
                            }
                        }
                    }
                }

                Divider()

                Button {
                    sortAscending.toggle()
                } label: {
                    Label(
                        sortAscending ? "Descending" : "Ascending",
                        systemImage: sortAscending ? "chevron.down" : "chevron.up"
                    )
                }
            } label: {
                Image(systemName: "arrow.up.arrow.down")
            }
            .help("Sort: \(sortField.rawValue) (\(sortAscending ? "ascending" : "descending"))")

            // Zoom controls (icon + map views only)
            if displayMode == .icon || displayMode == .map {
                Spacer()
                Button {
                    if displayMode == .icon {
                        iconViewScale = max(0.5, iconViewScale - 0.25)
                    } else {
                        mapCanvasScale = max(0.25, mapCanvasScale - 0.25)
                    }
                } label: {
                    Image(systemName: "minus.magnifyingglass")
                }
                .buttonStyle(.borderless)
                .keyboardShortcut("-", modifiers: .command)
                .help("Zoom Out")

                Button {
                    if displayMode == .icon {
                        iconViewScale = 1.0
                    } else {
                        mapCanvasScale = 1.0
                    }
                } label: {
                    Image(systemName: "1.magnifyingglass")
                }
                .buttonStyle(.borderless)
                .help("Reset Zoom")

                Button {
                    if displayMode == .icon {
                        iconViewScale = min(3.0, iconViewScale + 0.25)
                    } else {
                        mapCanvasScale = min(3.0, mapCanvasScale + 0.25)
                    }
                } label: {
                    Image(systemName: "plus.magnifyingglass")
                }
                .buttonStyle(.borderless)
                .keyboardShortcut("=", modifiers: .command)
                .help("Zoom In")
            }

            // Column configuration (only for table view)
            if showColumnConfig && viewMode == .table {
                Menu {
                    Text("Show Columns")
                        .font(.caption)

                    Divider()

                    Toggle("Name", isOn: $showName)
                    Toggle("Status", isOn: $showStatus)
                    Toggle("Progress", isOn: $showProgress)
                    Toggle("Output", isOn: $showOutput)
                    Toggle("Type", isOn: $showFileType)
                    Toggle("Path", isOn: $showPath)
                    Toggle("Created", isOn: $showCreatedDate)
                    Toggle("Modified", isOn: $showModifiedDate)
                    Toggle("Size", isOn: $showSize)

                    Divider()

                    Button("Reset to Default") {
                        onResetColumns()
                    }
                } label: {
                    Image(systemName: "slider.horizontal.3")
                }
                .help("Configure Columns")
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(.ultraThinMaterial)
    }
}
