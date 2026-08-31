import SwiftUI

extension ImageEditorView {
    var toolbar: some View {
        HStack(spacing: 12) {
            // The way OUT (2026-08-30): edits are committed as you Apply, so
            // Done just returns to Preview — no separate save step exists,
            // and the button says so.
            if let onDone {
                Button {
                    onDone()
                } label: {
                    Label("Done", systemImage: "checkmark.circle.fill")
                        .labelStyle(.titleAndIcon)
                }
                .buttonStyle(.borderless)
                .foregroundStyle(Color.accentColor)
                .help("Done — edits are already saved; return to Preview")
                .accessibilityIdentifier("imageEditDone")

                Divider().frame(height: 20)
            }

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
            // labelsHidden, or macOS squeezes "Show image as" into a
            // one-character column beside the segments — Daniel's unreadable
            // "S h" (2026-08-21). Icons + help + accessibility carry it.
            .labelsHidden()
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
                .accessibilityLabel("Enhance")
                .popover(isPresented: $showEnhancePopover, arrowEdge: .bottom) { enhancePopover }

                // Rotate-angle with slider popover (#3673) — a fine straighten/
                // rotate angle, live-previewed client-side while dragging.
                Button {
                    showRotatePopover = true
                } label: {
                    Image(systemName: "angle")
                }
                .buttonStyle(.borderless)
                .help("Rotate — fine straighten angle")
                .accessibilityLabel("Rotate")
                .popover(isPresented: $showRotatePopover, arrowEdge: .bottom) { rotatePopover }

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

            Divider().frame(height: 20)

            // Undo / Revert (Daniel, 2026-08-31). Steps commit on Apply, so
            // Undo rewrites the saved chain minus its last step and Revert
            // clears it — both are server truth, hence the busy gating.
            // No .keyboardShortcut here: ⌘Z has ONE owner, the Edit menu's
            // UndoLastActionButton, which routes to the editor via the
            // imageEditUndoAction focused value (#4354).
            toolButton("arrow.uturn.backward", help: "Undo — remove the last edit step (⌘Z)") {
                Task { await model.undoLastStep() }
            }
            .disabled(model.isBusy || model.chain.isEmpty)
            .accessibilityIdentifier("imageEditUndo")

            toolButton("arrow.counterclockwise.circle", help: "Revert to Original — discard all edits") {
                showRevertConfirm = true
            }
            .disabled(model.isBusy || model.chain.isEmpty)
            .accessibilityIdentifier("imageEditRevertToOriginal")
            .confirmationDialog(
                "Revert to the original image?",
                isPresented: $showRevertConfirm,
                titleVisibility: .visible
            ) {
                Button("Revert to Original", role: .destructive) {
                    Task { await model.resetAll() }
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("This discards all \(model.chain.operations.count) saved edit step(s). The original file is never changed.")
            }

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
            .labelsHidden()  // same one-character-column squeeze ("C o")
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
        // Tahoe/Golden-Gate Liquid Glass, matching MiniToolbar / SidebarModeBar /
        // the library bars instead of a solid window-background fill (#3038).
        .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 10))
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
            .accessibilityLabel("Previous image")
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
            .accessibilityLabel("Next image")
            .accessibilityIdentifier("imageEditorNext")
        }
    }

    /// Move `delta` positions through editable siblings, loading the neighbour and
    /// (if wired) syncing app selection so the window inspector follows.
    func step(by delta: Int) async {
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

    func currentPage(for doc: Document) -> Int {
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
        .accessibilityLabel(help)
    }

    private var editedBinding: Binding<Bool> {
        Binding(
            get: { model.showEdited },
            set: { newValue in if newValue != model.showEdited { model.setShowEdited(newValue) } }
        )
    }
}
