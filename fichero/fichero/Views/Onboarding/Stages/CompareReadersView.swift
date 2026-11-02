import FicheroAPIClient
import SwiftUI

/// The compare view on a person's own page (`wide.compare.three-modes`, `.per-line-diff`, `.empty-and-error-states`, #5900): the
/// page with its lines boxed, then the readers' texts line by line in the chosen mode, and Use This for any one reading of a line
/// (`wide.compare.pick-per-line`). The engine matches the lines and works out the agreement; `CompareViewModel` chooses what shows;
/// this only lays it out. Behind the `wideSetUp` flag.
struct CompareReadersView: View {
    @State var store: CompareReadersStore
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let failure = store.failure {
                Label(failure, systemImage: "exclamationmark.triangle").font(.callout).foregroundStyle(.orange)
            }
            if let model = store.model {
                if let empty = model.emptyState {
                    Text(empty).font(.callout).foregroundStyle(.secondary).accessibilityIdentifier("compare.empty")
                } else {
                    controls(model)
                    picture(model)
                    content(model)
                }
            } else if store.failure == nil {
                ProgressView().controlSize(.small)
            }
        }
        .task { await store.load() }
        .focusable()
        .onKeyPress(phases: .down) { press in handle(press) }
    }

    /// The key map is `CompareViewModel.command(for:option:)`; this only reads the press and does what the model answers.
    private func handle(_ press: KeyPress) -> KeyPress.Result {
        let key = Self.key(of: press)
        guard let key, let command = CompareViewModel.command(for: key, option: press.modifiers.contains(.option)),
              let outcome = store.apply(command) else { return .ignored }
        switch outcome {
        case .useThis(let readerId, let line): Task { await store.pick(readerId: readerId, onLine: line) }
        case .close: dismiss()
        case .moved, .nothing: break
        }
        return outcome == .nothing ? .ignored : .handled
    }

    private static func key(of press: KeyPress) -> CompareViewModel.Key? {
        switch press.key {
        case .leftArrow: return .left
        case .rightArrow: return .right
        case .upArrow: return .up
        case .downArrow: return .down
        case .return: return .return
        case .escape: return .escape
        default: return press.characters.first.flatMap { $0.wholeNumberValue }.map { .digit($0) }
        }
    }

    private func controls(_ model: CompareViewModel) -> some View {
        HStack {
            Picker("Show", selection: Binding(get: { model.mode }, set: { store.set(mode: $0) })) {
                Text("Side by Side").tag(CompareViewModel.Mode.sideBySide)
                Text("Overlay").tag(CompareViewModel.Mode.overlay)
                if model.wipePair != nil { Text("Wipe").tag(CompareViewModel.Mode.wipe) }
            }
            .pickerStyle(.segmented).labelsHidden().fixedSize()
            .accessibilityIdentifier("compare.mode")
            Toggle("Only lines that differ", isOn: Binding(get: { model.onlyDiffering }, set: { store.setOnlyDiffering($0) }))
                .compareCheckbox()
                .accessibilityIdentifier("compare.onlyDiffering")
        }
    }

    private func picture(_ model: CompareViewModel) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            boxedPicture(model)
            if let note = CompareViewModel.noBoxesNote(readFrom: store.frame?.readFrom.rawValue,
                                                       followed: store.frame?.followed ?? false) {
                Text(note).font(.caption).foregroundStyle(.secondary)
                    .accessibilityIdentifier("compare.noBoxes")
            }
        }
    }

    private func boxedPicture(_ model: CompareViewModel) -> some View {
        LibraryImageView(documentId: store.pageId, imageType: .display)
            .aspectRatio(contentMode: .fit)
            .overlay {
                Canvas { context, size in
                    for line in model.lines {
                        guard let drawn = CompareViewModel.drawnBox(of: line, frame: store.frame, photograph: store.image),
                              let rect = CompareViewModel.boxRect(drawn.box, image: drawn.image, canvas: size) else { continue }
                        context.stroke(Path(rect), with: .color(line.differs ? .orange : .blue), lineWidth: 1)
                    }
                }
                .allowsHitTesting(false)
            }
            .frame(maxHeight: 280)
            .accessibilityHidden(true)
    }

    @ViewBuilder
    private func content(_ model: CompareViewModel) -> some View {
        switch model.mode {
        case .sideBySide: sideBySide(model)
        case .overlay: overlay(model)
        case .wipe: wipe(model)
        }
    }

    /// A column per reader, each line's text in its reader's column; a reader that did not read the page says why.
    private func sideBySide(_ model: CompareViewModel) -> some View {
        List {
            Section {
                ForEach(model.rows) { row in
                    HStack(alignment: .top) {
                        ForEach(Array(model.readers.enumerated()).filter { pair in model.visibleReaders.contains { $0.id == pair.element.id } },
                                id: \.offset) { index, reader in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(row.texts[index] ?? "").font(.callout).textSelection(.enabled)
                                if row.texts[index] != nil, row.differs, row.canPick {
                                    Button("Use This") { Task { await store.pick(readerId: reader.id, onLine: row.id) } }
                                        .controlSize(.small)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    .padding(4)
                    .background(row.differs ? Color.orange.opacity(0.1) : Color.clear, in: RoundedRectangle(cornerRadius: 4))
                    .overlay(RoundedRectangle(cornerRadius: 4).stroke(model.focusedLine == row.id ? Color.accentColor : .clear))
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel(model.rowAnnouncement(row))
                }
            } header: {
                HStack(alignment: .top) {
                    ForEach(model.visibleReaders, id: \.id) { reader in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(reader.label).font(.callout.weight(.medium))
                            if let why = model.notReadBecause(reader: reader.id) {
                                Text(why).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityElement(children: .combine)
                        .accessibilityLabel(model.columnLabel(reader))
                    }
                }
                if CompareViewModel.usesPager(model.platform) {
                    HStack(spacing: 6) {  // the sample strip: a dot per candidate
                        ForEach(Array(model.pagerDots.enumerated()), id: \.offset) { _, on in
                            Circle().fill(on ? Color.accentColor : Color.secondary.opacity(0.4)).frame(width: 7, height: 7)
                        }
                    }
                    .accessibilityHidden(true)
                }
            }
        }
        .listStyle(.plain)
    }

    /// One text per line, from the readers the legend has on; a click on a legend entry switches that reader off.
    private func overlay(_ model: CompareViewModel) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                ForEach(model.readers, id: \.id) { reader in
                    Toggle(reader.label, isOn: Binding(get: { !model.drawn.filter { $0.id == reader.id }.isEmpty },
                                                       set: { _ in store.toggle(reader: reader.id) }))
                        .compareCheckbox()
                }
            }
            List(model.rows) { row in
                ForEach(Array(model.readers.enumerated()), id: \.offset) { index, reader in
                    if model.drawn.contains(where: { $0.id == reader.id }), let text = row.texts[index] {
                        Text(text).font(.callout).textSelection(.enabled)
                    }
                }
            }
            .listStyle(.plain)
        }
    }

    /// Reader A's text up to the handle, reader B's after it; a slider (keyboard-operable) moves the handle.
    @ViewBuilder
    private func wipe(_ model: CompareViewModel) -> some View {
        if model.wipePair != nil {
            Slider(value: Binding(get: { model.handle }, set: { store.moveHandle(to: $0) }), in: 0...1)
                .accessibilityLabel("Wipe between the first two readers")
                .accessibilityAdjustableAction { direction in
                    store.moveHandle(to: model.handle + (direction == .increment ? 1 : -1) * CompareViewModel.handleStep)
                }
                .accessibilityIdentifier("compare.wipe")
            List(model.rows) { row in
                let first = row.texts.first.flatMap { $0 } ?? ""
                let second = row.texts.dropFirst().first.flatMap { $0 } ?? ""
                let cut = model.charactersOnA(of: first)
                Text(String(first.prefix(cut)) + String(second.dropFirst(min(second.count, cut)))).font(.callout)
            }
            .listStyle(.plain)
        }
    }
}

private extension View {
    /// The checkbox look on the Mac; the plain switch elsewhere (`.checkbox` is macOS only).
    @ViewBuilder func compareCheckbox() -> some View {
        #if os(macOS)
        toggleStyle(.checkbox)
        #else
        self
        #endif
    }
}

#Preview("Compare readers, before the engine answers") {
    CompareReadersView(store: CompareReadersStore(client: FicheroClient(libraryPath: nil), pageId: "page-1", platform: .mac))
        .padding().frame(width: 520, height: 420)
}
