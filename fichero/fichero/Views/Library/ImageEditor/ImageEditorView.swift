import AppKit
import SwiftUI

private enum CompareMode: String, CaseIterable {
    case single = "Single"
    case wipe = "Slider"
    case sideBySide = "Side-by-Side"
}

/// Non-destructive image-editing surface (#469).
///
/// Renders the backend-rendered preview (so the original↔edited toggle is just
/// `apply_edits=false|true` on `/images/{id}/preview`), exposes the edit-chain
/// operations as controls.
///
/// Mounted from `EditorView` for `fileType == .image` documents. Prev/next
/// navigation (#1265) and rubber-band crop/batch (#1265) layer on top in
/// follow-up commits.
struct ImageEditorView: View {
    let document: Document
    /// Optional hook so the host can sync app selection when the user steps to
    /// a sibling image, keeping the window-level inspector pointed at the same
    /// document (#1265). When nil, navigation is still handled internally.
    var onNavigate: ((String) -> Void)?
    /// Multi-file selection (image document ids) for batch-apply (#1265).
    var selectedDocumentIDs: Set<String> = []

    @EnvironmentObject private var apiClient: APIClient
    @EnvironmentObject private var documentStore: DocumentStore
    @StateObject private var model = ImageEditorModel()

    /// Document currently loaded in the editor. Seeded from `document` and
    /// updated by prev/next so the canvas follows even when the host doesn't
    /// wire `onNavigate`.
    @State private var activeDocumentID: String = ""

    // Enhance popover state (sliders default to "no change" = 1.0).
    @State private var brightness: Double = 1.0
    @State private var contrast: Double = 1.0
    @State private var sharpen: Double = 1.0
    @State private var showEnhancePopover = false

    /// Marquee selection in normalized image space (0…1); nil when none (#1265).
    @State private var marqueeSelection: CGRect?
    @State private var compareMode: CompareMode = .single
    @State private var compareSplit: CGFloat = 0.5

    /// Creates region (bbox) annotations from the marquee selection (#1276).
    @StateObject private var annotationService = AnnotationService()

    /// Image documents in the current multi-selection (for batch-apply).
    private var selectedImages: [Document] {
        siblingImages.filter { selectedDocumentIDs.contains($0.id) }
    }

    /// Sibling images in the current folder, in display order — the prev/next set.
    private var siblingImages: [Document] {
        documentStore.currentDocuments.filter { $0.fileType == .image }
    }

    /// The document the editor is actually showing (resolved from the active id).
    private var activeDocument: Document {
        siblingImages.first(where: { $0.id == activeDocumentID })
            ?? documentStore.currentDocuments.first(where: { $0.id == activeDocumentID })
            ?? document
    }

    private var currentIndex: Int? {
        siblingImages.firstIndex(where: { $0.id == activeDocument.id })
    }

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()
            canvas
        }
        .task(id: document.id) {
            // External selection changed (host drove a new document).
            activeDocumentID = document.id
            marqueeSelection = nil
            await model.configure(apiClient: apiClient, documentId: document.id)
        }
        .onChange(of: model.chain.operations.count) { _ in
            // An op changed the rendered image — a stale region would mismap.
            marqueeSelection = nil
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
}

// MARK: - Toolbar, controls, canvas

private extension ImageEditorView {
    var toolbar: some View {
        HStack(spacing: 12) {
            navigationCluster

            Divider().frame(height: 20)

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

            if marqueeSelection != nil && compareMode == .single {
                Divider().frame(height: 20)
                Button {
                    Task { await cropToSelection() }
                } label: {
                    Label("Crop", systemImage: "crop")
                }
                .disabled(model.isBusy)
                .help("Crop the image to the selected region")
                .accessibilityIdentifier("imageEditCropToSelection")

                Button {
                    Task { await annotateSelection() }
                } label: {
                    Label("Annotate", systemImage: "highlighter")
                }
                .disabled(model.isBusy)
                .help("Save the selected region as an annotation on this image")
                .accessibilityIdentifier("imageEditAnnotateSelection")
            }

            if selectedImages.count > 1 {
                Divider().frame(height: 20)
                batchMenu
            }

            Spacer()

            Picker("", selection: $compareMode) {
                ForEach(CompareMode.allCases, id: \.self) { mode in
                    Text(mode.rawValue).tag(mode)
                }
            }
            .pickerStyle(.segmented)
            .frame(width: 240)
            .labelsHidden()
            .help("Compare original and edited images")

            if model.isBusy {
                ProgressView().controlSize(.small)
            }
        }
        .padding(.horizontal, 12)
        .frame(height: 44)
        .background(Color(.windowBackgroundColor))
    }

    /// Prev/next stepping through sibling images (#1265).
    @ViewBuilder
    private var navigationCluster: some View {
        let index = currentIndex
        let total = siblingImages.count
        HStack(spacing: 6) {
            Button {
                Task { await step(by: -1) }
            } label: {
                Image(systemName: "chevron.left")
            }
            .buttonStyle(.borderless)
            .disabled(model.isBusy || (index ?? 0) <= 0)
            .help("Previous image")
            .accessibilityIdentifier("imageEditorPrev")

            if let index, total > 0 {
                Text("\(index + 1) / \(total)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
                    .frame(minWidth: 44)
            }

            Button {
                Task { await step(by: 1) }
            } label: {
                Image(systemName: "chevron.right")
            }
            .buttonStyle(.borderless)
            .disabled(model.isBusy || index == nil || (index ?? 0) >= total - 1)
            .help("Next image")
            .accessibilityIdentifier("imageEditorNext")
        }
    }

    /// Move `delta` positions through `siblingImages`, loading the neighbour and
    /// (if wired) syncing app selection so the window inspector follows.
    private func step(by delta: Int) async {
        guard let index = currentIndex else { return }
        let target = index + delta
        guard siblingImages.indices.contains(target) else { return }
        let neighbour = siblingImages[target]
        activeDocumentID = neighbour.id
        marqueeSelection = nil
        onNavigate?(neighbour.id)
        await model.configure(apiClient: apiClient, documentId: neighbour.id)
    }

    /// Batch-apply menu (#1265) — fans a uniform op out across the multi-file
    /// selection client-side. Region crop is excluded: a marquee bbox is in one
    /// image's pixel space and doesn't translate across differently-sized files.
    private var batchMenu: some View {
        Menu {
            Button("Rotate Right 90°") {
                Task {
                    await model.batchApply(documentIds: selectedImages.map(\.id)) { service, id in
                        try await service.rotate(documentId: id, angle: -90)
                    }
                }
            }
            Button("Auto-Enhance") {
                Task {
                    await model.batchApply(documentIds: selectedImages.map(\.id)) { service, id in
                        try await service.enhance(documentId: id, autoLevels: true)
                    }
                }
            }
            Button("Remove Background") {
                Task {
                    await model.batchApply(documentIds: selectedImages.map(\.id)) { service, id in
                        try await service.removeBackground(documentId: id)
                    }
                }
            }
        } label: {
            Label("Apply to \(selectedImages.count)", systemImage: "square.stack.3d.up")
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
        .disabled(model.isBusy)
        .help("Apply an edit to all \(selectedImages.count) selected images")
        .accessibilityIdentifier("imageEditBatchMenu")
    }

    /// Map the marquee (normalized image space) to source pixels and crop.
    private func cropToSelection() async {
        guard let selection = marqueeSelection, let pixelSize = model.preview?.pixelSize else { return }
        let left = Int((selection.minX * pixelSize.width).rounded())
        let top = Int((selection.minY * pixelSize.height).rounded())
        let width = Int((selection.width * pixelSize.width).rounded())
        let height = Int((selection.height * pixelSize.height).rounded())
        guard width > 0, height > 0 else { return }
        await model.crop(left: left, top: top, width: width, height: height)
        marqueeSelection = nil
    }

    /// Persist the marquee as a region annotation (`bbox` = [x, y, width, height]
    /// as 0…1 fractions of the image) on the active document (#1276). Clears the
    /// selection on success so the toolbar reverts to its normal state.
    private func annotateSelection() async {
        guard let selection = marqueeSelection, selection.width > 0, selection.height > 0 else { return }
        let bbox = [
            Double(selection.minX),
            Double(selection.minY),
            Double(selection.width),
            Double(selection.height)
        ]
        let created = await annotationService.addNote(
            documentId: activeDocument.id,
            text: "",
            bbox: bbox,
            kind: .highlight
        )
        if created != nil { marqueeSelection = nil }
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
            if compareMode == .sideBySide {
                if let original = model.originalPreview, let edited = model.editedPreview {
                    HStack(spacing: 8) {
                        comparePane(image: original.image, pixelSize: original.pixelSize, title: "Original")
                        comparePane(image: edited.image, pixelSize: edited.pixelSize, title: "Edited")
                    }
                    .padding(8)
                } else {
                    ProgressView("Loading compare preview…")
                        .controlSize(.small)
                }
            } else if compareMode == .wipe {
                if let original = model.originalPreview, let edited = model.editedPreview {
                    GeometryReader { geo in
                        let fitted = ImageFit.fittedRect(
                            imagePixelSize: edited.pixelSize,
                            in: CGSize(width: geo.size.width - 24, height: geo.size.height - 24)
                        )
                        let frame = fitted.offsetBy(dx: 12, dy: 12)
                        Image(nsImage: original.image)
                            .resizable()
                            .interpolation(.high)
                            .frame(width: frame.width, height: frame.height)
                            .position(x: frame.midX, y: frame.midY)
                        Image(nsImage: edited.image)
                            .resizable()
                            .interpolation(.high)
                            .frame(width: frame.width, height: frame.height)
                            .position(x: frame.midX, y: frame.midY)
                            .mask(
                                Rectangle()
                                    .frame(width: max(0, min(1, compareSplit)) * frame.width, height: frame.height)
                                    .offset(x: frame.minX, y: frame.minY)
                            )
                    }
                    VStack {
                        Spacer()
                        Slider(value: $compareSplit, in: 0...1)
                            .padding(.horizontal, 24)
                            .padding(.bottom, 12)
                    }
                } else {
                    ProgressView("Loading compare preview…")
                        .controlSize(.small)
                }
            } else if let preview = model.preview {
                GeometryReader { geo in
                    let fitted = ImageFit.fittedRect(
                        imagePixelSize: preview.pixelSize,
                        in: CGSize(width: geo.size.width - 24, height: geo.size.height - 24)
                    )
                    // Re-centre into the padded container.
                    let frame = fitted.offsetBy(dx: 12, dy: 12)
                    Image(nsImage: preview.image)
                        .resizable()
                        .interpolation(.high)
                        .frame(width: frame.width, height: frame.height)
                        .position(x: frame.midX, y: frame.midY)
                    ImageMarqueeOverlay(fittedRect: frame, normalizedSelection: $marqueeSelection)
                }
            } else {
                ProgressView("Loading image…")
                    .controlSize(.small)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(nsColor: NSColor(red: 253 / 255, green: 253 / 255, blue: 253 / 255, alpha: 1)))
    }

    private func comparePane(image: NSImage, pixelSize: CGSize, title: String) -> some View {
        VStack(spacing: 6) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            GeometryReader { geo in
                let fitted = ImageFit.fittedRect(
                    imagePixelSize: pixelSize,
                    in: CGSize(width: geo.size.width - 12, height: geo.size.height - 12)
                )
                let frame = fitted.offsetBy(dx: 6, dy: 6)
                Image(nsImage: image)
                    .resizable()
                    .interpolation(.high)
                    .frame(width: frame.width, height: frame.height)
                    .position(x: frame.midX, y: frame.midY)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
