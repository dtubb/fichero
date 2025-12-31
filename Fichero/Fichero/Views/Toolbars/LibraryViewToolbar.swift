import SwiftUI

/// Toolbar for Library view with view mode picker and column configuration
struct LibraryViewToolbar: View {
    @Binding var viewMode: LibraryLayout
    let showColumnConfig: Bool

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

    var body: some View {
        HStack(spacing: 8) {
            // View mode picker
            Picker("View", selection: $viewMode) {
                Label("Icons", systemImage: "square.grid.2x2")
                    .tag(LibraryLayout.icons)
                Label("List", systemImage: "list.bullet")
                    .tag(LibraryLayout.list)
                Label("Table", systemImage: "tablecells")
                    .tag(LibraryLayout.table)
                Label("Map", systemImage: "rectangle.3.group")
                    .tag(LibraryLayout.map)
            }
            .pickerStyle(.segmented)
            .frame(width: 200)

            Spacer()

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
