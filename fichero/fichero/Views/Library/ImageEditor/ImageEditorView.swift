#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif
import SwiftUI

// swiftlint:disable file_length

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
    @EnvironmentObject private var storageService: StorageServiceGenerated
    @Environment(DocumentStore.self) private var documentStore: DocumentStore
    @State private var model = ImageEditorModel()

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

    @Environment(AnnotationStore.self) private var annotationStore

    /// Editable docs in the current multi-selection (for batch-apply).
    private var selectedEditableDocs: [Document] {
        siblingEditableDocs.filter { selectedDocumentIDs.contains($0.id) }
    }

    /// Sibling editable docs in the current folder, in display order —
    /// the prev/next set for image files and PDF pages.
    private var siblingEditableDocs: [Document] {
        documentStore.currentDocuments.filter { $0.fileType == .image || $0.docType == .page }
    }

    /// The document the editor is actually showing (resolved from the active id).
    private var activeDocument: Document {
        siblingEditableDocs.first(where: { $0.id == activeDocumentID })
            ?? documentStore.currentDocuments.first(where: { $0.id == activeDocumentID })
            ?? document
    }

    private var currentIndex: Int? {
        siblingEditableDocs.firstIndex(where: { $0.id == activeDocument.id })
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
            await model.configure(
                apiClient: apiClient,
                documentId: document.id,
                page: currentPage(for: document)
            )
            // Invalidate the storage-display cache after every successful edit so
            // StorageDisplayImageCanvas re-fetches edited bytes when exiting edit
            // mode (#2459 / #2469).
            model.onEditApplied = { [storageService] id in
                storageService.invalidateImageCache(for: id)
            }
        }
        .onChange(of: model.chain.operations.count) { _, _ in
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

            // Original ↔ Edited — icon-only segmented control (#1420).
            Picker("Show image as", selection: editedBinding) {
                Image(systemName: "photo").tag(false)
                    .accessibilityLabel("Original — unedited source image")
                Image(systemName: "wand.and.stars").tag(true)
                    .accessibilityLabel("Edited — with all applied edits")
            }
            .pickerStyle(.segmented)
            .frame(width: 64)
            .help(model.showEdited
                  ? "Showing edited version — click to compare original"
                  : "Showing original — click to show with edits applied")
            .accessibilityIdentifier("imageEditOriginalEditedToggle")

            Divider().frame(height: 20)

            // Edit tools — icon-only SF Symbols (#1420 spec).
            Group {
                toolButton("rotate.left", help: "Rotate left 90°") {
                    Task { await model.rotate(by: 90) }
                }
                toolButton("rotate.right", help: "Rotate right 90°") {
                    Task { await model.rotate(by: -90) }
                }
                toolButton("crop.rotate", help: "Straighten — auto-detect document skew") {
                    Task { await model.straighten() }
                }

                // Enhance with slider popover
                Button {
                    showEnhancePopover = true
                } label: {
                    Image(systemName: "slider.horizontal.3")
                }
                .buttonStyle(.borderless)
                .help("Enhance — adjust brightness, contrast, sharpen")
                .popover(isPresented: $showEnhancePopover, arrowEdge: .bottom) { enhancePopover }

                toolButton("person.and.background.dotted", help: "Remove background — AI-powered background removal") {
                    Task { await model.removeBackground() }
                }
                toolButton("sparkles", help: "Despeckle — remove noise and speckle artifacts") {
                    Task { await model.fuzzyClean() }
                }
                toolButton("square.split.2x1", help: "Segment — detect and label image regions") {
                    Task { await model.segment() }
                }
            }
            .disabled(model.isBusy)

            if marqueeSelection != nil && compareMode == .single {
                Divider().frame(height: 20)
                toolButton("crop", help: "Crop to selection") {
                    Task { await cropToSelection() }
                }
                .disabled(model.isBusy)
                .accessibilityIdentifier("imageEditCropToSelection")
                toolButton("highlighter", help: "Save selection as annotation") {
                    Task { await annotateSelection() }
                }
                .disabled(model.isBusy)
                .accessibilityIdentifier("imageEditAnnotateSelection")
            }

            if selectedEditableDocs.count > 1 {
                Divider().frame(height: 20)
                batchMenu
            }

            Spacer()

            // Compare mode — icon-only segmented (#1420 spec).
            Picker("Compare mode", selection: $compareMode) {
                Image(systemName: "rectangle")
                    .tag(CompareMode.single)
                    .accessibilityLabel("Single — show one view of the image")
                Image(systemName: "rectangle.righthalf.inset.filled.arrow.right")
                    .tag(CompareMode.wipe)
                    .accessibilityLabel("Slider — drag to wipe between original and edited")
                Image(systemName: "rectangle.split.2x1")
                    .tag(CompareMode.sideBySide)
                    .accessibilityLabel("Side-by-Side — original and edited in split view")
            }
            .pickerStyle(.segmented)
            .frame(width: 96)
            .help("Compare mode — Single view, Slider wipe, or Side-by-Side")

            if model.isBusy {
                ProgressView().controlSize(.small)
            }
        }
        .padding(.horizontal, 12)
        // Single source of truth for top-toolbar height so the image-edit
        // toolbar lines up with every other pane mini-toolbar (#1449/#1460).
        .frame(height: MiniToolbar<EmptyView, EmptyView>.standardHeight)
        .background(Color(.windowBackgroundColor))
    }

    /// Prev/next stepping through sibling images (#1265).
    @ViewBuilder
    private var navigationCluster: some View {
        let index = currentIndex
        let total = siblingEditableDocs.count
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

    /// Move `delta` positions through editable siblings, loading the neighbour and
    /// (if wired) syncing app selection so the window inspector follows.
    private func step(by delta: Int) async {
        guard let index = currentIndex else { return }
        let target = index + delta
        guard siblingEditableDocs.indices.contains(target) else { return }
        let neighbour = siblingEditableDocs[target]
        activeDocumentID = neighbour.id
        marqueeSelection = nil
        onNavigate?(neighbour.id)
        await model.configure(
            apiClient: apiClient,
            documentId: neighbour.id,
            page: currentPage(for: neighbour)
        )
    }

    /// Batch-apply menu (#1265) — fans a uniform op out across the multi-file
    /// selection client-side. Region crop is excluded: a marquee bbox is in one
    /// image's pixel space and doesn't translate across differently-sized files.
    private var batchMenu: some View {
        Menu {
            Button("Rotate Right 90°") {
                Task {
                    await model.batchApply(documentIds: selectedEditableDocs.map(\.id)) { service, id in
                        try await service.rotate(documentId: id, angle: -90)
                    }
                }
            }
            Button("Straighten") {
                Task {
                    await model.batchApply(documentIds: selectedEditableDocs.map(\.id)) { service, id in
                        try await service.straighten(documentId: id)
                    }
                }
            }
            Button("Auto-Enhance") {
                Task {
                    await model.batchApply(documentIds: selectedEditableDocs.map(\.id)) { service, id in
                        try await service.enhance(documentId: id, autoLevels: true)
                    }
                }
            }
            Button("Remove Background") {
                Task {
                    await model.batchApply(documentIds: selectedEditableDocs.map(\.id)) { service, id in
                        try await service.removeBackground(documentId: id)
                    }
                }
            }
        } label: {
            Label("Apply to \(selectedEditableDocs.count)", systemImage: "square.stack.3d.up")
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
        .disabled(model.isBusy)
        .help("Apply an edit to all \(selectedEditableDocs.count) selected files/pages")
        .accessibilityIdentifier("imageEditBatchMenu")
    }

    private func currentPage(for doc: Document) -> Int {
        if doc.docType == .page {
            return max(1, doc.sequence ?? 1)
        }
        return 1
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
        let created = await annotationStore.addNote(
            scope: .document(activeDocument.id),
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
            set: { newValue in if newValue != model.showEdited { model.setShowEdited(newValue) } }
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
                        let split = max(0, min(1, compareSplit))
                        ZStack(alignment: .topLeading) {
                            // Edited underneath — full size (revealed on the right).
                            Image(platformImage: edited.image)
                                .resizable()
                                .interpolation(.high)
                                .aspectRatio(contentMode: .fit)
                                .frame(width: frame.width, height: frame.height)
                            // Original on top — clipped to the left split portion,
                            // so left = Before (original), right = After (edited)
                            // and the labels below read correctly (#1538).
                            Image(platformImage: original.image)
                                .resizable()
                                .interpolation(.high)
                                .aspectRatio(contentMode: .fit)
                                .frame(width: frame.width, height: frame.height)
                                .frame(width: split * frame.width, height: frame.height, alignment: .leading)
                                .clipped()
                            // Divider line
                            Rectangle()
                                .fill(Color.white.opacity(0.9))
                                .frame(width: 2, height: frame.height)
                                .offset(x: split * frame.width - 1)
                            // Before / After labels
                            HStack(spacing: 0) {
                                Text("Before")
                                    .font(.caption2.weight(.medium))
                                    .padding(.horizontal, 5).padding(.vertical, 2)
                                    .background(Color.black.opacity(0.45))
                                    .foregroundStyle(.white)
                                    .cornerRadius(3)
                                    .padding(.leading, 6).padding(.top, 6)
                                    .opacity(split > 0.1 ? 1 : 0)
                                Spacer()
                                Text("After")
                                    .font(.caption2.weight(.medium))
                                    .padding(.horizontal, 5).padding(.vertical, 2)
                                    .background(Color.black.opacity(0.45))
                                    .foregroundStyle(.white)
                                    .cornerRadius(3)
                                    .padding(.trailing, 6).padding(.top, 6)
                                    .opacity(split < 0.9 ? 1 : 0)
                            }
                            .frame(width: frame.width)
                            // Drag handle on divider
                            Image(systemName: "arrow.left.and.right")
                                .font(.caption2)
                                .padding(5)
                                .background(Color.white.opacity(0.88))
                                .clipShape(Circle())
                                .offset(x: split * frame.width - 11, y: frame.height / 2 - 11)
                        }
                        .frame(width: frame.width, height: frame.height)
                        .offset(x: frame.minX, y: frame.minY)
                        // Drag on the image to adjust the wipe position
                        .gesture(
                            DragGesture(minimumDistance: 0)
                                .onChanged { value in
                                    compareSplit = max(0, min(1, value.location.x / frame.width))
                                }
                        )
                    }
                } else {
                    ProgressView("Loading compare preview…")
                        .controlSize(.small)
                }
            } else {
                // Single-mode: DocumentCanvas gives zoom/loupe/magnifier (#1402).
                // Shows last rendered frame while loading (model.preview?.image may
                // be nil briefly after an op; canvas retains the stale frame).
                DocumentCanvas(
                    content: .imageRendered(
                        image: model.preview?.image,
                        documentId: activeDocumentID
                    )
                )
            }

            // Busy overlay for any in-flight edit/load, in every compare mode
            // (#1532). Translucent so the last image stays visible mid-op; the
            // labelled spinner makes clear a potentially-slow op (remove-bg,
            // despeckle, enhance) is actually running.
            if model.isBusy {
                Color.black.opacity(0.10).allowsHitTesting(false)
                ProgressView("Working…")
                    .controlSize(.small)
                    .padding(10)
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
                    .allowsHitTesting(false)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(platformColor: .textBackgroundColor))
    }

    private func comparePane(image: PlatformImage, pixelSize: CGSize, title: String) -> some View {
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
                Image(platformImage: image)
                    .resizable()
                    .interpolation(.high)
                    .aspectRatio(contentMode: .fit)
                    .frame(width: frame.width, height: frame.height)
                    .position(x: frame.midX, y: frame.midY)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
