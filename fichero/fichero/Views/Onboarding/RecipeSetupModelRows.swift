import FicheroAPIClient
import SwiftUI

// Set Up… › Ready's model rows (#5573, #5592, #5619, #5620): the models to download first, the steps this Mac
// cannot run, and the steps Start will skip, each with its fix. Downloads go through the one download path
// (`ModelDownloads`); a model fix opens the model finder for the step.

/// The models the plan needs that are not on this Mac (#5573): each by name, its size and the
/// steps it serves, with Download through the one download path (`ModelDownloads`, #5620): the row
/// then says what the download's Activity job says, or why it failed; Start waits until they are
/// here, and the plan reads itself again when one is (`model.installed`).
struct RecipeDownloadRows: View {
    let store: RecipeSetupStore
    /// The project's downloads; nil without a project (nothing can be downloaded into no project).
    let downloads: ModelDownloads?

    var body: some View {
        if !store.downloads.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text("To download first").font(.subheadline.weight(.semibold))
                ForEach(store.downloads, id: \.model) { download in
                    let key = Self.key(download)
                    HStack(alignment: .firstTextBaseline) {
                        Text(Self.words(download, store: store)).font(.callout)
                        Spacer()
                        if let downloads, downloads.isActive(key) {
                            ProgressView().controlSize(.small)
                        } else if let downloads {
                            Button(ModelFinderCard.failed(downloads.state(key)) ? "Try Again" : "Download") {
                                Task { await downloads.start(key, name: download.name ?? download.model) }
                            }
                            .controlSize(.small)
                            .help("Download it to this Mac; Activity shows the download")
                        }
                    }
                    if let line = downloads?.line(key) {
                        let failed = ModelFinderCard.failed(downloads?.state(key))
                        Label(line, systemImage: failed ? "exclamationmark.triangle" : "arrow.down.circle")
                            .font(.caption)
                            .foregroundStyle(failed ? .orange : .secondary)
                            .textSelection(.enabled)
                    }
                    // The other half of the one choice (#5583): an installed model instead.
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

    /// A plan's download as the one download path keys it: its runtime and model, as the engine names them.
    static func key(_ download: Components.Schemas.StartDownload) -> ModelDownloads.Key {
        .init(runtime: download.runtime, model: download.model)
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

    var body: some View {
        if !store.skippedSteps.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text("Will not run").font(.subheadline.weight(.semibold))
                ForEach(store.skippedSteps, id: \.step) { skipped in
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
        }
    }

    private func press(_ fix: String, step: String) {
        if RecipeStepsView.fixRoute(fix, hasProject: project != nil) == .finder, let job = store.job(ofStepId: step) {
            findingFor = RecipeStepsView.FinderStep(id: step, job: job)
        } else {
            onFix(fix)
        }
    }
}

#Preview("Will not run") {
    RecipeSkippedRows(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil)), onFix: { _ in })
        .padding()
        .frame(width: 480, height: 160)
}
