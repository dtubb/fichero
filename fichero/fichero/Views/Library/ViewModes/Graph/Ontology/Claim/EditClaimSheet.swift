import FicheroAPIClient
import SwiftUI

/// Sheet for editing the text, type, and epistemic status of a claim (#1135).
/// Calls PATCH /api/claims/{id} on save.
struct EditClaimSheet: View {
    let claim: Components.Schemas.KnowledgeClaim
    let onSave: (Components.Schemas.KnowledgeClaim) -> Void

    @Environment(\.dismiss) private var dismiss
    // #4833 slice C: was `LibraryManager.shared.getLibrary(id: windowState.libraryId)`
    // — the same global-library-reaching pattern `ClaimReviewQueueSheet` was
    // fixed away from (`testReviewQueueDoesNotReachForTheGlobalLibrary`).
    // The per-window store sidesteps it and IS the audited save path.
    // Optional for the same reason `InlineClaimEditor`'s is: a non-optional
    // read here would trap in a host without one injected.
    @Environment(ClaimStore.self) private var claimStore: ClaimStore?
    @State private var text: String
    @State private var subject: String
    @State private var predicate: String
    @State private var object: String
    @State private var sourcePageLabel: String
    @State private var claimType: String
    @State private var epistemicStatus: String
    @State private var isSaving = false
    @State private var errorText: String?

    static let claimTypeOptions: [(label: String, raw: String)] = [
        ("Fact", "fact"),
        ("Claim", "claim"),
        ("Quotation", "quotation"),
        ("Hypothesis", "hypothesis"),
        ("Definition", "definition"),
        ("Judgment", "judgment"),
        ("Method", "method")
    ]

    static let epistemicStatusOptions: [(label: String, raw: String)] = [
        ("Confirmed", "confirmed"),
        ("Tentative", "tentative"),
        ("Rejected", "rejected")
    ]

    init(
        claim: Components.Schemas.KnowledgeClaim,
        onSave: @escaping (Components.Schemas.KnowledgeClaim) -> Void
    ) {
        self.claim = claim
        self.onSave = onSave
        _text = State(initialValue: claim.text)
        _subject = State(initialValue: claim.subjectCanonical ?? "")
        _predicate = State(initialValue: claim.predicateVerb ?? "")
        _object = State(initialValue: claim.objectPhrase ?? "")
        _sourcePageLabel = State(initialValue: claim.sourcePageLabel ?? "")
        _claimType = State(initialValue: claim.claimType?.rawValue ?? "claim")
        _epistemicStatus = State(initialValue: claim.epistemicStatus?.rawValue ?? "tentative")
    }

    var body: some View {
        VStack(spacing: 0) {
            Form {
                Section("Claim Text") {
                    TextEditor(text: $text)
                        .editorScaledFont()
                        .frame(minHeight: 80)
                }

                Section("Subject-Verb-Object") {
                    TextField("Subject", text: $subject)
                    TextField("Predicate", text: $predicate)
                    TextField("Object", text: $object)
                    TextField("Source page", text: $sourcePageLabel)
                }

                Section("Review") {
                    Picker("Kind", selection: $claimType) {
                        ForEach(Self.claimTypeOptions, id: \.raw) { item in
                            Text(item.label).tag(item.raw)
                        }
                    }
                    Picker("Epistemic Status", selection: $epistemicStatus) {
                        ForEach(Self.epistemicStatusOptions, id: \.raw) { item in
                            Text(item.label).tag(item.raw)
                        }
                    }
                }

                if let errorText {
                    Section {
                        Text(errorText)
                            .foregroundStyle(.red)
                            .font(.caption)
                    }
                }
            }
            .formStyle(.grouped)

            Divider()

            HStack {
                Button("Cancel") { dismiss() }
                    .keyboardShortcut(.cancelAction)
                Spacer()
                Button("Save", action: save)
                    .keyboardShortcut(.defaultAction)
                    .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSaving)
            }
            .padding()
        }
        .frame(width: 520, height: 520)
    }

    private func save() {
        guard let claimId = claim.id else { return }
        guard let claimStore else {
            errorText = "No claim store available in this window."
            return
        }
        isSaving = true
        errorText = nil
        Task {
            do {
                // #4833: PATCH /api/claims/{id} via the store — the audited
                // claim.patch action, splicing one row, same as
                // InlineClaimEditor's fix. `onSave` gets the RETURNED claim,
                // never the stale one this sheet was opened with.
                let updated = try await claimStore.patch(
                    claimId: claimId,
                    text: text.trimmingCharacters(in: .whitespacesAndNewlines),
                    subjectCanonical: trimmedOrNil(subject),
                    predicateVerb: trimmedOrNil(predicate),
                    objectPhrase: trimmedOrNil(object),
                    sourcePageLabel: trimmedOrNil(sourcePageLabel),
                    claimType: Components.Schemas.ClaimType(rawValue: claimType),
                    epistemicStatus: Components.Schemas.EpistemicStatus(rawValue: epistemicStatus)
                )
                onSave(updated)
                dismiss()
            } catch {
                errorText = error.localizedDescription
                isSaving = false
            }
        }
    }

    private func trimmedOrNil(_ value: String) -> String? {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}

struct InlineClaimEditor: View {
    let claim: Components.Schemas.KnowledgeClaim
    let onCancel: () -> Void
    let onSave: (Components.Schemas.KnowledgeClaim) -> Void

    // #4833: saves route through the store, not a second action call — see
    // `save()`. Optional: this editor mounts under EntityDigestView, which
    // deliberately reads ClaimStore as optional itself ("missing @Environment
    // of a non-optional traps, #4513") because it can render in a host with
    // no store injected — a non-optional read here would trap in exactly
    // that host.
    @Environment(ClaimStore.self) private var claimStore: ClaimStore?
    // #4833: subject is an ENTITY PICKER, never free text — `subjectEntityId`
    // is the only thing this editor can send for the subject. `subjectName`
    // is DISPLAY ONLY (what the picker button shows); it is never sent.
    @State private var subjectEntityId: String?
    @State private var subjectName: String
    @State private var predicate: String
    @State private var object: String
    @State private var sourcePageLabel: String
    @State private var claimType: String
    @State private var epistemicStatus: String
    // #4833: the wire fields already exist (KnowledgeClaim/ClaimPatchRequest
    // `time_start`/`time_end`/`time_precision`) — this editor just never read
    // or wrote them.
    @State private var timeStart: String
    @State private var timeEnd: String
    @State private var timePrecision: String
    @State private var isSaving = false
    @State private var errorText: String?

    init(
        claim: Components.Schemas.KnowledgeClaim,
        onCancel: @escaping () -> Void,
        onSave: @escaping (Components.Schemas.KnowledgeClaim) -> Void
    ) {
        self.claim = claim
        self.onCancel = onCancel
        self.onSave = onSave
        _subjectEntityId = State(initialValue: claim.subjectEntityId)
        _subjectName = State(initialValue: claim.subjectCanonical ?? "")
        _predicate = State(initialValue: claim.predicateVerb ?? "")
        _object = State(initialValue: claim.objectPhrase ?? "")
        _sourcePageLabel = State(initialValue: claim.sourcePageLabel ?? "")
        _claimType = State(initialValue: claim.claimType?.rawValue ?? "claim")
        _epistemicStatus = State(initialValue: claim.epistemicStatus?.rawValue ?? "tentative")
        _timeStart = State(initialValue: claim.timeStart ?? "")
        _timeEnd = State(initialValue: claim.timeEnd ?? "")
        _timePrecision = State(initialValue: claim.timePrecision ?? "")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                ClaimSubjectEntityPicker(subjectEntityId: $subjectEntityId, subjectName: $subjectName)
                TextField("Predicate", text: $predicate)
                TextField("Object", text: $object)
            }
            HStack(spacing: 6) {
                Picker("Kind", selection: $claimType) {
                    ForEach(EditClaimSheet.claimTypeOptions, id: \.raw) { item in
                        Text(item.label).tag(item.raw)
                    }
                }
                Picker("Status", selection: $epistemicStatus) {
                    ForEach(EditClaimSheet.epistemicStatusOptions, id: \.raw) { item in
                        Text(item.label).tag(item.raw)
                    }
                }
                TextField("Page", text: $sourcePageLabel)
                    .frame(width: 80)
            }
            HStack(spacing: 6) {
                TextField("Start (YYYY-MM-DD)", text: $timeStart)
                TextField("End (YYYY-MM-DD)", text: $timeEnd)
                TextField("Precision", text: $timePrecision)
                    .frame(width: 100)
            }
            if let errorText {
                Text(errorText)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
            HStack {
                Spacer()
                Button("Cancel", action: onCancel)
                Button("Save", action: save)
                    .buttonStyle(.borderedProminent)
                    .disabled(isSaving)
            }
        }
        .padding(10)
        .background(Color(.windowBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    private func save() {
        guard let claimId = claim.id else { return }
        guard let claimStore else {
            errorText = "No claim store available in this window."
            return
        }
        isSaving = true
        errorText = nil
        Task {
            do {
                // #4833: PATCH /api/claims/{id} IS the audited claim.patch
                // action (ClaimStore.patch calls entityService.patchClaim,
                // the SAME endpoint the direct actionsService call used) —
                // going through the store is what makes this splice one row
                // instead of a second, un-observed save path. It returns the
                // server's freshly-patched claim, which `onSave` gets —
                // never the stale `claim` this editor was opened with.
                let updated = try await claimStore.patch(
                    claimId: claimId,
                    // #4833: subject_entity_id only, never a name made up on
                    // the client — engine commit 69fba6090 updates entity_ids
                    // and regenerates the sentence's subject text server-side
                    // when none is sent. Sent only when it actually changed.
                    subjectEntityId: subjectEntityId != claim.subjectEntityId ? subjectEntityId : nil,
                    predicateVerb: trimmedOrNil(predicate),
                    objectPhrase: trimmedOrNil(object),
                    sourcePageLabel: trimmedOrNil(sourcePageLabel),
                    claimType: Components.Schemas.ClaimType(rawValue: claimType),
                    epistemicStatus: Components.Schemas.EpistemicStatus(rawValue: epistemicStatus),
                    timeStart: trimmedOrNil(timeStart),
                    timeEnd: trimmedOrNil(timeEnd),
                    timePrecision: trimmedOrNil(timePrecision)
                )
                onSave(updated)
            } catch {
                errorText = error.localizedDescription
                isSaving = false
            }
        }
    }

    private func trimmedOrNil(_ value: String) -> String? {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}

/// Subject picker for `InlineClaimEditor` (#4833): the subject must be an
/// existing `KnowledgeEntity`, chosen by search, never typed prose — the
/// engine regenerates the sentence's subject text from whatever entity
/// `subjectEntityId` resolves to, so a client-typed name would either be
/// discarded or, worse, silently diverge from it. Search reuses
/// `EntityService.listEntities(query:)`, the same free-text-against-
/// canonical-name-and-aliases lookup other surfaces already call — no new
/// endpoint.
struct ClaimSubjectEntityPicker: View {
    @Binding var subjectEntityId: String?
    @Binding var subjectName: String

    @Environment(EntityService.self) private var entityService: EntityService?
    @State private var isExpanded = false
    @State private var query = ""
    @State private var results: [Components.Schemas.KnowledgeEntity] = []
    @State private var isSearching = false

    /// Non-optional-id pairing so the results list can `ForEach` by a stable
    /// identity — same shape as `KnowledgeGraphInspectorSection.IdentifiedClaim`.
    private struct IdentifiedEntity: Identifiable {
        let id: String
        let entity: Components.Schemas.KnowledgeEntity
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Button {
                isExpanded.toggle()
            } label: {
                Text(subjectName.isEmpty ? "Subject: pick an entity…" : subjectName)
            }
            .accessibilityLabel(
                subjectName.isEmpty ? "Subject, none picked" : "Subject, \(subjectName), change"
            )
            .accessibilityHint("Opens entity search")
            if isExpanded {
                TextField("Search entities", text: $query)
                    .textFieldStyle(.roundedBorder)
                    .onChange(of: query) { _, newValue in
                        Task { await search(newValue) }
                    }
                if isSearching {
                    ProgressView().controlSize(.small)
                } else if !results.isEmpty {
                    let pairs = results.compactMap { entity in
                        entity.id.map { IdentifiedEntity(id: $0, entity: entity) }
                    }
                    List(pairs) { pair in
                        Button(pair.entity.canonicalName) {
                            subjectEntityId = pair.id
                            subjectName = pair.entity.canonicalName
                            isExpanded = false
                            query = ""
                            results = []
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Set subject to \(pair.entity.canonicalName)")
                    }
                    .frame(maxHeight: 120)
                }
            }
        }
    }

    private func search(_ text: String) async {
        guard let entityService, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            results = []
            return
        }
        isSearching = true
        defer { isSearching = false }
        results = (try? await entityService.listEntities(query: text, limit: 10)) ?? []
    }
}
