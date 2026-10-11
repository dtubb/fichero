import FicheroAPIClient
import SwiftUI

/// A stage's result on 3 to 5 of the person's pages, before Start (section 7c, #5668): the proposed pages with why
/// each was chosen, Try on These Pages (a cloud try says its cost first and runs only on a yes), and what it made per
/// page. Read and Find Lines are tried by the comparison of candidates, which the page shows under its steps.
struct SetupStageSamples: View {
    @State var store: SetupStageTryStore

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("On your pages").font(.headline)
            ForEach(store.samples, id: \.id) { page in
                HStack(alignment: .firstTextBaseline) {
                    Text(page.name).font(.callout)
                    Text(page.why).font(.caption).foregroundStyle(.secondary)
                }
            }
            HStack {
                Button("Try on These Pages") { Task { await store.tryIt() } }
                    .disabled(store.isTrying || store.samples.isEmpty || store.result?.isUnderWay == true)
                if store.isTrying || store.result?.isUnderWay == true { ProgressView().controlSize(.small) }
            }
            if let costQuestion = store.costQuestion {
                Text(costQuestion).font(.callout).foregroundStyle(.secondary)
                Button("Try, at That Cost") { Task { await store.tryIt(costOK: true) } }
            }
            if let refusal = store.refusal {
                Label(refusal, systemImage: "exclamationmark.triangle").font(.callout).foregroundStyle(.orange)
            }
            if let result = store.result { resultView(result) }
        }
        .task { await store.load(); await store.follow() }
    }

    @ViewBuilder
    private func resultView(_ result: SetupStageTryResult) -> some View {
        if let error = result.error {
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
        // Organise's grouping of the samples (`finddocs.review.setup-page`): each proposed document and its pages.
        if let documents = result.documents, !documents.isEmpty {
            Text("Proposed documents").font(.callout.weight(.medium))
            ForEach(Array(documents.enumerated()), id: \.offset) { _, document in
                VStack(alignment: .leading, spacing: 2) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(document.name).font(.callout)
                        Text(SetupStageTryResult.detail(of: document)).font(.caption).foregroundStyle(.secondary)
                    }
                    Text(document.pageIds.map { store.name(of: $0) }.joined(separator: ", "))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(6)
                .overlay(RoundedRectangle(cornerRadius: 6)
                    .strokeBorder(.secondary, style: StrokeStyle(lineWidth: 1, dash: [3, 2])))
            }
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
