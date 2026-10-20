import FicheroAPIClient
import SwiftUI

/// Check on your pages, under the reading step (section 8a, `source.try.bakeoff-is-the-same-tool`,
/// #4951): compare the readers on the project's corrected pages. One button; when the engine
/// will not run it (too few corrected lines), its sentence once and no button, and nothing else
/// waits on it. While it runs it is a job in Activity, its progress read from the Activity store,
/// and the person may leave. The result is the engine's table in the engine's order, each reader
/// by name (never a card id), with Use This for this project or one folder. Setup's Ready step
/// shows it as an optional row (Check on your pages); the Inspector under the reading step.
struct BakeoffSection: View {
    /// What the section needs beyond the recipe: the project's bake-off, its Activity, and the
    /// folders Use This can be scoped to.
    struct Context {
        let store: BakeoffStore
        let activity: ActivityStore?
        let folders: [BakeoffStore.Folder]
        /// The line finders' comparison, for Find lines (#5660 item 7); nil where there is none.
        var lineStore: BakeoffStore?

        /// The context for a step's own comparison: the readers' for a reading step, the line finders' for Find
        /// lines; nil for a step nothing compares.
        func forStep(_ job: String) -> Context? {
            switch job {
            case BakeoffStore.step: self
            case BakeoffStore.lineStep: lineStore.map { Context(store: $0, activity: activity, folders: folders) }
            default: nil
            }
        }
    }

    let context: Context
    /// The recipe whose reading step Use This sets (setup's store, or the Inspector's).
    let setup: RecipeSetupStore

    @State private var scope: BakeoffStore.Scope = .project
    @State private var confirmation: String?

    private var store: BakeoffStore { context.store }

    /// The comparison's job as Activity reports it, if Activity lists it.
    private var job: ActivityJob? {
        guard let id = store.comparison?.jobId else { return nil }
        return context.activity?.backgroundJobs.first { $0.id == id }
    }

    /// Changes as the job moves on, so the comparison is read again then.
    private var jobKey: String {
        guard store.isRunning else { return "idle" }
        return job.map { "\($0.state)" } ?? "not listed"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(store.comparesLines ? "Compare the line finders on your corrected pages"
                 : "Compare readers on your corrected pages").font(.callout.weight(.semibold))
            if let sentence = store.notReadySentence {
                Text(sentence)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            } else if store.canRun {
                Button(store.comparison == nil ? (store.comparesLines ? "Compare the Line Finders" : "Compare Readers")
                       : "Compare Again") {
                    confirmation = nil
                    Task { await store.start() }
                }
                .controlSize(.small)
            }
            if store.isStarting {
                ProgressView().controlSize(.small)
            }
            if let comparison = store.comparison {
                if store.isRunning {
                    progress(comparison)
                } else if let reason = comparison.reason, comparison.state != "done" {
                    Text(reason).font(.callout).foregroundStyle(.secondary)
                }
                Text(Self.basis(comparison, lines: store.comparesLines)).font(.caption).foregroundStyle(.secondary)
                if store.comparesLines { lineTable(comparison) } else { table(comparison) }
                if let why = comparison.noWinnerWhy {
                    Text(why).font(.caption).foregroundStyle(.secondary)
                }
                // No "Use for" a folder: a folder's own reader is stored but no run applies it yet, so Use This is for
                // the project (`source.recipe.per-folder`, spec review 2026-10-20).
                if let confirmation {
                    Label(confirmation, systemImage: "checkmark.circle").font(.body)
                }
            }
            if let error = store.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle").font(.body).foregroundStyle(.orange)
            }
        }
        .padding(.leading, 12)
        // Read on every showing: the newest comparison, and whether there are enough corrected
        // lines now (corrections made since the last showing count).
        .task {
            await store.loadLatest()
        }
        // Read the comparison again as its job moves on in Activity; while it runs and Activity
        // does not list it, read it now and then.
        .task(id: jobKey) {
            guard store.isRunning else { return }
            await store.refresh()
            while store.isRunning, !Task.isCancelled {
                try? await Task.sleep(for: .seconds(5))
                await store.refresh()
            }
        }
    }

    @ViewBuilder
    private func progress(_ comparison: BakeoffStore.Comparison) -> some View {
        let label = "Comparing \(store.comparesLines ? "the line finders" : "readers") on \(comparison.pages.count) pages. "
            + "It runs in Activity; you can carry on."
        if let job, job.total > 0 {
            ProgressView(value: Double(job.current), total: Double(job.total)) {
                Text(label).font(.body)
            } currentValueLabel: {
                Text("\(job.current) of \(job.total)")
            }
        } else {
            ProgressView { Text(label).font(.body) }
                .progressViewStyle(.linear)
        }
    }

    private func table(_ comparison: BakeoffStore.Comparison) -> some View {
        Table(of: BakeoffStore.Row.self) {
            // Use This sits after the numbers, before the long reasons, so it stays in reach however wide those are.
            TableColumn("Reader") { row in nameCell(row) }
                .width(min: 140, ideal: 180)
            TableColumn("Errors per 100 letters") { row in Text(BakeoffStore.errorRate(row)).monospacedDigit() }
                .width(min: 44, ideal: 50)
            TableColumn("Errors per 100 words") { row in Text(BakeoffStore.wordErrorRate(row)).monospacedDigit() }
                .width(min: 44, ideal: 50)
            TableColumn("Time") { row in Text(BakeoffStore.time(row)).monospacedDigit() }
                .width(min: 80, ideal: 90)
            TableColumn("") { row in useButton(row) }
                .width(min: 70, ideal: 76)
            TableColumn("Cost for all pages") { row in wrapping(BakeoffStore.cost(row)) }
                .width(min: 90, ideal: 110)
            TableColumn("Why not scored") { row in wrapping(BakeoffStore.note(row), secondary: true) }
                .width(min: 120, ideal: 180)
        } rows: {
            // The engine's order, as it ranked them; the app never re-sorts.
            ForEach(comparison.rows) { row in
                TableRow(row)
            }
        }
        .frame(height: CGFloat(comparison.rows.count) * 40 + 34)
    }

    /// The line finders (#5660 item 7): the checked lines each found, its extra lines and its time.
    private func lineTable(_ comparison: BakeoffStore.Comparison) -> some View {
        Table(of: BakeoffStore.Row.self) {
            TableColumn("Line finder") { row in Text(BakeoffStore.name(of: row)) }
                .width(min: 150, ideal: 210)
            TableColumn("Lines found") { row in Text(BakeoffStore.linesFound(row)).monospacedDigit() }
                .width(min: 70, ideal: 90)
            TableColumn("Extra lines") { row in Text(BakeoffStore.extraLines(row)).monospacedDigit() }
                .width(min: 60, ideal: 80)
            TableColumn("Time") { row in Text(BakeoffStore.time(row)).monospacedDigit() }
                .width(min: 56, ideal: 70)
            TableColumn("Why not compared") { row in wrapping(row.why ?? "", secondary: true) }
                .width(min: 120, ideal: 200)
            TableColumn("") { row in useButton(row) }
                .width(min: 70, ideal: 80)
        } rows: {
            ForEach(comparison.rows) { row in
                TableRow(row)
            }
        }
        .frame(height: CGFloat(comparison.rows.count) * 40 + 34)
    }

    /// A cell's words on up to two lines, the whole of them on hover: a cost or a reason never cut to "…" unread.
    private func wrapping(_ text: String, secondary: Bool = false) -> some View {
        Text(text)
            .foregroundStyle(secondary ? .secondary : .primary)
            .lineLimit(2)
            .fixedSize(horizontal: false, vertical: true)
            .help(text)
    }

    /// A reader by name, and why it takes part (the rules' pick, or one of each kind tried beside them).
    private func nameCell(_ row: BakeoffStore.Row) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(BakeoffStore.name(of: row))
            Text(BakeoffStore.role(row)).font(.caption).foregroundStyle(.secondary)
        }
    }

    /// Use This, where the engine accepts it; disabled, saying why, where it does not.
    private func useButton(_ row: BakeoffStore.Row) -> some View {
        let refusal = BakeoffStore.useRefusal(row, comparesLines: store.comparesLines)
        return Button("Use This") { use(row) }
            .controlSize(.small)
            .disabled(refusal != nil || store.usingCard != nil)
            .help(refusal ?? (store.usingCard != nil ? "Setting another one; wait for it to finish"
                              : "Use this for the step"))
    }

    private func use(_ row: BakeoffStore.Row) {
        let name = BakeoffStore.name(of: row)
        let scopeName: String
        switch scope {
        case .project: scopeName = "this project"
        case .folder(let id): scopeName = context.folders.first { $0.id == id }?.name ?? "the folder"
        }
        confirmation = nil
        Task {
            if await store.use(row, scope: scope, in: setup) {
                confirmation = "\(name) now reads \(scopeName)."
            }
        }
    }

    /// What the table rests on, in one line.
    static func basis(_ comparison: BakeoffStore.Comparison, lines: Bool = false) -> String {
        let pages = comparison.pages.count
        let sample = "\(comparison.lines) corrected lines on \(pages) page\(pages == 1 ? "" : "s")"
        return lines
            ? "Measured on \(sample), ranked by the share of checked lines found, then fewer extra lines, then time."
            : "Measured on \(sample), ranked by error rate, then this Mac before the cloud, cost and speed."
    }
}

extension BakeoffSection.Context {
    /// A project's own bake-off, Activity and folders.
    @MainActor
    init(project: LibraryManager.LibraryReference) {
        self.init(store: project.bakeoffStore, activity: project.activityStore,
                  folders: BakeoffStore.Folder.folders(in: project.documentStore.collections),
                  lineStore: project.lineBakeoffStore)
    }
}

extension BakeoffStore.Folder {
    /// The project's folders, by name, for Use This's scope.
    static func folders(in documents: [Document]) -> [BakeoffStore.Folder] {
        documents.filter { $0.docType == .folder }
            .map { BakeoffStore.Folder(id: $0.id, name: $0.name) }
            .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }
}

// MARK: - Previews

enum BakeoffPreviewFixtures {
    static func row(rank: Int, card: String, name: String, reader: BakeoffStore.Row.ReaderPayload?, ruleRank: Int?,
                    local: Bool = true, cer: Double?, pagesPerHour: Double?, cost: Double? = 0,
                    why: String? = nil) -> BakeoffStore.Row {
        BakeoffStore.Row(
            rank: rank, card: card, name: name,
            role: BakeoffStore.Row.RolePayload(rawValue: ruleRank == nil ? "baseline for print" : "rule rank")!,
            ruleRank: ruleRank, reader: reader, model: nil, runsOn: local ? "this-mac" : "cloud", local: local,
            cer: cer, policy: cer == nil ? nil : "diplomatic", scores: .init(additionalProperties: [:]),
            perPage: [], pagesPerHour: pagesPerHour, seconds: nil,
            costUsd: .init(value: cost, basis: local ? "measured" : "estimate", from: "price list"),
            carbonGPerPage: nil, trainable: true, sizeGb: 0.02, why: why
        )
    }

    static let comparison = BakeoffStore.Comparison(
        id: "job-1", jobId: "job-1", step: BakeoffStore.step, startedAt: "2026-10-05T10:00:00Z", state: "done",
        reason: nil,
        pages: [.init(documentId: "p1", name: "f. 1r", lines: 61), .init(documentId: "p2", name: "f. 1v", lines: 58)],
        leftOut: [], lines: 119,
        rows: [
            row(rank: 1, card: "kraken-catmus", name: "CATMuS Medieval, medieval manuscripts (French, Latin, Spanish)",
                reader: .kraken, ruleRank: 2, cer: 0.042, pagesPerHour: 410),
            row(rank: 2, card: "kraken-mccatmus", name: "McCATMuS, general Latin-script recognition, 16th-21st century",
                reader: .kraken, ruleRank: 1, cer: 0.061, pagesPerHour: 380),
            row(rank: 3, card: "gpt-vision", name: "GPT vision", reader: .vision, ruleRank: 3, local: false, cer: nil,
                pagesPerHour: nil,
                cost: 18.4, why: "a remote model target is not built in the evaluation job yet: priced, not scored")
        ],
        winner: "kraken-catmus"
    )
}

#Preview("Compared") {
    let store = BakeoffStore(client: FicheroClient(libraryPath: nil))
    store.previewComparison(BakeoffPreviewFixtures.comparison)
    return BakeoffSection(
        context: .init(store: store, activity: nil, folders: [.init(id: "f1", name: "Letters, 1650s")]),
        setup: RecipeSetupStore(client: FicheroClient(libraryPath: nil))
    )
    .padding()
    .frame(width: 820, height: 320)
}

#Preview("Not enough corrected lines") {
    let store = BakeoffStore(client: FicheroClient(libraryPath: nil))
    store.previewRefusal("The bake-off needs at least 100 corrected lines on at least 2 pages; there are 40 on 1 page. "
                         + "Correct 60 more corrected lines and corrected lines on 1 more page, and it will be offered again.")
    return BakeoffSection(context: .init(store: store, activity: nil, folders: []),
                          setup: RecipeSetupStore(client: FicheroClient(libraryPath: nil)))
        .padding()
        .frame(width: 520, height: 160)
}
