import SwiftUI

/// A section of an opened run that is closed until opened, and stays as the person left it
/// (`activity.window.open-a-run`: Details and Log are disclosures, closed by default and remembered).
struct ActivityDetailsDisclosure<Content: View>: View {
    let title: String
    /// Said beside the title while it is closed or open ("3 problems").
    var detail: String?
    @AppStorage private var expanded: Bool
    private let content: Content

    /// `key` is the UserDefaults key the open/closed choice is kept under.
    init(_ title: String, detail: String? = nil, key: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.detail = detail
        _expanded = AppStorage(wrappedValue: false, key)
        self.content = content()
    }

    var body: some View {
        DisclosureGroup(isExpanded: $expanded) {
            content.padding(.top, 4)
        } label: {
            HStack(spacing: 6) {
                Text(title).font(.headline)
                if let detail { Text(detail).font(.callout).foregroundStyle(.orange) }
            }
        }
    }
}

#Preview("Closed until opened") {
    ActivityDetailsDisclosure("Details", key: "activity.preview.details") {
        Text("Started 14:02 · 4 min · peak memory 3.1 GB")
    }
    .padding()
    .frame(width: 360)
}
