import AppKit
import SwiftUI

/// Content tab for DocumentInspector showing extracted text content
struct DocumentInspectorContentTab: View {
    let document: Document
    @EnvironmentObject private var documentService: DocumentServiceGenerated
    @EnvironmentObject private var documentStore: DocumentStore
    @AppStorage("editor.rulersVisible") private var rulersVisible = true
    @AppStorage("editor.fontName") private var fontName: String = "System"
    @AppStorage("editor.fontSize") private var fontSize: Double = 14
    @AppStorage("editor.lineSpacing") private var lineSpacing: Double = 4
    @AppStorage("editor.marginHorizontal") private var marginH: Double = 16
    @AppStorage("editor.marginVertical") private var marginV: Double = 12

    @StateObject private var state = DocumentInspectorContentState()
    @State private var autoSaveTask: Task<Void, Never>?

    var body: some View {
        VStack(spacing: 0) {
            editorFormatBar
            Divider()
            editorArea
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onAppear { onViewAppear() }
        .onDisappear { onViewDisappear() }
        .onChange(of: state.documentSignature(for: document)) { _, newSignature in
            handleSignatureChange(newSignature)
        }
    }

    // MARK: - Editor Area

    private var editorArea: some View {
        ZStack(alignment: .topLeading) {
            AttributedTextEditor(
                text: $state.draftAttributedText,
                isEditable: !state.isSaving,
                rulersVisible: rulersVisible,
                fontName: fontName,
                fontSize: fontSize,
                lineSpacing: lineSpacing,
                marginH: marginH,
                marginV: marginV,
                contentRevision: state.editorRevision,
                onTextChanged: {
                    scheduleAutoSave()
                    state.saveError = nil
                },
                onEditingChanged: { isEditing in
                    state.isEditingText = isEditing
                    if !isEditing {
                        scheduleAutoSave(immediate: true)
                    }
                    if !isEditing, state.pendingExternalSignature != nil, !state.hasChanges {
                        state.loadDraft(from: document)
                        state.saveError = nil
                    }
                }
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(.textBackgroundColor))

            placeholderOverlay
            saveStatusOverlay
        }
    }

    private var placeholderOverlay: some View {
        Group {
            if state.draftContent.isEmpty {
                Text("Add notes or edit extracted text...")
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 14)
                    .allowsHitTesting(false)
            }
        }
    }

    @ViewBuilder
    private var saveStatusOverlay: some View {
        if let saveError = state.saveError {
            Text(saveError)
                .font(.caption)
                .foregroundStyle(.red)
                .padding(8)
                .background(.regularMaterial)
                .clipShape(RoundedRectangle(cornerRadius: 6))
                .padding(8)
        } else if state.isSaving {
            HStack(spacing: 6) {
                ProgressView()
                    .controlSize(.small)
                Text("Saving...")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(8)
            .background(.regularMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .padding(8)
        }
    }

    // MARK: - Format Bar

    private var editorFormatBar: some View {
        HStack(spacing: 10) {
            Picker("Font", selection: $fontName) {
                ForEach(state.availableFonts, id: \.self) { name in
                    Text(name).tag(name)
                }
            }
            .frame(maxWidth: 200)

            HStack(spacing: 6) {
                Text("Size")
                    .foregroundStyle(.secondary)
                Stepper(value: $fontSize, in: 8...72, step: 1) {
                    Text("\(Int(fontSize))")
                        .monospacedDigit()
                }
                .labelsHidden()
                .frame(width: 70)
            }

            HStack(spacing: 6) {
                Text("Spacing")
                    .foregroundStyle(.secondary)
                Stepper(value: $lineSpacing, in: 0...24, step: 1) {
                    Text("\(Int(lineSpacing))")
                        .monospacedDigit()
                }
                .labelsHidden()
                .frame(width: 70)
            }

            Toggle("Ruler", isOn: $rulersVisible)
                .toggleStyle(.checkbox)

            Spacer()
        }
        .font(.caption)
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(Color(nsColor: .windowBackgroundColor))
    }

    // MARK: - Lifecycle

    private func onViewAppear() {
        if state.availableFonts.isEmpty {
            state.availableFonts = ["System"] + NSFontManager.shared.availableFonts
                .filter { !$0.hasPrefix(".") }
                .sorted()
        }
        state.loadDraft(from: document)
    }

    private func onViewDisappear() {
        autoSaveTask?.cancel()
        autoSaveTask = nil
    }

    private func handleSignatureChange(_ newSignature: String) {
        guard newSignature != state.lastLoadedSignature else { return }
        if state.isEditingText && state.hasChanges {
            state.pendingExternalSignature = newSignature
            return
        }
        state.loadDraft(from: document)
        state.saveError = nil
    }

    // MARK: - Auto-Save

    private func scheduleAutoSave(immediate: Bool = false) {
        autoSaveTask?.cancel()
        autoSaveTask = Task { @MainActor in
            if !immediate {
                try? await Task.sleep(nanoseconds: 600_000_000)
            }
            guard !Task.isCancelled else { return }
            await state.saveContent(
                document: document,
                documentService: documentService,
                documentStore: documentStore
            )
        }
    }
}
