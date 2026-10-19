import SwiftUI

/// The Reader's lens "Where the Readers Disagree" (#5665, `source.disagree.lens`): the page's lines, each word tinted
/// by how many readers gave it; clicking a word lists its variants (`.popover`); Page › Next Doubtful Word walks the
/// doubtful ones (`.next-doubtful`). With fewer than two readings it says so and offers another reader
/// (`.fewer-than-two`). Read from the project's `ReadingDisagreementStore`.
struct ReaderDisagreementView: View {
    let pageId: String

    @Environment(LibraryManager.self) private var libraryManager: LibraryManager?
    @Environment(DocumentStore.self) private var documentStore: DocumentStore?
    @Environment(StorageService.self) private var storageService: StorageService?

    /// The page's picture, read when its words have boxes to tint over it.
    @State private var pageImage: PlatformImage?
    /// Why the step could not be added, in the engine's words.
    @State private var findRefusal: String?

    private var library: LibraryManager.LibraryReference? {
        documentStore.flatMap { libraryManager?.library(owningService: $0) }
    }

    var body: some View {
        if let library {
            let store = library.disagreementStore
            let libraryId = library.id
            let manager = libraryManager
            let storage = storageService
            let hasDoubtful = !(store.disagreement(of: pageId)?.doubtfulRefs.isEmpty ?? true)
            DisagreementPageView(
                state: store.pages[pageId],
                selected: Binding(get: { store.selected[pageId] }, set: { store.selected[pageId] = $0 }),
                readWithAnotherModel: { manager?.requestSetUp(for: libraryId, stage: "read") },
                findWhereTheyDisagree: {
                    let setup = library.recipeSetupStore
                    Task {
                        findRefusal = nil
                        if await setup.addStep(job: DisagreementPageView.findJob) {
                            manager?.requestSetUp(for: libraryId, stage: "read")
                        } else {
                            findRefusal = setup.errorMessage
                        }
                    }
                },
                findRefusal: findRefusal,
                pageImage: pageImage
            )
            .task(id: pageId) {
                pageImage = nil
                await store.load(pageId: pageId)
                if let disagreement = store.disagreement(of: pageId), DisagreementOverlay.hasBoxes(disagreement) {
                    pageImage = try? await storage?.getDisplayPlatformImage(pageId)
                }
            }
            .focusedSceneValue(\.nextDoubtfulWord, FocusedLibraryAction(isEnabled: hasDoubtful, target: pageId) {
                _ = store.selectNextDoubtful(on: pageId)
            })
            .focusedSceneValue(\.previousDoubtfulWord, FocusedLibraryAction(isEnabled: hasDoubtful, target: pageId) {
                _ = store.selectPreviousDoubtful(on: pageId)
            })
        }
    }
}

/// The lens's body, given what the store holds.
struct DisagreementPageView: View {
    let state: ReadingDisagreementStore.State?
    @Binding var selected: ReadingDisagreement.WordRef?
    let readWithAnotherModel: () -> Void
    /// Adds the step Find where the readers disagree to the project's plan and opens Set Up on it.
    var findWhereTheyDisagree: () -> Void = {}
    /// Why adding that step did not work, in the engine's words.
    var findRefusal: String?
    /// The page's picture, when its words have boxes: each word's tint is drawn over it.
    var pageImage: PlatformImage?

    static let findTitle = "Find Where the Readers Disagree"
    /// The recipe step it adds (`source.disagree.recipe-step`).
    static let findJob = "find-where-readers-disagree"

    /// The word whose variants are open; a click opens it, navigation only selects.
    @State private var popoverFor: ReadingDisagreement.WordRef?

    var body: some View {
        switch state {
        case nil, .loading?:
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        case .unavailable(let words)?:
            PaneEmptyStateView(reason: words, systemImage: "exclamationmark.bubble")
        case .loaded(let disagreement)?:
            if disagreement.isComparable {
                lines(of: disagreement)
            } else {
                fewerThanTwo
            }
        }
    }

    /// One line and one offer (`source.disagree.fewer-than-two`).
    private var fewerThanTwo: some View {
        VStack(spacing: 10) {
            Text("This page has fewer than two readings, so there is nothing to compare.")
                .foregroundStyle(.secondary)
            HStack {
                Button("Read with Another Model…", action: readWithAnotherModel)
                Button(Self.findTitle, action: findWhereTheyDisagree)
                    .help("Adds the step to the project's Read stage: one reader, read five times, then compared")
            }
            if let findRefusal {
                Text(findRefusal).font(.callout).foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityIdentifier("reader.disagreement.fewerThanTwo")
    }

    private func lines(of disagreement: ReadingDisagreement) -> some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    header(of: disagreement)
                    // Words with boxes are tinted on the page itself; a line with a word that has none stays text.
                    let drawn = DisagreementOverlay.hasBoxes(disagreement)
                    if drawn { tintedPage(disagreement) }
                    ForEach(drawn ? DisagreementOverlay.linesAsText(disagreement) : Array(disagreement.lines.indices),
                            id: \.self) { index in
                        lineRow(disagreement, index)
                    }
                }
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .onChange(of: selected) { _, ref in
                if let ref { withAnimation { proxy.scrollTo(ref.line, anchor: .center) } }
            }
        }
        .accessibilityIdentifier("reader.disagreement")
    }

    /// The page's figure, labelled agreement, with the readers and the convention compared at.
    private func header(of disagreement: ReadingDisagreement) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            if let page = disagreement.pageAgreement {
                Text(ReadingDisagreement.percent(page)).font(.headline)
            }
            let readers = disagreement.readers.map(\.label).joined(separator: ", ")
            let convention = disagreement.normalisedAs.map { ", compared \($0.replacingOccurrences(of: "_", with: " "))" }
            Text("\(disagreement.readers.count) readers: \(readers)\(convention ?? "")")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private func lineRow(_ disagreement: ReadingDisagreement, _ index: Int) -> some View {
        let line = disagreement.lines[index]
        return VStack(alignment: .leading, spacing: 4) {
            Text(ReadingDisagreement.percent(line.agreement))
                .font(.caption)
                .foregroundStyle(.secondary)
            FlowLayout(spacing: 4) {
                ForEach(line.words.indices, id: \.self) { wordIndex in
                    wordView(disagreement, ReadingDisagreement.WordRef(line: index, word: wordIndex))
                }
            }
        }
        .id(index)
    }

    @ViewBuilder
    private func wordView(_ disagreement: ReadingDisagreement, _ ref: ReadingDisagreement.WordRef) -> some View {
        if let word = disagreement.word(ref) {
            Text(word.text)
                .font(.body)
                .padding(.horizontal, 2)
                .background(DisagreementTint.of(word.agreement).color, in: RoundedRectangle(cornerRadius: 3))
                .overlay {
                    if selected == ref {
                        RoundedRectangle(cornerRadius: 3).strokeBorder(Color.accentColor, lineWidth: 1.5)
                    }
                }
                .contentShape(Rectangle())
                .onTapGesture {
                    selected = ref
                    popoverFor = ref
                }
                .popover(isPresented: Binding(get: { popoverFor == ref },
                                              set: { if !$0, popoverFor == ref { popoverFor = nil } })) {
                    DisagreementWordPopover(word: word.text, rows: disagreement.variantRows(for: word))
                }
                .accessibilityLabel("\(word.text), \(ReadingDisagreement.percent(word.agreement))")
                .accessibilityAddTraits(.isButton)
        }
    }

    /// The page with each boxed word's tint over it, at the size it is drawn; a click opens the word's variants.
    @ViewBuilder
    private func tintedPage(_ disagreement: ReadingDisagreement) -> some View {
        if let pageImage {
            Image(platformImage: pageImage)
                .resizable()
                .scaledToFit()
                .overlay {
                    GeometryReader { geometry in
                        let frame = DisagreementOverlay.frame(of: disagreement, imageSize: pageImage.size)
                        ForEach(DisagreementOverlay.boxes(disagreement, frame: frame, drawnAt: geometry.size),
                                id: \.ref) { box in
                            boxView(disagreement, box)
                        }
                    }
                }
                .accessibilityIdentifier("reader.disagreement.page")
        } else {
            ProgressView().frame(maxWidth: .infinity, minHeight: 120)
        }
    }

    @ViewBuilder
    private func boxView(_ disagreement: ReadingDisagreement, _ box: DisagreementOverlay.Box) -> some View {
        if let word = disagreement.word(box.ref) {
            Rectangle()
                .fill(box.tint.color)
                .overlay {
                    if selected == box.ref { Rectangle().strokeBorder(Color.accentColor, lineWidth: 1.5) }
                }
                .contentShape(Rectangle())
                .frame(width: box.rect.width, height: box.rect.height)
                .position(x: box.rect.midX, y: box.rect.midY)
                .onTapGesture {
                    selected = box.ref
                    popoverFor = box.ref
                }
                .popover(isPresented: Binding(get: { popoverFor == box.ref },
                                              set: { if !$0, popoverFor == box.ref { popoverFor = nil } })) {
                    DisagreementWordPopover(word: word.text, rows: disagreement.variantRows(for: word))
                }
                .accessibilityLabel("\(word.text), \(ReadingDisagreement.percent(word.agreement))")
                .accessibilityAddTraits(.isButton)
        }
    }
}

/// A word's variants and who gave each (`source.disagree.popover`).
struct DisagreementWordPopover: View {
    let word: String
    let rows: [ReadingDisagreement.VariantRow]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(word).font(.headline)
            ForEach(rows.indices, id: \.self) { index in
                let row = rows[index]
                HStack(alignment: .firstTextBaseline) {
                    Text(row.text).font(BundledFonts.shared.font(.body))  // a variant is line text (#5842)
                    Spacer()
                    Text(row.count).font(.caption).monospacedDigit().foregroundStyle(.secondary)
                }
                Text(row.readers).font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding()
        .frame(minWidth: 220)
        .accessibilityIdentifier("reader.disagreement.popover")
    }
}

#Preview("Where the readers disagree") {
    DisagreementPageView(state: .loaded(DisagreementPreview.page), selected: .constant(nil), readWithAnotherModel: {})
        .frame(width: 520, height: 320)
}

#Preview("Fewer than two readings") {
    DisagreementPageView(
        state: .loaded(.init(pageId: "p", readers: [.init(id: "k", label: "Kraken")], pageAgreement: nil,
                             normalisedAs: "as_written", lines: [])),
        selected: .constant(nil), readWithAnotherModel: {}
    )
    .frame(width: 520, height: 200)
}

/// A page read by three readers, for the previews.
enum DisagreementPreview {
    static let page: ReadingDisagreement = {
        let json = """
        {"page_id":"p","readers":[{"id":"k","label":"Kraken"},{"id":"q1","label":"Comma Qwen, run 1"},
         {"id":"q2","label":"Comma Qwen, run 2"}],"page_agreement":0.78,"normalised_as":"as_written",
         "lines":[{"segment_id":"l1","agreement":0.78,"text":"vende una casa","words":[
          {"text":"vende","char_start":0,"char_end":5,"agreement":1,"variants":[{"text":"vende","readers":["k","q1","q2"]}]},
          {"text":"una","char_start":6,"char_end":9,"agreement":0.67,
           "variants":[{"text":"una","readers":["k","q1"]},{"text":"vna","readers":["q2"]}]},
          {"text":"casa","char_start":10,"char_end":14,"agreement":0.33,
           "variants":[{"text":"casa","readers":["k"]},{"text":"cosa","readers":["q1"]},{"text":"","readers":["q2"]}]}]}]}
        """
        return (try? ReadingDisagreement.decode(Data(json.utf8)))
            ?? ReadingDisagreement(pageId: nil, readers: [], pageAgreement: nil, normalisedAs: nil, lines: [])
    }()
}
