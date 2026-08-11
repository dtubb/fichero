import SwiftUI

// MARK: - Pane Filter Bar (shared filter/action strip for content panes)

/// Which edge of its pane a shared mini-toolbar strip sits on (#4362).
///
/// The component owns the edge-specific chrome — a top bar draws its hairline
/// separator BELOW itself (between bar and the content underneath, sitting
/// flush under the window toolbar), a bottom bar draws it ABOVE (between the
/// content's tail and the bar). Hosts pick an edge and supply content only.
enum MiniToolbarPlacement {
    case top
    case bottom

    /// The ONE placement decision for reader-style control bars (#4362).
    ///
    /// BOTTOM everywhere now (Daniel, 2026-08-11, supersedes the Mac-top
    /// choice): "bottom of library and reader is where we can filter, and
    /// where we can show which metadata or columns to show" — the Xcode
    /// console model. The TOP mini toolbar's future job is close/split
    /// controls, not filtering. Touch platforms already wanted bottom for
    /// reachability, so the platform fork is gone.
    static var preferredForReader: MiniToolbarPlacement {
        .bottom
    }
}

/// Mini-toolbar-height filter/action strip for sidebar / library / inspector
/// panes. It shares `MiniToolbarMetricPolicy` so filter rows line up with the
/// reader, preview, and inspector mini-toolbars on macOS, iPad, and iPhone.
struct PaneFilterBar<Content: View>: View {
    static var height: CGFloat {
        MiniToolbar<EmptyView, EmptyView>.standardHeight
    }

    let placement: MiniToolbarPlacement
    let content: Content

    init(
        placement: MiniToolbarPlacement = .bottom,
        @ViewBuilder content: () -> Content
    ) {
        self.placement = placement
        self.content = content()
    }

    var body: some View {
        VStack(spacing: 0) {
            if placement == .bottom {
                Divider()
            }
            #if os(visionOS)
            HStack(spacing: 6) {
                content
            }
            .padding(.horizontal, 8)
            .frame(height: Self.height)
            .frame(maxWidth: .infinity)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
            #else
            GlassEffectContainer {
                HStack(spacing: 6) {
                    content
                }
                .padding(.horizontal, 8)
                .frame(height: Self.height)
                .frame(maxWidth: .infinity)
                .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 8))
            }
            #endif
            if placement == .top {
                Divider()
            }
        }
    }
}
