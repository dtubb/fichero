import FicheroAPIClient
import SwiftUI

/// A stage's result on 3 to 5 of the person's pages, before Start (section 7c, #5668): the proposed pages with why
/// each was chosen, Compare on These Pages (a cloud try says its cost first and runs only on a yes), and what it made per
/// page. Read and Find Lines are tried by the comparison of candidates, which the page shows under its steps.
struct SetupStageSamples: View {
    @State var store: SetupStageTryStore
    /// Use This One, per model, from the compare window (the use-candidate route); nil where a step cannot take it.
    var useThis: ((StageCandidate) -> Void)?
    /// Keeps the choices on screen on the project before a try: the engine tries what the saved setup has chosen, so a
    /// step just ticked is "not chosen" until this runs (`source.onboard.stages.try-reads-the-screen`, #6015). False: do not try.
    var saveFirst: (() async -> Bool)?
    @State private var comparing: ComparedPage?

    private func compare(costOK: Bool = false) {
        Task {
            if let saveFirst, await !saveFirst() { return }
            await store.tryIt(costOK: costOK)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("On your pages").font(.headline)
            // A sample's name is the engine's for that page ("f. 1r"), never a Document's raw name.
            ForEach(store.samples, id: \.id) { sample in
                HStack(alignment: .center) {
                    // The person's own page, drawn from its own picture (#5808): a placeholder until its thumbnail
                    // is made, never the shipped example image.
                    if sample.thumbnail ?? false {
                        LibraryImageView(documentId: sample.id, imageType: .thumbnail)
                            .aspectRatio(contentMode: .fill)
                            .frame(width: 28, height: 36)
                            .clipShape(RoundedRectangle(cornerRadius: 4))
                    } else {
                        RoundedRectangle(cornerRadius: 4).fill(.quaternary).frame(width: 28, height: 36)
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        Text(sample.name).font(.callout)
                        Text(sample.yours ?? true ? "Your page · \(sample.why)" : sample.why)
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            HStack(alignment: .firstTextBaseline) {
                Button("Compare on These Pages") { compare() }
                    .disabled(store.isTrying || store.samples.isEmpty || store.result?.isUnderWay == true)
                if store.isTrying || store.result?.isUnderWay == true { ProgressView().controlSize(.small) }
                if let words = store.result?.underWayWords {
                    Text(words).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
                // Set Up is modal: the try can be stopped where it was started (`try-progress-in-place`).
                if store.result?.isUnderWay == true, store.result?.jobId != nil {
                    Button("Stop") { Task { await store.stop() } }
                }
            }
            // Where each model is, in place: "Kraken: page 2 of 5, finding lines".
            ForEach(store.result?.progressLines ?? [], id: \.self) { line in
                Text(line).font(.caption).foregroundStyle(.secondary)
            }
            if let costQuestion = store.costQuestion {
                Text(costQuestion).font(.callout).foregroundStyle(.secondary)
                Button("Compare, at That Cost") { compare(costOK: true) }
            }
            if let refusal = store.refusal {
                Label(refusal, systemImage: "exclamationmark.triangle").font(.callout).foregroundStyle(.orange)
            }
            if store.samples.isEmpty, store.refusal == nil, !store.isTrying {
                // The button is off without sample pages: say why rather than leave it dead (#5806).
                Text("Add some pages to the project first: there are none to compare on yet.")
                    .font(.callout).foregroundStyle(.secondary)
            }
            if let result = store.result { resultView(result) }
        }
        .task { await store.load(); await store.follow() }
        .sheet(item: $comparing) { page in
            StageCompareWindow(pageId: page.id, name: store.name(of: page.id),
                               candidates: store.result?.candidates ?? [], useThis: useThis)
        }
    }

    @ViewBuilder
    private func resultView(_ result: SetupStageTryResult) -> some View {
        if let error = result.failure {
            Label(error, systemImage: "xmark.octagon").font(.callout).foregroundStyle(.red)
        }
        // Each model beside the others on each page (#6034).
        let compared = (result.candidates ?? []).filter { !($0.perPage ?? []).isEmpty }
        if compared.count > 1 {
            // First the candidates side by side on each page, the picture with each one's lines and its reading
            // (#6034), counts under each; the page's name opens it larger in the compare window (#6047, #5856).
            ForEach(result.pages ?? store.samples.map(\.id), id: \.self) { pageId in
                let here = compared.filter { $0.perPage?.contains { $0.id == pageId } == true }
                if here.count > 1 {
                    VStack(alignment: .leading, spacing: 4) {
                        Button { comparing = ComparedPage(id: pageId) } label: {
                            Text(store.name(of: pageId)).font(.callout.weight(.medium))
                        }
                        .buttonStyle(.plain)
                        .help("Open this page larger, to compare the models on it")
                        StageCompareColumns(pageId: pageId, candidates: here, useThis: useThis,
                                            pictureWidth: 160...260)
                    }
                    .accessibilityIdentifier("setup.compare.sideBySide")
                }
            }
        }
        ForEach(result.perPage ?? [], id: \.id) { page in
            VStack(alignment: .leading, spacing: 2) {
                Text(store.name(of: page.id)).font(.callout.weight(.medium))
                let summary = SetupStageTryResult.summary(of: page)
                if !summary.isEmpty { Text(summary).font(.caption).foregroundStyle(.secondary) }
                if let reading = page.readings?.first {
                    Text(reading.text).font(.callout).lineLimit(4)
                }
                ForEach(page.statements?.prefix(3).map { $0 } ?? [], id: \.self) { statement in
                    Text(statement).font(.caption)
                }
            }
        }
        // Organise on its run of pages (`finddocs.review.setup-page`): the strip, its proposed documents as dashed
        // groups over it, its entries under their pages.
        if result.documents != nil || result.entries != nil {
            OrganiseTryStrip(
                pages: result.pages ?? store.samples.map(\.id),
                documents: result.documents ?? [],
                entries: result.entries ?? [],
                name: { store.name(of: $0) }
            )
        }
        if let names = result.names, !names.isEmpty {
            FlowLayout(spacing: 4) {
                ForEach(names, id: \.name) { name in
                    Text(name.name)
                        .font(.caption)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Color.secondary.opacity(0.12), in: Capsule())
                        .help(name.type ?? "")
                }
            }
        }
    }
}

/// The page the compare window is open on.
struct ComparedPage: Identifiable { let id: String }

#Preview("Samples before a try") {
    SetupStageSamples(store: SetupStageTryStore(client: FicheroClient(libraryPath: nil), stageId: "names"))
        .padding()
        .frame(width: 520)
}
