#if DEBUG
import SwiftUI

/// A lightweight, dependency-free wireframe of a `PaneList` — nested placeholder panes coloured by
/// kind — for eyeballing and SCREENSHOTTING workspace compositions in the Xcode canvas without
/// booting the app. This is the design-verification surface for the workspace spec
/// (panes-magnifiers-workspaces §"v2 workspace design"): each default renders as a mini window you
/// can inspect and capture. The SHIPPING renderer is `ContentView.paneComposition`; this only
/// mirrors its layout rule (top-level nodes = a horizontal row; a split arranges its children along
/// its axis) so the picture matches what the app draws. `#if DEBUG` — never ships in Release.
struct WorkspaceLayoutPreview: View {
    let title: String
    let list: PaneList
    var size = CGSize(width: 360, height: 220)

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.title3.weight(.semibold))
            HStack(spacing: 0) {
                sidebar
                row(list.nodes, axis: .horizontal)   // top level lays out as a horizontal row
            }
            .frame(width: size.width, height: size.height)
            .background(Color.gray.opacity(0.06))
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(.secondary.opacity(0.35)))
        }
    }

    // The always-present sidebar, with the chat region beneath it.
    private var sidebar: some View {
        VStack(spacing: 5) {
            ForEach(0..<4, id: \.self) { _ in
                Capsule().fill(.secondary.opacity(0.3)).frame(height: 4)
            }
            Spacer(minLength: 6)
            RoundedRectangle(cornerRadius: 4)
                .fill(.green.opacity(0.16))
                .overlay(Text("chat").font(.system(size: 7, design: .monospaced)).foregroundStyle(.green))
                .frame(height: 34)
        }
        .padding(6)
        .frame(width: 48)
        .overlay(Divider(), alignment: .trailing)
    }

    // AnyView because the recursion (row → node → row) can't ride an opaque `some View`.
    private func row(_ nodes: [PaneNode], axis: SplitAxis) -> AnyView {
        let panes = ForEach(Array(nodes.enumerated()), id: \.offset) { _, node in
            nodeView(node)
        }
        let stack = Group {
            if axis == .horizontal { HStack(spacing: 3) { panes } } else { VStack(spacing: 3) { panes } }
        }
        return AnyView(stack.padding(3))
    }

    private func nodeView(_ node: PaneNode) -> AnyView {
        switch node {
        case let .leaf(_, kind, _, config):
            return AnyView(paneBox(kind, config))
        case let .split(_, axis, children):
            return row(children, axis: axis)
        }
    }

    private func paneBox(_ kind: PaneKind, _ config: PaneConfig) -> some View {
        RoundedRectangle(cornerRadius: 5)
            .fill(color(kind).opacity(0.16))
            .overlay(RoundedRectangle(cornerRadius: 5).strokeBorder(color(kind).opacity(0.55)))
            .overlay(alignment: .topLeading) {
                Text(paneLabel(kind, config))
                    .font(.system(size: 8, weight: .medium, design: .monospaced))
                    .foregroundStyle(color(kind))
                    .padding(4)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func color(_ kind: PaneKind) -> Color {
        switch kind {
        case .library: .blue
        case .preview: .orange
        case .reading: .purple
        case .inspector: .gray
        case .chat: .green
        }
    }

    // Label shows the pane's kind AND its per-pane config, so "library · claims" and a word-box
    // preview read differently — the whole point of the composition model.
    private func paneLabel(_ kind: PaneKind, _ config: PaneConfig) -> String {
        switch kind {
        case .library:
            if let content = config.libraryContentKind { return content.capitalized }
            if let layout = config.libraryLayout { return "Library · \(layout)" }
            return "Library"
        case .preview:
            return config.previewWordBoxes == true ? "Word boxes" : "Source"
        case .reading: return "Reader"
        case .inspector: return "Inspector"
        case .chat: return "Chat"
        }
    }
}

#Preview("Workspaces — the six defaults") {
    ScrollView {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 380), spacing: 28)], alignment: .leading, spacing: 28) {
            ForEach(BuiltInWorkspaceLayout.allCases) { layout in
                WorkspaceLayoutPreview(title: "⌘⌥\(layout.defaultSlot)  \(layout.title)", list: layout.panes)
            }
        }
        .padding(28)
    }
    .frame(width: 860, height: 760)
}
#endif
