import FicheroAPIClient
import SwiftUI

/// The chain strip under a sample page (`wide.chain.strip-on-the-page`, #5386): the photograph, then each picture a step made of it,
/// each with its operation's name and figure, "Find Lines reads this one" on the one every later step reads, and a passed-over
/// picture's reason. Clicking a thumbnail shows it larger. Words are the engine's; this lays them out.
struct RenditionChainStripView: View {
    @State private var store: RenditionChainStore

    init(client: FicheroClient, pageId: String) {
        _store = State(initialValue: RenditionChainStore(client: client, pageId: pageId))
    }

    @Environment(RenditionService.self) private var renditionService: RenditionService?
    @State private var shown: String?

    var body: some View {
        Group {
            if RenditionChainRow.isWorthShowing(store.rows) {
                VStack(alignment: .leading, spacing: 6) {
                    ScrollView(.horizontal) {
                        HStack(alignment: .top, spacing: 10) {
                            ForEach(store.rows) { row in cell(row) }
                        }
                    }
                    .pagerScroller()
                    if let shown, let row = store.rows.first(where: { $0.id == shown }) { large(row) }
                }
                .accessibilityIdentifier("prepareImages.chain")
            } else if let failure = store.failure {
                Text(failure).font(.caption).foregroundStyle(.secondary)
            }
        }
        .task { await store.load() }
    }

    private func cell(_ row: RenditionChainRow) -> some View {
        Button { shown = shown == row.id ? nil : row.id } label: {
            VStack(alignment: .leading, spacing: 2) {
                picture(row).frame(width: 56, height: 72).clipShape(RoundedRectangle(cornerRadius: 4))
                    .overlay(RoundedRectangle(cornerRadius: 4).stroke(row.readsThis ? Color.accentColor : .clear, lineWidth: 2))
                Text(row.title).font(.caption.weight(.medium))
                Text(row.figure).font(.caption2).foregroundStyle(.secondary)
                if row.readsThis { Text(RenditionChainRow.readsThisWords).font(.caption2).foregroundStyle(Color.accentColor) }
                if let why = row.passedOver { Text(why).font(.caption2).foregroundStyle(.orange) }
            }
            .frame(width: 110, alignment: .leading)
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("prepareImages.chain.\(row.id)")
    }

    @ViewBuilder private func picture(_ row: RenditionChainRow) -> some View {
        if let renditionId = row.renditionId {
            RenditionPicture(documentId: store.pageId, renditionId: renditionId, service: renditionService)
        } else {
            LibraryImageView(documentId: store.pageId, imageType: .thumbnail).aspectRatio(contentMode: .fill)
        }
    }

    private func large(_ row: RenditionChainRow) -> some View {
        picture(row).aspectRatio(contentMode: .fit).frame(maxHeight: 360)
    }
}

/// One rendition's bytes drawn as a picture; a placeholder until they arrive or when they cannot be had.
private struct RenditionPicture: View {
    let documentId: String
    let renditionId: String
    let service: RenditionService?
    @State private var image: Image?

    var body: some View {
        Group {
            if let image { image.resizable().aspectRatio(contentMode: .fill) } else { Rectangle().fill(.quaternary) }
        }
        .task {
            guard let service, let data = try? await service.contentData(documentId: documentId, renditionId: renditionId) else { return }
            #if canImport(AppKit)
            if let loaded = NSImage(data: data) { image = Image(nsImage: loaded) }
            #else
            if let loaded = UIImage(data: data) { image = Image(uiImage: loaded) }
            #endif
        }
    }
}

#Preview("Chain strip, before the engine answers") {
    RenditionChainStripView(client: FicheroClient(libraryPath: nil), pageId: "page-1").padding().frame(width: 420)
}
