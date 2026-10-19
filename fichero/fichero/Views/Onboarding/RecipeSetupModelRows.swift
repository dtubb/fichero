import FicheroAPIClient
import SwiftUI

// Set Up… › Ready's model rows (#5573, #5592, #5619, #5664): what Start will fetch, the steps this Mac cannot
// run, and the steps Start will skip, each with its fix. Nobody downloads in setup (ruled 2026-10-11, #5664):
// Start fetches every model it needs, through the one download path, and its steps wait for them.

/// What Start will fetch before its steps run (#5664): the engine's one sentence, each model by the name a person
/// reads and its size, with the total ("Start downloads Qwen2.5-VL 7B (5.7 GB) and the Kraken reader PP-OCRv6
/// (60 MB): 5.8 GB in all."). No Download button and no "To download first": pressing Start is the download. A
/// model already on its way says how far it has got; an installed model the plan could use instead stays one press.
struct RecipeDownloadRows: View {
    let store: RecipeSetupStore

    var body: some View {
        let sentence = Self.sentence(store)
        let underWay = store.downloads.filter(Self.isUnderWay)
        let instead = store.downloads.filter { !($0.instead ?? []).isEmpty }
        if sentence != nil || !underWay.isEmpty || !instead.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                if let sentence {
                    Label(Self.withFreeDisk(sentence), systemImage: "arrow.down.circle")
                        .font(.body)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("setup.ready.startDownloads")
                }
                ForEach(underWay, id: \.model) { download in
                    Label("\(Self.words(download, store: store)): \(Self.engineProgress(download) ?? "downloading")",
                          systemImage: "arrow.down.circle.dotted")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
                // The other half of the one choice (#5583): an installed model instead of fetching one.
                ForEach(instead, id: \.model) { download in
                    ForEach(download.instead ?? [], id: \.card) { installed in
                        // A licence that is not open is in the button's words: the press accepts it.
                        let licence = (installed.licence ?? "").isEmpty ? "" : " (licence: \(installed.licence ?? ""))"
                        Button("Use the installed \(installed.name)\(licence)") {
                            Task { await store.useInstead(download, installed) }
                        }
                        .controlSize(.small)
                    }
                }
            }
        }
    }

    /// The engine's sentence plus the room there is for it ("5.8 GB in all; 112 GB free").
    static func withFreeDisk(_ sentence: String, free: Int64? = freeDiskBytes()) -> String {
        guard let free else { return sentence }
        let words = ByteCountFormatter.string(fromByteCount: free, countStyle: .file)
        return sentence.hasSuffix(".") ? "\(sentence.dropLast()); \(words) free." : "\(sentence) (\(words) free)"
    }

    static func freeDiskBytes() -> Int64? {
        let values = try? URL(fileURLWithPath: NSHomeDirectory()).resourceValues(
            forKeys: [.volumeAvailableCapacityForImportantUsageKey])
        return values?.volumeAvailableCapacityForImportantUsage
    }

    /// The engine's sentence for what Start will fetch, or nil when it fetches nothing.
    static func sentence(_ store: RecipeSetupStore) -> String? {
        store.startPlan?.startDownloads?.sentence
    }

    /// The engine's plan says this model is already downloading (a `download-model` job under way, #5660).
    static func isUnderWay(_ download: Components.Schemas.StartDownload) -> Bool {
        download.downloading == true
    }

    /// What the plan says of a download under way: its job's progress, or that it is downloading; nil for a
    /// download not started, which Start will fetch (#5664).
    static func engineProgress(_ download: Components.Schemas.StartDownload) -> String? {
        guard isUnderWay(download) else { return nil }
        return download.progress ?? "Downloading…"
    }

    /// "spaCy model es_core_news_sm · 13 MB · for Find names", or by its name ("Qwen2.5-VL 7B (OCR) · 5653 MB · for
    /// Correct") when the engine gives one.
    static func words(_ download: Components.Schemas.StartDownload, store: RecipeSetupStore) -> String {
        let runtime = download.runtime == "spacy" ? "spaCy" : download.runtime
        let size = download.sizeMb.map { " · \($0) MB" } ?? ""
        let steps = download.steps.map { store.title(ofStepId: $0) }.joined(separator: ", ")
        let model = download.name ?? "\(runtime) model \(download.model)"
        return "\(model)\(size) · for \(steps)"
    }
}

/// The models the plan's steps need that this Mac cannot run (#5592, `ai.where.fallback-free-and-asked`): under
/// each step, "Can't run on this Mac (why)", and for each free place the plan offers, a button that runs it there,
/// only on the press. A paid place is never offered, so it never has a button.
struct RecipeElsewhereRows: View {
    let store: RecipeSetupStore

    var body: some View {
        if !store.elsewhere.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(store.elsewhere, id: \.model) { entry in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(entry.steps.map { store.title(ofStepId: $0) }.joined(separator: ", "))
                            .font(.callout.weight(.medium))
                        Text("Can't run on this Mac (\(entry.why))").font(.callout).foregroundStyle(.secondary)
                        ForEach(entry.instead ?? [], id: \.provider) { place in
                            Button(Self.buttonTitle(place)) {
                                Task { await store.useFreePlace(entry, place) }
                            }
                            .controlSize(.small)
                        }
                    }
                }
            }
        }
    }

    /// "Run it free at Studio Mac".
    static func buttonTitle(_ place: Components.Schemas.StartPlaceInstead) -> String {
        "Run it free at \(place.providerName)"
    }
}

/// The steps Start will skip (#5573): each by title, the engine's why, and its fix as a button
/// when setup has one; the other steps still run. Choose a model… opens the model finder for that
/// step's job (#5619), as it does on the step's own row.
struct RecipeSkippedRows: View {
    let store: RecipeSetupStore
    let onFix: (String) -> Void
    /// The project whose model finder a fix opens; nil without a project.
    var project: LibraryManager.LibraryReference?

    @State private var findingFor: RecipeStepsView.FinderStep?
    @State private var reviewingLicence: RecipeStepsView.FinderStep?

    var body: some View {
        if !store.skippedStepsOfChosenStages.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text("Will not run").font(.subheadline.weight(.semibold))
                ForEach(store.skippedStepsOfChosenStages, id: \.step) { skipped in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(store.title(ofStepId: skipped.step)).font(.callout.weight(.medium))
                        Text(skipped.why).font(.callout).foregroundStyle(.secondary)
                        if let fix = skipped.fix {
                            Button(RecipeStepRow.fixTitle(fix)) { press(fix, step: skipped.step) }
                                .controlSize(.small)
                        }
                    }
                }
            }
            .sheet(item: $findingFor) { step in
                if let project {
                    ModelFinderSheet(project: project, setup: store, step: step) { findingFor = nil }
                }
            }
            .sheet(item: $reviewingLicence) { step in
                if let project {
                    LicenceReviewSheet(finder: project.modelFinderStore, setup: store, step: step) { reviewingLicence = nil }
                }
            }
        }
    }

    private func press(_ fix: String, step: String) {
        let route = RecipeStepsView.fixRoute(fix, hasProject: project != nil)
        guard route != .setup, let job = store.job(ofStepId: step) else {
            onFix(fix)
            return
        }
        let finderStep = RecipeStepsView.FinderStep(id: step, job: job)
        if route == .finder { findingFor = finderStep } else { reviewingLicence = finderStep }
    }
}

/// The steps that are built in (#5816): part of the plan, with the engine's sentence, in the plain secondary style of
/// any other line (no warning colour, no icon, no button). Never listed under "Will not run".
struct RecipeBuiltInRows: View {
    static let heading = "Built in"

    let store: RecipeSetupStore

    var body: some View {
        if !store.builtInSteps.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text(Self.heading).font(.subheadline.weight(.semibold))
                ForEach(store.builtInSteps, id: \.step) { built in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(store.title(ofStepId: built.step)).font(.callout.weight(.medium))
                        Text(built.sentence).font(.callout).foregroundStyle(.secondary)
                    }
                }
            }
        }
    }
}

#Preview("What Start will fetch") {
    RecipeDownloadRows(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil)))
        .padding()
        .frame(width: 480, height: 80)
}

#Preview("Will not run") {
    RecipeSkippedRows(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil)), onFix: { _ in })
        .padding()
        .frame(width: 480, height: 160)
}
