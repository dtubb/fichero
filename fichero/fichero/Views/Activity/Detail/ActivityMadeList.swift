import SwiftUI

/// What a finished workflow run made: each artifact's name and type, opening its document, then "and N more". The list
/// only; taking a run back waits for `safety/run-take-back.md`.
struct ActivityMadeList: View {
    let made: ActivityDetails.Made
    let open: (_ documentId: String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("What this run made").font(.headline)
            ForEach(made.items) { item in
                Button { open(item.documentId) } label: {
                    Text(item.name == item.type ? item.name : "\(item.name) · \(item.type)")
                }
                #if os(macOS)
                .buttonStyle(.link)
                #else
                .buttonStyle(.borderless)  // .link is macOS only (#6390)
                #endif
                .font(.callout)
                .accessibilityIdentifier("activity.details.made.item")
            }
            if made.more > 0 {
                Text("and \(made.more) more").font(.callout).foregroundStyle(.secondary)
            }
        }
        .accessibilityIdentifier("activity.details.made")
    }
}

#Preview("What a run made") {
    ActivityMadeList(
        made: ActivityDetails.Made(
            items: [
                ActivityDetails.MadeItem(id: "a1", name: "transcribe", type: "transcription", documentId: "doc-1"),
                ActivityDetails.MadeItem(id: "a2", name: "names", type: "names", documentId: "doc-2")
            ],
            more: 3),
        open: { _ in }
    )
    .padding()
    .frame(width: 320)
}
