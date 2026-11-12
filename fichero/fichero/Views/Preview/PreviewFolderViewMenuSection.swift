import SwiftUI

/// The "Show folder as" section of the Preview head's selector menu: List, Table, Icons, Canvas, the pane's
/// current one ticked (`library.preview.folder-view-picker-in-the-head`). Dimmed while the selection
/// is not a single folder; the choice is kept either way. Absent outside a pane slot, where a pick
/// would have nowhere to land.
struct PreviewFolderViewMenuSection: View {
    let selectionIsFolder: Bool

    @Environment(\.panePreviewFolderView) private var storedView
    @Environment(\.panePreviewFolderViewSwitcher) private var switcher

    var body: some View {
        if let switcher {
            let current = PreviewFolderView.effective(storedView)
            Section("Show folder as") {
                ForEach(PreviewFolderView.allCases) { option in
                    Button {
                        switcher.switchFolderView(option)
                    } label: {
                        Label {
                            HStack(spacing: 4) {
                                Text(option.title)
                                if option == current { Image(systemName: "checkmark") }
                            }
                        } icon: {
                            Image(systemName: option.icon)
                        }
                    }
                    .accessibilityIdentifier("previewHeadFolderView.\(option.rawValue)")
                }
            }
            .disabled(!selectionIsFolder)
            .accessibilityIdentifier("previewHeadFolderView")
        }
    }
}

#Preview("Show folder as") {
    Menu("Preview") { PreviewFolderViewMenuSection(selectionIsFolder: true) }
        .padding()
}
