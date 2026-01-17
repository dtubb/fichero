import SwiftUI

/// Menu commands for image preview controls (zoom, magnifier panel, loupe)
struct ImagePreviewMenuCommands: View {
    // MARK: - Constants

    private enum MagnifierLimits {
        static let minMagnification: Double = 1.0
        static let maxMagnification: Double = 16.0
        static let zoomFactor: Double = 1.5
    }

    // MARK: - Focused Values

    @FocusedValue(\.imageZoomActions) private var zoomActions

    // MARK: - Storage

    @AppStorage("imagePreview.magnifierEnabled") private var magnifierEnabled = false
    @AppStorage("imagePreview.loupeEnabled") private var loupeEnabled = false
    @AppStorage("imagePreview.magnifierLocked") private var magnifierLocked = false
    @AppStorage("imagePreview.loupeMagnification") private var loupeMagnification: Double = 3.0
    @AppStorage("imagePreview.loupeSize") private var loupeSize: Double = 150.0
    @AppStorage("imagePreview.panelMagnification") private var panelMagnification: Double = 4.0
    @AppStorage("imagePreview.panelHeight") private var panelHeight: Double = 120.0

    // MARK: - Body

    var body: some View {
        Section("Image Preview") {
            mainZoomSection
            Divider()
            magnifierSection
            Divider()
            loupeSection
        }
    }

    // MARK: - Main Image Zoom Section

    @ViewBuilder
    private var mainZoomSection: some View {
        Button("Actual Size") {
            zoomActions?.actualSize()
        }
        .keyboardShortcut("0", modifiers: [.command])
        .disabled(zoomActions == nil)

        Button("Zoom to Fit") {
            zoomActions?.zoomToFit()
        }
        .keyboardShortcut("9", modifiers: [.command])
        .disabled(zoomActions == nil)

        Button("Zoom In") {
            zoomActions?.zoomIn()
        }
        .keyboardShortcut("+", modifiers: [.command])
        .disabled(zoomActions?.canZoomIn != true)

        Button("Zoom Out") {
            zoomActions?.zoomOut()
        }
        .keyboardShortcut("-", modifiers: [.command])
        .disabled(zoomActions?.canZoomOut != true)
    }

    // MARK: - Magnifier Section

    @ViewBuilder
    private var magnifierSection: some View {
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

        // Magnifier zoom in
        Button("Magnifier Zoom In") {
            panelMagnification = min(panelMagnification * MagnifierLimits.zoomFactor, MagnifierLimits.maxMagnification)
        }
        .keyboardShortcut("]", modifiers: [.command, .option])
        .disabled(!magnifierEnabled || panelMagnification >= MagnifierLimits.maxMagnification)

        // Magnifier zoom out
        Button("Magnifier Zoom Out") {
            panelMagnification = max(panelMagnification / MagnifierLimits.zoomFactor, MagnifierLimits.minMagnification)
        }
        .keyboardShortcut("[", modifiers: [.command, .option])
        .disabled(!magnifierEnabled || panelMagnification <= MagnifierLimits.minMagnification)
    }

    // MARK: - Loupe Section

    @ViewBuilder
    private var loupeSection: some View {
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
