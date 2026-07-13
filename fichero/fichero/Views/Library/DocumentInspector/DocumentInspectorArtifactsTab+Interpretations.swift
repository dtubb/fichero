import FicheroAPIClient
import SwiftUI

// MARK: - Hermeneutics interpretations panel

/// Shows interpretations for this document + inline "New Interpretation" form.
/// Always visible so the user can create the first interpretation even when none exist.
struct DocumentInterpretationsSection: View { // swiftlint:disable:this type_body_length
    let documentId: String
    @Environment(InterpretationStore.self) private var store

    // Live-refresh via the per-document InterpretationStore (#2009): the store
    // owns the fetch + the `interpretation.*` change-stream reactions (#2008), so
    // a create/edit in any window (chat, another window, this one) updates this
    // panel in place. Reading `store.items` in `body` registers the @Observable
    // dependency. The form actions also route through the store, keeping this
    // inspector surface on the same observable update path.
    private var interpretations: [Components.Schemas.Interpretation] { store.items }
    private var isLoading: Bool { store.isLoading }
    private var frameworks: [Components.Schemas.InterpretiveFramework] { store.frameworks }

    @State private var isExpanded = false

    // Create form
    @State private var showingCreateForm = false
    @State private var selectedFrameworkId: String = ""
    @State private var selectedAct: Components.Schemas.InterpretiveActType = .reading
    @State private var newInterpretationText: String = ""
    @State private var newConfidence: Double = 0.8
    @State private var isSubmitting = false
    @State private var submitError: String?

    // Edit form (one row expanded at a time)
    @State private var editingInterpId: String?
    @State private var editText: String = ""
    @State private var editConfidence: Double = 0.8
    @State private var isSavingEdit = false
    @State private var editError: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header row — always visible
            HStack(spacing: 6) {
                if isLoading {
                    ProgressView().scaleEffect(0.55)
                } else {
                    Image(systemName: "text.magnifyingglass")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Text(interpretations.isEmpty
                     ? "Interpretations"
                     : "Interpretations (\(interpretations.count))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Button {
                    withAnimation(.easeInOut(duration: 0.12)) {
                        showingCreateForm.toggle()
                        if showingCreateForm && frameworks.isEmpty {
                            Task { await loadFrameworks() }
                        }
                    }
                } label: {
                    Image(systemName: showingCreateForm ? "xmark.circle" : "plus.circle")
                        .font(.caption)
                        .foregroundStyle(Color.accentColor)
                }
                .buttonStyle(.borderless)
                .help(showingCreateForm ? "Cancel" : "Add interpretation")
                if !interpretations.isEmpty {
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.caption2).foregroundStyle(.tertiary)
                        .onTapGesture { withAnimation { isExpanded.toggle() } }
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .contentShape(Rectangle())
            .onTapGesture {
                if !interpretations.isEmpty {
                    withAnimation { isExpanded.toggle() }
                }
            }

            // Interpretation list (collapsed by default until loaded)
            if isExpanded && !isLoading {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(interpretations, id: \.id) { interp in
                        interpretationRow(interp)
                    }
                }
                .padding(.horizontal, 12)
                .padding(.bottom, 6)
            }

            // Inline create form
            if showingCreateForm {
                createForm
                    .padding(.horizontal, 12)
                    .padding(.bottom, 8)
            }
        }
        .task(id: documentId) {
            await store.setScope(documentId: documentId)
            if !interpretations.isEmpty { isExpanded = true }
        }
    }

    // MARK: - Create form

    @ViewBuilder
    private var createForm: some View {
        VStack(alignment: .leading, spacing: 8) {
            Divider()

            // Framework picker — required for the backend
            if store.isLoadingFrameworks {
                HStack(spacing: 6) {
                    ProgressView().scaleEffect(0.55)
                    Text("Loading frameworks…").font(.caption2).foregroundStyle(.secondary)
                }
            } else if let frameworksError = store.frameworksError {
                Text(frameworksError).font(.caption2).foregroundStyle(.red)
            } else if frameworks.isEmpty {
                Text("No frameworks available.").font(.caption2).foregroundStyle(.secondary)
            } else {
                Picker("Framework", selection: $selectedFrameworkId) {
                    ForEach(frameworks, id: \.id) { framework in
                        Text(framework.name).tag(framework.id ?? "")
                    }
                }
                .pickerStyle(.menu)
                .font(.caption)
                .labelsHidden()
            }

            // Act picker
            Picker("Act", selection: $selectedAct) {
                ForEach(Components.Schemas.InterpretiveActType.allCases, id: \.self) { act in
                    Text(actLabel(act)).tag(act)
                }
            }
            .pickerStyle(.menu)
            .font(.caption)
            .labelsHidden()

            // Interpretation text
            TextEditor(text: $newInterpretationText)
                .editorScaledFont(.caption)
                .frame(minHeight: 60)
                .padding(4)
                .background(Color(.textBackgroundColor))
                .cornerRadius(4)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color(.separatorColor), lineWidth: 0.5)
                )
                .overlay(alignment: .topLeading) {
                    if newInterpretationText.isEmpty {
                        Text("Interpretation text…")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                            .padding(.horizontal, 8)
                            .padding(.top, 8)
                            .allowsHitTesting(false)
                    }
                }

            // Confidence slider
            VStack(alignment: .leading, spacing: 2) {
                HStack {
                    Text("Confidence").font(.caption2).foregroundStyle(.secondary)
                    Spacer()
                    Text(String(format: "%.0f%%", newConfidence * 100))
                        .font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                }
                Slider(value: $newConfidence, in: 0...1, step: 0.05)
            }

            if let err = submitError {
                Text(err).font(.caption2).foregroundStyle(.red)
            }

            HStack {
                Spacer()
                Button("Cancel") {
                    withAnimation { showingCreateForm = false }
                    resetForm()
                }
                .buttonStyle(.bordered)
                .controlSize(.small)

                Button("Save") {
                    Task { await submitInterpretation() }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(
                    newInterpretationText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    || selectedFrameworkId.isEmpty
                    || isSubmitting
                )
            }
        }
        .font(.caption)
    }

    // MARK: - Rows

    @ViewBuilder
    // swiftlint:disable:next function_body_length
    private func interpretationRow(_ interp: Components.Schemas.Interpretation) -> some View {
        let isEditing = editingInterpId == interp.id
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 4) {
                Text(actLabel(interp.act))
                    .font(.caption2)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.accentColor.opacity(0.12))
                    .foregroundStyle(Color.accentColor)
                    .clipShape(Capsule())
                Spacer()
                if let conf = interp.confidence {
                    Text(String(format: "%.0f%%", conf * 100))
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.tertiary)
                }
                Button {
                    if isEditing {
                        editingInterpId = nil
                        editError = nil
                    } else {
                        editText = interp.interpretationText
                        editConfidence = interp.confidence ?? 0.8
                        editingInterpId = interp.id
                        editError = nil
                    }
                } label: {
                    Image(systemName: isEditing ? "xmark.circle" : "pencil.circle")
                        .font(.caption)
                        .foregroundStyle(isEditing ? Color.secondary : Color.accentColor)
                }
                .buttonStyle(.borderless)
                .help(isEditing ? "Cancel edit" : "Edit interpretation")
            }
            if isEditing {
                editForm(for: interp)
            } else {
                Text(interp.interpretationText)
                    .font(.caption)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
                if let insights = interp.keyInsights, !insights.isEmpty {
                    VStack(alignment: .leading, spacing: 1) {
                        ForEach(insights.prefix(2), id: \.self) { insight in
                            HStack(alignment: .top, spacing: 4) {
                                Text("•").font(.caption2).foregroundStyle(.secondary)
                                Text(insight).font(.caption2).foregroundStyle(.secondary).lineLimit(2)
                            }
                        }
                    }
                }
            }
        }
        .padding(.vertical, 2)
    }

    @ViewBuilder
    private func editForm(for interp: Components.Schemas.Interpretation) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            TextEditor(text: $editText)
                .editorScaledFont(.caption)
                .frame(minHeight: 56)
                .padding(4)
                .background(Color(.textBackgroundColor))
                .cornerRadius(4)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color(.separatorColor), lineWidth: 0.5)
                )
            VStack(alignment: .leading, spacing: 2) {
                HStack {
                    Text("Confidence").font(.caption2).foregroundStyle(.secondary)
                    Spacer()
                    Text(String(format: "%.0f%%", editConfidence * 100))
                        .font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                }
                Slider(value: $editConfidence, in: 0...1, step: 0.05)
            }
            if let err = editError {
                Text(err).font(.caption2).foregroundStyle(.red)
            }
            HStack {
                Spacer()
                Button("Cancel") {
                    editingInterpId = nil
                    editError = nil
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                Button("Save") {
                    Task { await saveEdit(for: interp) }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(editText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSavingEdit)
            }
        }
        .font(.caption)
        .padding(.top, 4)
    }

    private func actLabel(_ act: Components.Schemas.InterpretiveActType) -> String {
        switch act {
        case .reading: return "Reading"
        case .translating: return "Translating"
        case .contextualizing: return "Contextualizing"
        case .synthesizing: return "Synthesizing"
        case .critiquing: return "Critiquing"
        case .applying: return "Applying"
        }
    }

    // MARK: - Load / Submit

    private func loadFrameworks() async {
        await store.loadFrameworks()
        if let first = store.frameworks.first, let fwId = first.id {
            selectedFrameworkId = fwId
        }
    }

    private func submitInterpretation() async {
        let text = newInterpretationText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !selectedFrameworkId.isEmpty else { return }
        isSubmitting = true
        submitError = nil
        defer { isSubmitting = false }
        do {
            try await store.create(
                frameworkId: selectedFrameworkId,
                documentId: documentId,
                act: selectedAct,
                text: text,
                confidence: newConfidence
            )
            isExpanded = true
            withAnimation { showingCreateForm = false }
            resetForm()
        } catch {
            submitError = error.localizedDescription
        }
    }

    private func saveEdit(for interp: Components.Schemas.Interpretation) async {
        let text = editText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, let interpId = interp.id else { return }
        isSavingEdit = true
        editError = nil
        defer { isSavingEdit = false }
        do {
            try await store.update(
                interpretationId: interpId,
                text: text,
                confidence: editConfidence
            )
            editingInterpId = nil
        } catch {
            editError = error.localizedDescription
        }
    }

    private func resetForm() {
        newInterpretationText = ""
        selectedAct = .reading
        newConfidence = 0.8
        submitError = nil
    }
}
