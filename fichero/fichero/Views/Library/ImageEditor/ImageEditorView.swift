import AppKit
import SwiftUI

/// Non-destructive image-editing surface (#469).
///
/// Renders the backend-rendered preview (so the original↔edited toggle is just
/// `apply_edits=false|true` on `/images/{id}/preview`), exposes the edit-chain
/// operations as controls, and shows the chain inspector alongside.
///
/// Mounted from `EditorView` for `fileType == .image` documents. Prev/next
/// navigation (#1265) and rubber-band crop/batch (#1265) layer on top in
/// follow-up commits.
struct ImageEditorView: View {
    let document: Document

    @EnvironmentObject private var apiClient: APIClient
    @StateObject private var model = ImageEditorModel()

    // Enhance popover state (sliders default to "no change" = 1.0).
    @State private var brightness: Double = 1.0
    @State private var contrast: Double = 1.0
    @State private var sharpen: Double = 1.0
    @State private var showEnhancePopover = false

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()
            HStack(spacing: 0) {
                canvas
                Divider()
                ImageEditChainPanel(
                    chain: model.chain,
                    isBusy: model.isBusy,
                    onRemove: { index in Task { await model.removeOperation(at: index) } },
                    onReset: { Task { await model.resetAll() } }
                )
                .frame(width: 260)
            }
        }
        .task(id: document.id) {
            await model.configure(apiClient: apiClient, documentId: document.id)
        }
        .alert(
            "Image edit failed",
            isPresented: Binding(
                get: { model.errorMessage != nil },
                set: { if !$0 { model.errorMessage = nil } }
            )
        ) {
            Button("OK", role: .cancel) { model.errorMessage = nil }
        } message: {
            Text(model.errorMessage ?? "")
        }
    }

    // MARK: - Toolbar

    private var toolbar: some View {
        HStack(spacing: 12) {
            // #469 original↔edited toggle.
            Picker("", selection: editedBinding) {
                Text("Original").tag(false)
                Text("Edited").tag(true)
            }
            .pickerStyle(.segmented)
            .frame(width: 160)
            .labelsHidden()
            .help("Compare the original image with the edited result")
            .accessibilityIdentifier("imageEditOriginalEditedToggle")

            Divider().frame(height: 20)

            Group {
                toolButton("rotate.left", help: "Rotate left 90°") {
                    Task { await model.rotate(by: 90) }
                }
                toolButton("rotate.right", help: "Rotate right 90°") {
                    Task { await model.rotate(by: -90) }
                }

                Button {
                    showEnhancePopover = true
                } label: {
                    Image(systemName: "wand.and.stars")
                }
                .buttonStyle(.borderless)
                .help("Enhance — brightness, contrast, sharpen")
                .popover(isPresented: $showEnhancePopover, arrowEdge: .bottom) { enhancePopover }

                toolButton("person.crop.rectangle.badge.xmark", help: "Remove background") {
                    Task { await model.removeBackground() }
                }
                toolButton("square.split.bottomrightquarter", help: "Segment into regions") {
                    Task { await model.segment() }
                }
            }
            .disabled(model.isBusy)

            Spacer()

            if model.isBusy {
                ProgressView().controlSize(.small)
            }
        }
        .padding(.horizontal, 12)
        .frame(height: 44)
        .background(Color(.windowBackgroundColor))
    }

    private func toolButton(_ systemImage: String, help: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemImage)
        }
        .buttonStyle(.borderless)
        .help(help)
    }

    private var editedBinding: Binding<Bool> {
        Binding(
            get: { model.showEdited },
            set: { newValue in if newValue != model.showEdited { model.toggleEdited() } }
        )
    }

    // MARK: - Enhance popover

    private var enhancePopover: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Enhance").font(.headline)
            enhanceSlider("Brightness", value: $brightness)
            enhanceSlider("Contrast", value: $contrast)
            enhanceSlider("Sharpen", value: $sharpen)
            HStack {
                Button("Auto Levels") {
                    Task { await model.enhance(brightness: 1, contrast: 1, sharpen: 1, autoLevels: true) }
                    showEnhancePopover = false
                }
                Spacer()
                Button("Apply") {
                    Task {
                        await model.enhance(
                            brightness: brightness,
                            contrast: contrast,
                            sharpen: sharpen,
                            autoLevels: false
                        )
                    }
                    resetEnhanceSliders()
                    showEnhancePopover = false
                }
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(16)
        .frame(width: 260)
    }

    private func enhanceSlider(_ label: String, value: Binding<Double>) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(label).font(.subheadline)
                Spacer()
                Text(String(format: "%.2f×", value.wrappedValue))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            Slider(value: value, in: 0.0...2.0)
        }
    }

    private func resetEnhanceSliders() {
        brightness = 1.0
        contrast = 1.0
        sharpen = 1.0
    }

    // MARK: - Canvas

    private var canvas: some View {
        ZStack {
            CheckerboardPattern().opacity(0.12)
            if let preview = model.preview {
                Image(nsImage: preview.image)
                    .resizable()
                    .interpolation(.high)
                    .aspectRatio(contentMode: .fit)
                    .padding(12)
            } else {
                ProgressView("Loading image…")
                    .controlSize(.small)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(nsColor: NSColor(red: 253 / 255, green: 253 / 255, blue: 253 / 255, alpha: 1)))
    }
}
