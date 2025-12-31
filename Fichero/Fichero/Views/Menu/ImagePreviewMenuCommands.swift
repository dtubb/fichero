import SwiftUI

/// Menu commands for image preview controls (magnifier panel, loupe)
struct ImagePreviewMenuCommands: View {
    @AppStorage("imagePreview.magnifierEnabled") private var magnifierEnabled = false
    @AppStorage("imagePreview.loupeEnabled") private var loupeEnabled = false
    @AppStorage("imagePreview.magnifierLocked") private var magnifierLocked = false
    @AppStorage("imagePreview.loupeMagnification") private var loupeMagnification: Double = 3.0
    @AppStorage("imagePreview.loupeSize") private var loupeSize: Double = 150.0
    @AppStorage("imagePreview.panelMagnification") private var panelMagnification: Double = 4.0
    @AppStorage("imagePreview.panelHeight") private var panelHeight: Double = 120.0

    var body: some View {
        Section("Image Preview") {
            // Magnifier panel toggle
            Button {
                magnifierEnabled.toggle()
            } label: {
                HStack {
                    if magnifierEnabled {
                        Image(systemName: "checkmark")
                    }
                    Label("Magnifier Panel", systemImage: "rectangle.bottomhalf.inset.filled")
                }
            }
            .keyboardShortcut("m", modifiers: [.command, .option])

            // Lock magnifier toggle
            Button {
                magnifierLocked.toggle()
            } label: {
                HStack {
                    if magnifierLocked {
                        Image(systemName: "checkmark")
                    }
                    Label("Lock Magnifier", systemImage: "lock")
                }
            }
            .keyboardShortcut("l", modifiers: [.command, .option])
            .disabled(!magnifierEnabled)

            Divider()

            // Loupe toggle
            Button {
                loupeEnabled.toggle()
            } label: {
                HStack {
                    if loupeEnabled {
                        Image(systemName: "checkmark")
                    }
                    Label("Loupe", systemImage: "eye")
                }
            }
            .keyboardShortcut("k", modifiers: [.command, .option])
        }
    }
}
