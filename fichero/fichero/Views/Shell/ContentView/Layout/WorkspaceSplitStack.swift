import SwiftUI

/// A RESIZABLE stack for an applied workspace's splits. The applied-workspace renderer
/// (`paneListRow`/`paneSplitView`) used plain HStack/VStack with fixed flex frames, so the panes
/// couldn't be resized (CD 2026-09-16: "I can't resize them"). This lays 1–3 child panes out along
/// `axis` with a draggable `ResizableDivider` between each pair; the leading extents persist per
/// split position via `@SceneStorage` keyed by `storageKey`, and the last child flexes to fill.
///
/// SplitAxis.horizontal ⇒ columns side by side (resize WIDTH); .vertical ⇒ rows stacked (resize
/// HEIGHT). Four-plus children (rare) put the extras in the flexing tail.
struct WorkspaceSplitStack: View {
    let axis: SplitAxis
    let children: [AnyView]

    @SceneStorage private var extent0: Double
    @SceneStorage private var extent1: Double

    init(axis: SplitAxis, storageKey: String, children: [AnyView]) {
        self.axis = axis
        self.children = children
        let fallback: Double = axis == .horizontal ? 360 : 300
        self._extent0 = SceneStorage(wrappedValue: fallback, "wsplit.\(storageKey).0")
        self._extent1 = SceneStorage(wrappedValue: fallback, "wsplit.\(storageKey).1")
    }

    var body: some View {
        Group {
            if axis == .horizontal {
                HStack(spacing: 0) { content }
            } else {
                VStack(spacing: 0) { content }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    @ViewBuilder private var content: some View {
        switch children.count {
        case 0:
            EmptyView()
        case 1:
            children[0].frame(maxWidth: .infinity, maxHeight: .infinity)
        case 2:
            sized(children[0], $extent0)
            divider($extent0)
            children[1].frame(maxWidth: .infinity, maxHeight: .infinity)
        default:
            sized(children[0], $extent0)
            divider($extent0)
            sized(children[1], $extent1)
            divider($extent1)
            // Everything from index 2 on shares the flexing tail (usually just one pane).
            ForEach(Array(children.dropFirst(2).enumerated()), id: \.offset) { _, child in
                child.frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
    }

    @ViewBuilder private func sized(_ view: AnyView, _ extent: Binding<Double>) -> some View {
        if axis == .horizontal {
            view.frame(width: extent.wrappedValue).frame(maxHeight: .infinity)
        } else {
            view.frame(height: extent.wrappedValue).frame(maxWidth: .infinity)
        }
    }

    private func divider(_ extent: Binding<Double>) -> some View {
        ResizableDivider(
            width: extent,
            minWidth: axis == .horizontal ? 220 : 140,
            maxWidth: axis == .horizontal ? 1400 : 1100,
            edge: .leading,   // the panel is on the leading side; drag toward the trailing to grow it
            axis: axis == .horizontal ? .horizontal : .vertical
        )
    }
}
