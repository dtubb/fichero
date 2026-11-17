import SwiftUI

/// The Pass menu on the Source's and the Reader's heads (#6670, `source.editor.pass-shown-is-picked`): which of
/// the page's passes (a Kraken run, a model's read, an import) the page shows. Picking one shows its segments at
/// once without promoting it; promoting stays the way to set the default. Shown only when there is a choice.
struct PassPickerMenu: View {
    let documentId: String?

    @Environment(SegmentService.self) private var segmentService: SegmentService?

    var body: some View {
        if let documentId, let segmentService {
            let store = SegmentStore.shared(for: segmentService)
            let passes = store.passes(documentId: documentId)
            if PassChoice.offersChoice(passes) {
                let picked = store.pickedPassByDocument[documentId]
                Menu {
                    ForEach(PassChoice.items(passes: passes, pickedId: picked)) { item in
                        Button { store.pickPass(item.id, documentId: documentId) } label: {
                            if item.isShown {
                                Label(item.title, systemImage: "checkmark")
                            } else {
                                Text(item.title)
                            }
                        }
                    }
                    if picked != nil {
                        Divider()
                        Button("Show the Promoted Pass") { store.pickPass(nil, documentId: documentId) }
                    }
                } label: {
                    // Named, as the renditions menu names its rendition: an icon alone was missed (owner 2026-11-17).
                    let title = PassChoice.shownTitle(passes: passes, pickedId: picked) ?? "Pass"
                    Label(title, systemImage: "square.stack.3d.up")
                        .labelStyle(.titleAndIcon)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .paneBarMenuStyle()
                .fixedSize()
                .help("Which pass this page shows: a run's segments, without promoting it")
                .accessibilityLabel("Pass shown")
                .accessibilityIdentifier("paneHeadPassMenu")
            }
        }
    }
}
