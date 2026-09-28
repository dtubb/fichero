import SwiftUI

/// The Inspector at the selection's LEVEL (ruled 2026-09-27, `build-notes-inspector.md`): a path head
/// -- Page › block › line › word, where clicking a crumb inspects that level -- then the same sections
/// at every level, a section with nothing to say hidden. Slice 1 has two: Text and Order.
///
/// The Inspector never types a reading or draws a shape; its verbs act on the selection (ruled).
/// It has no selection of its own: it shows the focused pane's.
struct SegmentInspectorView: View {
    let documentId: String
    /// The focused pane's selection, as segment ids, in the order picked.
    let selectedIds: [String]

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(\.undoManager) private var undoManager
    @State private var level: Level = .selection
    @State private var text: InspectorText?
    @State private var language: [InspectorLanguage.Row] = []
    /// The Segment menu's Language… / Script… prompt (#5157).
    @State private var askingFor: SegmentAttributeMenu.CodeKind?
    @State private var code = ""

    /// What the sections describe: the selection itself, a crumb the person clicked, or the page.
    enum Level: Equatable {
        case selection
        case segment(String)
        case page
    }

    private var segments: [Segment] {
        segmentService.map { SegmentStore.shared(for: $0).segments(documentId: documentId) } ?? []
    }

    private var path: InspectorPath? {
        selectedIds.count == 1
            ? InspectorPath.to(selectedIds[0], in: segments)
            : InspectorPath.common(selectedIds, in: segments)
    }

    /// The inspected segment; nil is the page. A mixed selection is inspected at its common parent.
    private var inspected: String? {
        switch level {
        case .page: nil
        case .segment(let id): id
        case .selection: selectedIds.count == 1 ? selectedIds.first : path?.crumbs.last?.segmentId
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            pathHead
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if selectedIds.count > 1, level == .selection {
                        Text(countsLine).font(.caption).foregroundStyle(.secondary)
                    }
                    if let text, !text.readings.isEmpty {
                        InspectorTextSection(text: text) { reading in choose(reading, in: text) }
                    }
                    if !language.isEmpty {
                        InspectorLanguageSection(rows: language)
                    }
                    if let inspected {
                        // Who wrote the ink, and who judged so (#5161).
                        InspectorHandsSection(segmentId: inspected)
                        // What the editor knows about the state of the text (5.5).
                        InspectorEditorialSection(
                            segmentId: inspected, reading: text?.countingReading(ofKind: "transcription")
                        )
                        // Declared signs, and a character's letterform (5.6).
                        InspectorSignsSection(
                            segmentId: inspected, reading: text?.countingContent(ofKind: "transcription")
                        )
                        // Typed links, both ways, and the segment's reference (5.7).
                        InspectorLinksSection(segmentId: inspected, documentId: documentId, selectedIds: selectedIds)
                        // What is said about it: claims and mentions whose anchor names it (5.7).
                        InspectorStatementsSection(segmentId: inspected, documentId: documentId)
                        // What applies here, from the library down (5.8).
                        InspectorRightsSection(targetKind: "segment", targetId: inspected, pageId: documentId)
                        // Its picture, baseline and own history, with Restore (#5163).
                        InspectorSegmentMakingSection(segmentId: inspected, documentId: documentId)
                    }
                    if level == .page {
                        // Page level: how the page's passes were made (#5149).
                        InspectorMakingSection(documentId: documentId)
                        InspectorRightsSection(targetKind: "document", targetId: documentId, pageId: documentId)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(8)
            }
            // The Order section: the inspected segment's children, rearrangeable with the same verbs
            // as everywhere else (one `ReadingOrderStore`); hidden when it has none.
            ReadingOrderList(documentId: documentId, parentSegmentId: inspected, hidesWhenEmpty: true)
                .frame(maxHeight: 260)
        }
        .task(id: inspected) {
            text = nil
            await reloadText()
        }
        .onChange(of: selectedIds) { level = .selection }
        .alert(askingFor == .script ? "Script" : "Language", isPresented: Binding(
            get: { askingFor != nil }, set: { if !$0 { askingFor = nil } }
        )) {
            TextField(askingFor == .script ? "ISO 15924, e.g. Syrc" : "BCP 47, e.g. syc", text: $code)
            Button("Set") {
                let value = code.trimmingCharacters(in: .whitespaces)
                if !value.isEmpty { setAttribute(askingFor == .script ? .script(value) : .language(value)) }
                askingFor = nil
            }
            Button("Cancel", role: .cancel) { askingFor = nil }
        } message: {
            Text("Set on the \(selectedIds.count == 1 ? "selected segment" : "\(selectedIds.count) selected segments").")
        }
    }

    /// The Segment menu's verb (#5157): one audited `segment.update_many` over the selection, ⌘Z.
    private func setAttribute(_ attribute: SegmentEdit.Attribute) {
        guard let segmentService, let actionsService = actionStore?.actionsService else { return }
        let store = SegmentStore.shared(for: segmentService)
        let byId = Dictionary(
            store.segments(documentId: documentId).map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first }
        )
        guard case .success(let call) = SegmentEdit.set(attribute, on: selectedIds.compactMap { byId[$0] }) else { return }
        let runner = SegmentEditRunner(actionsService: actionsService, store: store)
        let undoManager = undoManager
        Task {
            try? await runner.run(call, documentId: documentId, actionName: "Set Segment", undoManager: undoManager)
        }
    }

    private func reloadText() async {
        language = []
        guard let inspected, let segmentService else { return }
        text = try? await segmentService.readings(segmentId: inspected)
        let settings = (try? await segmentService.resolvedSettings(segmentId: inspected)) ?? []
        language = InspectorLanguage.rows(settings)
    }

    /// "Make This Count" (#5153): the audited `reading.choose`, ⌘Z by its own audit id.
    private func choose(_ reading: InspectorText.Reading, in text: InspectorText) {
        guard let inspected, let params = ReadingChoice.choose(reading, of: inspected, in: text),
              let actionsService = actionStore?.actionsService else { return }
        let undoManager = undoManager
        Task {
            try? await ReadingChoice.run(
                params, actionsService: actionsService, undoManager: undoManager,
                afterChange: { await reloadText() }
            )
        }
    }

    private var pathHead: some View {
        HStack(spacing: 4) {
            crumb("Page", selected: inspected == nil) { level = .page }
            ForEach(path?.crumbs ?? []) { crumb in
                Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.tertiary)
                self.crumb(crumb.label, selected: inspected == crumb.segmentId) { level = .segment(crumb.segmentId) }
            }
            Spacer(minLength: 0)
            // Verbs on the SELECTION (ruled: the Inspector offers verbs, never typing a reading).
            SegmentAttributeMenu(apply: { setAttribute($0) }, askForCode: { askingFor = $0; code = "" })
                .menuStyle(.button)
                .buttonStyle(.borderless)
                .fixedSize()
                .font(.caption)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Path")
    }

    private func crumb(_ title: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(title, action: action)
            .buttonStyle(.borderless)
            .font(selected ? .caption.weight(.semibold) : .caption)
            .foregroundStyle(selected ? .primary : .secondary)
    }

    private var countsLine: String {
        InspectorPath.kindCounts(selectedIds, in: segments)
            .map { "\($0.count) \($0.count == 1 ? $0.kind : $0.kind + "s")" }
            .joined(separator: ", ")
    }
}

/// Language, script, direction and encoding for the inspected segment, each saying where it came from
/// (#5158). A fallback says it is one.
struct InspectorLanguageSection: View {
    let rows: [InspectorLanguage.Row]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Language & Script").font(.headline)
            ForEach(rows) { row in
                VStack(alignment: .leading, spacing: 1) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(row.title).font(.subheadline).foregroundStyle(.secondary)
                        Spacer(minLength: 8)
                        Text(row.value).font(.body).textSelection(.enabled)
                    }
                    Text(row.origin).font(.caption).foregroundStyle(.secondary)
                        .help(row.basis)
                }
                .accessibilityElement(children: .combine)
            }
        }
    }
}

/// Every live reading, grouped by kind; the one that counts is marked with WHY it counts.
struct InspectorTextSection: View {
    let text: InspectorText
    /// "Make This Count" on a reading that does not count; nil shows no verb (a preview, a reader).
    var onChoose: ((InspectorText.Reading) -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Text").font(.headline)
            ForEach(text.kinds, id: \.self) { kind in
                VStack(alignment: .leading, spacing: 6) {
                    Text(kind.capitalized).font(.subheadline).foregroundStyle(.secondary)
                    ForEach(text.readings(ofKind: kind)) { reading in
                        row(reading)
                    }
                    if let counting = text.counting[kind], counting.readingId == nil {
                        Text(counting.why.label).font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    private func row(_ reading: InspectorText.Reading) -> some View {
        let counts = text.counts(reading)
        return VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Image(systemName: counts ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(counts ? Color.accentColor : .secondary)
                    .accessibilityLabel(counts ? "Counts" : "Does not count")
                if let role = reading.pairRole {
                    Text(role).font(.caption.monospaced()).foregroundStyle(.secondary)
                }
                Text(reading.content).font(.body).textSelection(.enabled)
            }
            HStack(spacing: 8) {
                Text(detail(reading, counts: counts)).font(.caption).foregroundStyle(.secondary)
                if !counts, let onChoose {
                    Button("Make This Count") { onChoose(reading) }
                        .buttonStyle(.borderless)
                        .font(.caption)
                        .help("Choose this reading as the one that counts for \(reading.kind)")
                }
            }
        }
    }

    /// Who made it, who wrote it down, the guideline, and -- for the one that counts -- why.
    private func detail(_ reading: InspectorText.Reading, counts: Bool) -> String {
        var parts = [reading.maker.capitalized]
        if let author = reading.author { parts.append(author) }
        if let guideline = reading.guideline { parts.append(guideline) }
        if let level = reading.level { parts.append("level \(level)") }
        if let confidence = reading.machineConfidence { parts.append("confidence \(Int((confidence * 100).rounded()))%") }
        if reading.correctsId != nil { parts.append("a correction") }
        if reading.readFromRenditionId != nil { parts.append("read from another image") }
        if counts, let why = text.counting[reading.kind]?.why { parts.append(why.label) }
        return parts.joined(separator: " · ")
    }
}

#if DEBUG
#Preview("Text: a machine reading, a person's correction that counts, a sic / corr pair") {
    let reading = { (id: String, content: String, maker: String, pair: String?, role: String?) in
        InspectorText.Reading(
            id: id, kind: "transcription", content: content, maker: maker, author: maker == "human" ? "dtubb" : nil,
            guideline: "diplomatic", pairId: pair, pairRole: role
        )
    }
    InspectorTextSection(text: InspectorText(
        readings: [
            reading("r1", "Tlie qnick brown fox", "workflow", nil, nil),
            reading("r2", "The quick brown fox", "human", nil, nil),
            reading("r3", "recieve", "human", "p1", "sic"),
            reading("r4", "receive", "human", "p1", "corr")
        ],
        counting: ["transcription": .init(readingId: "r2", why: .chosen)]
    ))
    .padding()
    .frame(width: 320)
}
#endif
