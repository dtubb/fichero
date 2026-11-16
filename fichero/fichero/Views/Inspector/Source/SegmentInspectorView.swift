import SwiftUI

/// The Inspector at the selection's LEVEL (ruled 2026-09-27, `build-notes-inspector.md`): a path head
/// -- Page › block › line › word, where clicking a crumb inspects that level -- then the same sections
/// at every level, a section with nothing to say hidden. Slice 1 has two: Text and Order.
///
/// The Inspector draws no shape; its verbs act on the selection (ruled). It types a reading only as the
/// Reader does -- Type a Reading… for a segment with none, Edit… for the one that counts (#5201), both the
/// Reader's own `representation.create`. It has no selection of its own: it shows the focused pane's.
struct SegmentInspectorView: View {
    let documentId: String
    /// The focused pane's selection, as segment ids, in the order picked.
    let selectedIds: [String]
    /// The ids the Order section's own click or double-click selected: the Inspector holds (#5424).
    var onOrderSelected: (([String]) -> Void)?

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(WindowSteps.self) private var windowSteps: WindowSteps?
    @Environment(WindowState.self) private var windowState: WindowState?
    @State private var level: Level = .selection
    @State private var text: InspectorText?
    @State private var language: [InspectorLanguage.Row] = []
    /// The Segment menu's Language… / Script… prompt (#5157).
    @State private var askingFor: SegmentAttributeMenu.CodeKind?
    @State private var code = ""
    /// Edit… (#5201): the words being edited, with the reading they correct; nil when not editing.
    @State private var editing: (reading: InspectorText.Reading, words: String)?
    /// Why the last Edit… did not land.
    @State private var editNote: String?
    /// Why the last Delete did not happen (`source.editor.delete-selected-lines`); nil after one did.
    @State private var deleteNote: String?
    /// Why a multi-selection's language, script and direction are not shown (too many lines, or a read failed).
    @State private var multiNote: String?
    /// The inspected segment's resolved direction (the engine's cascade), which the editor lays out in.
    @State private var direction: String?
    /// The sections that hold nothing, hidden behind the head's Add menu (#6413), and those the person asked for.
    @State private var emptySections: Set<InspectorSegmentLayout.Addition> = []
    @State private var revealedSections: Set<InspectorSegmentLayout.Addition> = []

    /// What the sections describe: the selection itself, a crumb the person clicked, or the page.
    enum Level: Equatable {
        case selection
        case segment(String)
        case page
    }

    private var segments: [Segment] {
        segmentService.map { SegmentStore.shared(for: $0).segments(documentId: documentId) } ?? []
    }

    /// The teacher-line check's flags (#5446): the store every line list reads.
    private var flags: FlaggedLineStore? {
        segmentService.map { FlaggedLineStore.shared(for: $0) }
    }

    private var path: InspectorPath? {
        selectedIds.count == 1
            ? InspectorPath.to(selectedIds[0], in: segments)
            : InspectorPath.common(selectedIds, in: segments)
    }

    /// The inspected segment; nil is the page. A mixed selection is inspected at its common parent.
    /// Several lines selected and described as a selection: language, script and direction are theirs together
    /// (Mixed where they differ); the per-line sections wait for one line (`source.inspector.multi-selection`).
    private var isMulti: Bool { selectedIds.count > 1 && level == .selection }

    /// The most lines whose settings are compared at once.
    private static let multiCap = 200

    private var inspected: String? {
        switch level {
        case .page: nil
        case .segment(let id): id
        case .selection: selectedIds.count == 1 ? selectedIds.first : path?.crumbs.last?.segmentId
        }
    }

    /// The line's text a name's words are fixed on (#5602): its counted transcription, else its own text.
    private func lineText(of segmentId: String) -> String? {
        text?.countingContent(ofKind: "transcription") ?? segments.first { $0.id == segmentId }?.text
    }

    /// Up/Down step the shared selection through the page in reading order (#6457); Shift extends.
    /// A text field being edited keeps its arrows.
    private func step(_ places: Int, extend: Bool) -> KeyPress.Result {
        guard editing == nil, let segmentService, let focused = windowState?.sharedRegionSelection,
              InspectorPath.stepSelection(
                by: places, extend: extend, startsFromNothing: true, selection: focused,
                documentId: documentId, store: SegmentStore.shared(for: segmentService)
              ) else { return .ignored }
        return .handled
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            pathHead
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
            if let deleteNote {
                Text(deleteNote).font(.caption).foregroundStyle(.secondary).padding(.horizontal, 8)
            }
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if selectedIds.count > 1, level == .selection {
                        Text(countsLine).font(.caption).foregroundStyle(.secondary)
                    }
                    if isMulti {
                        InspectorBulkSection(selectedIds: selectedIds)
                        Text("Select one line to see its text, hands, certainty, rights and links.")
                            .font(.caption).foregroundStyle(.secondary)
                        if let multiNote {
                            Text(multiNote).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    if !isMulti, let inspected, let flags, let line = flags.flag(segmentId: inspected, documentId: documentId) {
                        // The teacher-line check flagged it (#5446): why, in words, and the person's Confirm.
                        InspectorFlaggedSection(
                            line: line, runWords: flags.runWords(line), note: flags.confirmNote,
                            confirm: { Task { await flags.confirm(segmentId: inspected, documentId: documentId) } }
                        )
                    }
                    if let inspected, !isMulti {
                        InspectorSegmentPicture(segmentId: inspected)
                    }
                    if hasReadingsGroup {
                        InspectorGroupBox(group: .readings) { readingsGroup }
                    }
                    if !isMulti, let inspected {
                        InspectorGroupBox(group: .details) {
                            if !language.isEmpty {
                                InspectorDetailsLine(rows: language)
                            }
                            // Who wrote the ink, and who judged so (#5161); hidden while none is named.
                            InspectorHandsSection(
                                segmentId: inspected, hidesWhenEmpty: hides(.hand), onEmpty: { noted(.hand, empty: $0) }
                            )
                            // What the editor knows about the state of the text (5.5); hidden while nothing is.
                            InspectorEditorialSection(
                                segmentId: inspected, reading: text?.countingReading(ofKind: "transcription"),
                                hidesWhenEmpty: hides(.certaintyMark), onEmpty: { noted(.certaintyMark, empty: $0) }
                            )
                            // Declared signs, and a character's letterform (5.6).
                            InspectorSignsSection(
                                segmentId: inspected, reading: text?.countingContent(ofKind: "transcription")
                            )
                        }
                        InspectorGroupBox(group: .history) {
                            // Its baseline and own history, with Restore (#5163); the picture is in the head.
                            InspectorSegmentMakingSection(segmentId: inspected, documentId: documentId, grouped: true)
                        }
                        InspectorGroupBox(group: .linksAndRights) {
                            // Typed links, both ways, and the segment's reference (5.7).
                            InspectorLinksSection(
                                segmentId: inspected, documentId: documentId, selectedIds: selectedIds, quietWhenEmpty: true
                            )
                            // What is said about it: claims and mentions whose anchor names it (5.7), each
                            // corrected in place (#5602); a name's words are fixed on the line's counted text.
                            InspectorStatementsSection(
                                segmentId: inspected, documentId: documentId, lineText: lineText(of: inspected)
                            )
                            // What applies here, from the library down (5.8).
                            InspectorRightsSection(targetKind: "segment", targetId: inspected, pageId: documentId)
                        }
                    } else if !language.isEmpty {
                        InspectorGroupBox(group: .details) { InspectorDetailsLine(rows: language) }
                    }
                    if level == .page {
                        // Page level: how the page's passes were made (#5149).
                        InspectorGroupBox(group: .history) { InspectorMakingSection(documentId: documentId) }
                        InspectorGroupBox(group: .linksAndRights) {
                            InspectorRightsSection(targetKind: "document", targetId: documentId, pageId: documentId)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(8)
            }
            // The Order section: the inspected segment's children, rearrangeable with the same verbs
            // as everywhere else (one `ReadingOrderStore`); hidden when it has none.
            ReadingOrderList(
                documentId: documentId, parentSegmentId: inspected, hidesWhenEmpty: true, onSelected: onOrderSelected
            )
                .frame(maxHeight: 260)
        }
        .task(id: inspected) {
            text = nil
            emptySections = []
            revealedSections = []
            editing = nil
            editNote = nil
            await reloadText()
            await flags?.load(documentId: documentId)
        }
        // A reading written for the inspected line elsewhere (typing in the Reader, a batch, an undo) shows
        // here at once: this line's readings generation moved, so its readings are re-read in place.
        // Not `.task(id: inspected)`, which also drops an Edit… in progress.
        .onChange(of: readingRevision) { Task { await reloadText() } }
        .onChange(of: selectedIds) { level = .selection }
        .focusable()
        .onKeyPress(.upArrow, phases: .down) { press in step(-1, extend: press.modifiers.contains(.shift)) }
        .onKeyPress(.downArrow, phases: .down) { press in step(1, extend: press.modifiers.contains(.shift)) }
        // The selection's settings are read under a task keyed on the ids: a newer selection cancels the older read, so
        // an older run can never finish last and show the old selection's answer (## 1075).
        .task(id: isMulti ? selectedIds : []) { if isMulti { await reloadText() } }
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
        let windowSteps = windowSteps
        Task {
            try? await runner.run(call, documentId: documentId, actionName: "Set Segment", steps: windowSteps)
            // The rows describe the lines as they are now (Mixed becomes one value once they agree).
            await reloadText()
        }
    }

    private var readingRevision: Int {
        guard let inspected, let segmentService else { return 0 }
        return SegmentStore.shared(for: segmentService).readingRevision(for: inspected)
    }

    /// Delete the selected lines (`source.editor.delete-selected-lines`): the Preview's own plan and runner.
    private func deleteSelected() {
        guard let segmentService else { return }
        let store = SegmentStore.shared(for: segmentService)
        let segments = SegmentDeleter.segments(selectedIds, documentId: documentId, store: store)
        let actionsService = actionStore?.actionsService, steps = windowSteps, documentId = documentId
        let focused = windowState?.sharedRegionSelection
        Task {
            deleteNote = await SegmentDeleter.run(
                segments, documentId: documentId, store: store, actionsService: actionsService, steps: steps,
                clearing: focused
            )
        }
    }

    private func reloadText() async {
        language = []
        if isMulti, let segmentService {
            // The selection as one: each line's resolved settings, Mixed where they differ.
            text = nil
            direction = nil
            multiNote = nil
            let ids = selectedIds
            // One request for the whole selection (`resolve-many`, #6082), not one per line; over the cap, none.
            var reads: [[InspectorLanguage.Setting]?] = []
            if ids.count <= Self.multiCap {
                reads = ((try? await segmentService.resolvedSettings(segmentIds: ids)) ?? []).map { Optional($0) }
                if reads.count != ids.count { reads = ids.map { _ in nil } }
            }
            // Apply only if this is still the selection (an older read must not show the old selection's answer).
            guard !Task.isCancelled, ids == selectedIds else { return }
            switch InspectorLanguage.selection(reads, total: ids.count, cap: Self.multiCap) {
            case .rows(let rows): language = rows
            case .note(let note): multiNote = note
            }
            return
        }
        guard let inspected, let segmentService else { return }
        text = try? await segmentService.readings(segmentId: inspected)
        let settings = (try? await segmentService.resolvedSettings(segmentId: inspected)) ?? []
        language = InspectorLanguage.rows(settings)
        direction = settings.first { $0.key == "direction" }?.value
    }

    /// Edit… saved (#5201): the Reader's typed-line message through the Reader's runner -- one
    /// `representation.create` correcting the reading shown, refused when another counts now, ⌘Z.
    private func saveEdit() async {
        guard let editing, let inspected, let segmentService, let actionsService = actionStore?.actionsService else { return }
        let runner = ReaderTextEditRunner(
            actionsService: actionsService, segmentService: segmentService, steps: windowSteps,
            refreshPage: { _ in await reloadText() }
        )
        if let problem = await InspectorReadingEdit.save(
            editing.words, documentId: documentId, segmentId: inspected, editing: editing.reading, runner: runner
        ) {
            editNote = InspectorReadingEdit.note(for: problem)
            if problem == ReaderTextEditRunner.staleProblem { await reloadText() }
        } else {
            self.editing = nil
        }
    }

    /// "Make This Count" (#5153): the audited `reading.choose`, ⌘Z by its own audit id.
    private func choose(_ reading: InspectorText.Reading, in text: InspectorText) {
        guard let inspected, let params = ReadingChoice.choose(reading, of: inspected, in: text),
              let actionsService = actionStore?.actionsService else { return }
        let windowSteps = windowSteps
        Task {
            try? await ReadingChoice.run(
                params, actionsService: actionsService, steps: windowSteps,
                afterChange: { await reloadText() }
            )
        }
    }
}

// MARK: - The Readings group

extension SegmentInspectorView {
    /// The Readings group shows when the segment has readings, or has none and says so with Type a Reading….
    private var hasReadingsGroup: Bool {
        if let text, !text.readings.isEmpty { return true }
        return noReadingSegmentId != nil
    }

    /// The inspected segment, when it was left without a reading (deleting-words-keeps-ink).
    private var noReadingSegmentId: String? {
        guard text != nil, let inspected,
              let segment = segments.first(where: { $0.id == inspected }), SegmentsPane.lacksReading(segment) else { return nil }
        return inspected
    }

    @ViewBuilder private var readingsGroup: some View {
        if let text, !text.readings.isEmpty {
            InspectorTextSection(
                text: text, onChoose: { reading in choose(reading, in: text) },
                onEdit: inspected == nil ? nil : { reading in
                    editing = (reading, reading.content)
                    editNote = nil
                }
            )
            if let editing {
                InspectorReadingEditor(
                    text: Binding(get: { editing.words }, set: { self.editing?.words = $0 }),
                    layout: InspectorReadingEdit.layout(direction: direction),
                    save: { Task { await saveEdit() } },
                    cancel: { self.editing = nil }
                )
            }
            if let editNote {
                Text(editNote).font(.caption).foregroundStyle(.secondary)
            }
        } else if let segmentId = noReadingSegmentId {
            InspectorNoReadingSection(segmentId: segmentId, documentId: documentId) { await reloadText() }
        }
    }
}

// MARK: - The path head

extension SegmentInspectorView {
    private var pathHead: some View {
        HStack(spacing: 4) {
            crumb("Page", selected: inspected == nil) { level = .page }
            ForEach(path?.crumbs ?? []) { crumb in
                Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.tertiary)
                self.crumb(crumb.label, selected: inspected == crumb.segmentId) { level = .segment(crumb.segmentId) }
            }
            Spacer(minLength: 0)
            addMenu
            // Verbs on the SELECTION (ruled: the Inspector offers verbs, never typing a reading).
            SegmentAttributeMenu(apply: { setAttribute($0) }, askForCode: { askingFor = $0; code = "" })
                .menuStyle(.button)
                .buttonStyle(.borderless)
                .fixedSize()
                .font(.caption)
            // Delete the selected lines: the one `segment.delete` batch every surface uses, one ⌘Z.
            Button { deleteSelected() } label: { Label("Delete", systemImage: "trash") }
                .buttonStyle(.borderless)
                .labelStyle(.iconOnly)
                .font(.caption)
                .disabled(selectedIds.isEmpty)
                .help("Delete the selected lines (⌘Z brings them back)")
                .accessibilityLabel("Delete")
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

    /// ONE Add menu (#6413): each section hidden while it holds nothing, shown again to use its own verbs.
    @ViewBuilder private var addMenu: some View {
        let hidden = InspectorSegmentLayout.addMenu(empty: emptySections, revealed: revealedSections)
        if !isMulti, inspected != nil, !hidden.isEmpty {
            Menu("Add") {
                ForEach(hidden) { addition in
                    Button("\(addition.title)…") { revealedSections.insert(addition) }
                }
            }
            .menuStyle(.button)
            .buttonStyle(.borderless)
            .fixedSize()
            .font(.caption)
            .help("Add a hand or a certainty mark to this segment")
        }
    }

    private func hides(_ addition: InspectorSegmentLayout.Addition) -> Bool {
        InspectorSegmentLayout.hides(addition, empty: emptySections, revealed: revealedSections)
    }

    private func noted(_ addition: InspectorSegmentLayout.Addition, empty: Bool) {
        if empty { emptySections.insert(addition) } else { emptySections.remove(addition) }
    }

    private var countsLine: String {
        InspectorPath.kindCounts(selectedIds, in: segments)
            .map { "\($0.count) \($0.count == 1 ? $0.kind : $0.kind + "s")" }
            .joined(separator: ", ")
    }
}

#Preview("Segment inspector: two lines selected") {
    SegmentInspectorView(documentId: "doc-1", selectedIds: ["line-1", "line-2"], onOrderSelected: nil)
        .frame(width: 320, height: 480)
}
