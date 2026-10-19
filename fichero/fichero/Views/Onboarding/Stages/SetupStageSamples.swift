import FicheroAPIClient
import SwiftUI

/// A stage's result on 3 to 5 of the person's pages, before Start (section 7c, #5668): the proposed pages with why
/// each was chosen, Compare on These Pages (a cloud try says its cost first and runs only on a yes), and what it made per
/// page. Read and Find Lines are tried by the comparison of candidates, which the page shows under its steps.
struct SetupStageSamples: View {
    @State var store: SetupStageTryStore

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
                Button("Compare on These Pages") { Task { await store.tryIt() } }
                    .disabled(store.isTrying || store.samples.isEmpty || store.result?.isUnderWay == true)
                if store.isTrying || store.result?.isUnderWay == true { ProgressView().controlSize(.small) }
                if let words = store.result?.underWayWords {
                    Text(words).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
            }
            if let costQuestion = store.costQuestion {
                Text(costQuestion).font(.callout).foregroundStyle(.secondary)
                Button("Compare, at That Cost") { Task { await store.tryIt(costOK: true) } }
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
    }

    @ViewBuilder
    private func resultView(_ result: SetupStageTryResult) -> some View {
        if let error = result.failure {
            Label(error, systemImage: "xmark.octagon").font(.callout).foregroundStyle(.red)
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

#Preview("Samples before a try") {
    SetupStageSamples(store: SetupStageTryStore(client: FicheroClient(libraryPath: nil), stageId: "names"))
        .padding()
        .frame(width: 520)
}
