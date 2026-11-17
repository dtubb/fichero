import SwiftUI

/// The page in view, as the engine is told it (`activity.foreground.rank-on-the-row-and-the-pick`, #6442; Step 1.14):
/// the page the Preview shows first, then the page before it, then the five after, because people page forward.
enum PageInView {
    struct Item: Equatable, Hashable, Sendable {
        let subject: String
        let rank: Int
    }

    /// How long a selection settles before it is reported, and how often the report is sent again while it stands.
    static let settle: Duration = .milliseconds(300)
    static let heartbeat: Duration = .seconds(30)

    /// The page shown (rank 0), the one before (1), and the five after (2…6), from the order its folder lists them; the
    /// page alone when it is not in that order; nothing when nothing is shown.
    static func items(shown: String?, in order: [String]) -> [Item] {
        guard let shown else { return [] }
        guard let index = order.firstIndex(of: shown) else { return [Item(subject: shown, rank: 0)] }
        var items = [Item(subject: shown, rank: 0)]
        if index > 0 { items.append(Item(subject: order[index - 1], rank: 1)) }
        for (offset, id) in order[(index + 1)...].prefix(5).enumerated() {
            items.append(Item(subject: id, rank: 2 + offset))
        }
        return items
    }
}

/// One window's reporter: after the selection settles it tells its project's engine what is in view, and again every
/// thirty seconds while it stands; a new page replaces the set (the engine drops a window that stops reporting after 90
/// s).
struct PageInViewReporter: ViewModifier {
    let service: ActivityService?
    let items: [PageInView.Item]
    @State private var client = UUID().uuidString

    func body(content: Content) -> some View {
        content.task(id: items) {
            guard let service else { return }
            try? await Task.sleep(for: PageInView.settle)
            while !Task.isCancelled {
                try? await service.setForeground(client: client, items: items)
                try? await Task.sleep(for: PageInView.heartbeat)
            }
        }
    }
}
