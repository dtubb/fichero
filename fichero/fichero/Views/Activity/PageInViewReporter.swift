import SwiftUI

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
