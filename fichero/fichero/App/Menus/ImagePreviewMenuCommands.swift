import SwiftUI

/// Menu commands for image preview controls (zoom, magnifier panel, loupe)
struct ImagePreviewMenuCommands: View {
    // MARK: - Constants

    private enum MagnifierLimits {
        static let minMagnification: Double = 0.25
        static let maxMagnification: Double = 16.0
        static let zoomFactor: Double = 1.5
    }

    // MARK: - Focused Values

    @FocusedValue(\.imageZoomActions) private var zoomActions
    private var hasActiveImagePreview: Bool { zoomActions != nil }

    // MARK: - Storage

    @AppStorage("imagePreview.magnifierEnabled") private var magnifierEnabled = false
    @AppStorage("imagePreview.loupeEnabled") private var loupeEnabled = false
    @AppStorage("imagePreview.magnifierLocked") private var magnifierLocked = false
    @AppStorage("imagePreview.loupeLocked") private var loupeLocked = false
    @AppStorage("imagePreview.loupeMagnification") private var loupeMagnification: Double = 3.0
    @AppStorage("imagePreview.loupeSize") private var loupeSize: Double = 150.0
    @AppStorage("imagePreview.panelMagnification") private var panelMagnification: Double = 4.0
    @AppStorage("imagePreview.panelHeight") private var panelHeight: Double = 120.0

    // MARK: - Body

    var body: some View {
        // One "Zoom" submenu instead of 14 flat rows (#4121 View-menu diet —
        // Preview.app's own pattern). Keyboard shortcuts keep working from
        // the submenu; content and gating are unchanged.
        Menu("Zoom") {
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
        .disabled(!hasActiveImagePreview)

        Button("Zoom to Fit") {
            zoomActions?.zoomToFit()
        }
        .keyboardShortcut("9", modifiers: [.command])
        .disabled(!hasActiveImagePreview)

        Button("Zoom In") {
            zoomActions?.zoomIn()
        }
        .keyboardShortcut("+", modifiers: [.command])
        .disabled(!hasActiveImagePreview || zoomActions?.canZoomIn != true)

        Button("Zoom Out") {
            zoomActions?.zoomOut()
        }
        .keyboardShortcut("-", modifiers: [.command])
        .disabled(!hasActiveImagePreview || zoomActions?.canZoomOut != true)
    }

    // MARK: - Magnifier Section

    @ViewBuilder
    private var magnifierSection: some View {
        // Magnifier panel toggle (⌘⇧M)
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
        .keyboardShortcut("m", modifiers: [.command, .shift])
        .disabled(!hasActiveImagePreview)

        // Lock magnifier (⌘⌥M — freezes focus point at last location)
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
        .keyboardShortcut("m", modifiers: [.command, .option])
        .disabled(!hasActiveImagePreview || !magnifierEnabled)

        // Magnifier zoom in
        Button("Magnifier Zoom In") {
            panelMagnification = min(panelMagnification * MagnifierLimits.zoomFactor, MagnifierLimits.maxMagnification)
        }
        .keyboardShortcut("]", modifiers: [.command, .option])
        .disabled(!hasActiveImagePreview || !magnifierEnabled || panelMagnification >= MagnifierLimits.maxMagnification)

        // Magnifier zoom out
        Button("Magnifier Zoom Out") {
            panelMagnification = max(panelMagnification / MagnifierLimits.zoomFactor, MagnifierLimits.minMagnification)
        }
        .keyboardShortcut("[", modifiers: [.command, .option])
        .disabled(!hasActiveImagePreview || !magnifierEnabled || panelMagnification <= MagnifierLimits.minMagnification)
    }

    // MARK: - Loupe Section

    @ViewBuilder
    private var loupeSection: some View {
        // Loupe toggle (L for Loupe)
        Button {
            loupeEnabled.toggle()
        } label: {
            HStack {
                if loupeEnabled {
                    Image(systemName: "checkmark")
                }
                Label("Loupe", systemImage: "magnifyingglass.circle")
            }
        }
        .keyboardShortcut("l", modifiers: [.command, .option])
        .disabled(!hasActiveImagePreview)

        // Lock loupe toggle (Shift + toggle shortcut)
        Button {
            loupeLocked.toggle()
        } label: {
            HStack {
                if loupeLocked {
                    Image(systemName: "checkmark")
                }
                Label("Lock Loupe", systemImage: "lock")
            }
        }
        .keyboardShortcut("l", modifiers: [.command, .shift])
        .disabled(!hasActiveImagePreview || !loupeEnabled)

        // Loupe zoom in
        Button("Loupe Zoom In") {
            loupeMagnification = min(loupeMagnification * MagnifierLimits.zoomFactor, MagnifierLimits.maxMagnification)
        }
        .keyboardShortcut("]", modifiers: [.command, .control])
        .disabled(!hasActiveImagePreview || !loupeEnabled || loupeMagnification >= MagnifierLimits.maxMagnification)

        // Loupe zoom out
        Button("Loupe Zoom Out") {
            loupeMagnification = max(loupeMagnification / MagnifierLimits.zoomFactor, MagnifierLimits.minMagnification)
        }
        .keyboardShortcut("[", modifiers: [.command, .control])
        .disabled(!hasActiveImagePreview || !loupeEnabled || loupeMagnification <= MagnifierLimits.minMagnification)
    }
}
