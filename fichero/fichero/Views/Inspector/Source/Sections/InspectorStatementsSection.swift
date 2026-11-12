import SwiftUI

/// The Inspector's statements (5.7, second half): the claims and mentions whose anchor names this
/// segment, each opening its claim or entity in the knowledge views (the one focus the Reader and the
/// Knowledge inspector already follow), and each corrected in place (`source.extract.corrected-in-place`,
/// #5602): a mention re-pointed to another entity or its words fixed on the line, a statement dated or
/// rejected. After any correction the section re-reads this one segment's statements. Hidden when nothing
/// is said about the segment.
struct InspectorStatementsSection: View {
    let segmentId: String
    let documentId: String
    /// The line's text, where "Fix the words" selects the corrected span. Nil hides that correction.
    var lineText: String?

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(KGFocusState.self) private var kgFocusState: KGFocusState?
    @State private var answer = InspectorStatements.Answer()
    /// The one correction open, by row id.
    @State private var editing: Correction?
    @State private var failure: String?

    /// One correction, sent through the statements service.
    typealias Correct = @MainActor @Sendable (StatementService) async throws -> Void
    /// How a row hands its correction up to be sent.
    typealias Send = (@escaping Correct) -> Void

    enum Correction: Equatable {
        case repoint(rowId: String)
        case respan(rowId: String)
        case date(rowId: String)

        var rowId: String {
            switch self {
            case .repoint(let id), .respan(let id), .date(let id): id
            }
        }
    }

    var body: some View {
        // The container always exists, so the load runs while the section has nothing to show.
        VStack(alignment: .leading, spacing: 0) {
            let rows = InspectorStatements.rows(answer)
            if !rows.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Said About This").font(.headline)
                    ForEach(rows) { row in
                        StatementRowView(
                            row: row, documentId: documentId, lineText: lineText,
                            editing: editing?.rowId == row.id ? editing : nil,
                            onOpen: { open(row) },
                            onBegin: { editing = $0; failure = nil },
                            onCancel: { editing = nil },
                            onCorrect: { correct in Task { await apply(correct) } }
                        )
                    }
                    if let failure {
                        Text(failure).font(.caption).foregroundStyle(.red)
                    }
                }
            }
        }
        .task(id: segmentId) { editing = nil; failure = nil; await reload() }
    }

    private func open(_ row: InspectorStatements.Row) {
        guard let kgFocusState else { return }
        if row.isClaim {
            kgFocusState.focusClaim(claimId: row.targetId, entityId: nil, sourceDocumentId: documentId)
        } else {
            kgFocusState.focusEntity(entityId: row.targetId, sourceDocumentId: documentId)
        }
    }

    /// Sends one correction, then re-reads this segment's statements in place.
    private func apply(_ correct: Correct) async {
        guard let segmentService else { return }
        do {
            try await correct(StatementService(client: segmentService.client))
            editing = nil
            failure = nil
        } catch {
            failure = error.localizedDescription
        }
        await reload()
    }

    private func reload() async {
        guard let segmentService else { return }
        answer = (try? await StatementService(client: segmentService.client).statements(segmentId: segmentId))
            ?? InspectorStatements.Answer()
    }
}

/// One statement or mention: opens it, offers its corrections, and holds the one correction open on it.
private struct StatementRowView: View {
    let row: InspectorStatements.Row
    let documentId: String
    let lineText: String?
    let editing: InspectorStatementsSection.Correction?
    let onOpen: () -> Void
    let onBegin: (InspectorStatementsSection.Correction) -> Void
    let onCancel: () -> Void
    let onCorrect: InspectorStatementsSection.Send

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Button(action: onOpen) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(row.title).font(.body).multilineTextAlignment(.leading)
                        Text(row.detail).font(.caption).foregroundStyle(.secondary)
                        if row.corrected {
                            Label("corrected by you", systemImage: "person.fill.checkmark")
                                .font(.caption2).foregroundStyle(.secondary)
                                .accessibilityLabel("Corrected by you")
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
                .help(row.isClaim ? "Open this claim" : "Open this entity")
                .accessibilityHint(row.isClaim ? "Opens the claim" : "Opens the entity")
                correctionsMenu
            }
            if let editing {
                editor(for: editing)
            }
        }
    }

    private var correctionsMenu: some View {
        Menu {
            if row.isClaim {
                Button("Change Date…") { onBegin(.date(rowId: row.id)) }
                Button("Not True (Reject)") {
                    let claimId = row.targetId
                    onCorrect { try await $0.reject(claimId: claimId) }
                }
            } else if let mention = row.mention, mention.pageSpan != nil {
                Button("Not This Person… (Choose Another)") { onBegin(.repoint(rowId: row.id)) }
                if let lineText, InspectorStatements.lineTextMatches(mention, lineText: lineText) {
                    Button("Fix the Words…") { onBegin(.respan(rowId: row.id)) }
                }
            }
        } label: {
            Image(systemName: "ellipsis.circle")
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .disabled(!row.isClaim && row.mention?.pageSpan == nil)
        .help(row.isClaim ? "Correct this statement" : "Correct this name")
        .accessibilityLabel(row.isClaim ? "Correct this statement" : "Correct this name")
    }

    @ViewBuilder
    private func editor(for correction: InspectorStatementsSection.Correction) -> some View {
        let documentId = documentId
        switch correction {
        case .date:
            StatementDateEditor(onCancel: onCancel) { date in
                let claimId = row.targetId
                onCorrect { try await $0.setDate(claimId: claimId, date: date) }
            }
        case .repoint:
            if let mention = row.mention {
                MentionRepointEditor(mention: mention, onCancel: onCancel) { entityId in
                    onCorrect { try await $0.repoint(mention, documentId: documentId, toEntityId: entityId) }
                }
            }
        case .respan:
            if let mention = row.mention, let lineText {
                MentionRespanEditor(mention: mention, lineText: lineText, onCancel: onCancel) { span in
                    onCorrect {
                        try await $0.respan(mention, documentId: documentId, newStart: span.start, newEnd: span.end)
                    }
                }
            }
        }
    }
}

#if DEBUG
#Preview("Said about this: a claim, a name, and a name a person corrected") {
    let rows = InspectorStatements.rows(.init(
        claims: [.init(id: "c1", text: "Abraham begat Isaac", curationState: "unreviewed", confidence: 0.5,
                       via: "anchor", excerpt: "ܐܒܪܗܡ ܐܘܠܕ")],
        mentions: [
            .init(id: "e1", name: "Abraham", entityType: "person", excerpt: "ܐܒܪܗܡ",
                  sourceCharStart: 10, sourceCharEnd: 15, charStart: 0, charEnd: 5),
            .init(id: "e2", name: "Isaac", entityType: "person", excerpt: "ܐܝܣܚܩ",
                  sourceCharStart: 22, sourceCharEnd: 27, charStart: 12, charEnd: 17, correctedByPerson: true)
        ]
    ))
    VStack(alignment: .leading, spacing: 6) {
        Text("Said About This").font(.headline)
        ForEach(rows) { row in
            StatementRowView(
                row: row, documentId: "doc-1", lineText: "ܐܒܪܗܡ ܐܘܠܕ ܠܐܝܣܚܩ",
                editing: row.isClaim ? .date(rowId: row.id) : nil,
                onOpen: {}, onBegin: { _ in }, onCancel: {}, onCorrect: { _ in }
            )
        }
    }
    .padding()
    .frame(width: 340)
}
#endif
