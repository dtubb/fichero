import FicheroAPIClient
import SwiftUI

/// "34 of 92 pages are in iCloud and not on this Mac", with Copy into the Project (#5669): in Set Up's Add material
/// once material is added, and on Ready before Start. Without room on this disk it says why, with the numbers, and
/// offers nothing.
struct ICloudPagesNotice: View {
    let store: ICloudPagesStore
    let actionsService: ActionsService?
    @Environment(WindowSteps.self) private var steps: WindowSteps?

    var body: some View {
        if let pages = store.pages, pages.pages > 0 {
            VStack(alignment: .leading, spacing: 6) {
                Label(pages.sentence, systemImage: "icloud.and.arrow.down")
                    .font(.callout)
                if let refusal = pages.refusal, !pages.room {
                    Text(refusal).font(.caption).foregroundStyle(.orange)
                } else if let actionsService {
                    Button("Copy into the Project") {
                        Task { await store.copyIntoProject(actionsService: actionsService, steps: steps) }
                    }
                    .help(pages.offer)
                    .disabled(!store.canCopy)
                    Text(pages.offer).font(.caption).foregroundStyle(.secondary)
                }
                if store.isCopying { ProgressView().controlSize(.small) }
                if let refusal = store.refusal { Text(refusal).font(.caption).foregroundStyle(.orange) }
            }
            .accessibilityIdentifier("setup.inICloud")
        } else if let copied = store.copied {
            Label(copied, systemImage: "checkmark.circle").font(.callout)
        }
    }
}

#Preview("Pages in iCloud") {
    ICloudPagesNotice(store: ICloudPagesStore(client: FicheroClient(libraryPath: nil)), actionsService: nil)
        .padding()
        .frame(width: 480)
}
