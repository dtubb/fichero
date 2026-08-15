import SwiftUI

// MARK: - The equatable label core (2026-08-15 selection-stall fix)

/// The row's icon+name pair behind `Equatable`: every input is plain data,
/// so a selection change re-renders only the rows entering/leaving the
/// selection instead of every row in a 204-child folder (0.4–2.6s commits
/// in Daniel's 2026-08-14 night log; measured by SidebarSelectionPerfTests).
/// The rename field, lock badge and hover affordance stay OUTSIDE — they
/// carry bindings/closures that cannot be compared.
struct SidebarRowLabelCore: View, Equatable {
    /// The rename branch shows only the icon; the TextField follows outside.
    let iconOnly: Bool
    let name: String
    let icon: String
    let contentColor: Color
    let weight: Font.Weight?
    let isAlias: Bool
    let iconTint: Color
    let badgeSymbol: String?
    let badgeColor: Color?
    let childrenLoading: Bool
    let workflowRunning: Bool
    let documentProcessing: Bool
    let containerProgress: Double?
    let containerSummary: String?
    let isDefaultWorkflowFolder: Bool

    /// Excluded from == (only stored `let`s above are compared by the
    /// synthesized conformance? NO — synthesis compares ALL stored
    /// properties, and @State's box is reference-identical across updates,
    /// so it compares equal to itself; the explicit == below keeps the
    /// contract visible and @State out of it).
    @State private var isPulsing = false

    // nonisolated: Equatable's requirement is nonisolated, and View types
    // inherit MainActor under the macOS 26 SDK. Safe — only immutable `let`
    // value fields are read.
    nonisolated static func == (lhs: SidebarRowLabelCore, rhs: SidebarRowLabelCore) -> Bool {
        lhs.iconOnly == rhs.iconOnly
            && lhs.name == rhs.name
            && lhs.icon == rhs.icon
            && lhs.contentColor == rhs.contentColor
            && lhs.weight == rhs.weight
            && lhs.isAlias == rhs.isAlias
            && lhs.iconTint == rhs.iconTint
            && lhs.badgeSymbol == rhs.badgeSymbol
            && lhs.badgeColor == rhs.badgeColor
            && lhs.childrenLoading == rhs.childrenLoading
            && lhs.workflowRunning == rhs.workflowRunning
            && lhs.documentProcessing == rhs.documentProcessing
            && lhs.containerProgress == rhs.containerProgress
            && lhs.containerSummary == rhs.containerSummary
            && lhs.isDefaultWorkflowFolder == rhs.isDefaultWorkflowFolder
    }

    var body: some View {
        iconView
            .allowsHitTesting(false)
        if !iconOnly {
            Text(name)
                .lineLimit(1)
                // Stated explicitly, never inherited (#4371's mechanism
                // stands): the native emphasized source-list selection
                // forces white-and-bold. The COLOURS follow Finder
                // (Daniel, 2026-08-08): accent name when selected, white
                // over the solid accent fill while a drop targets this
                // row, primary otherwise.
                .foregroundStyle(contentColor)
                .fontWeight(weight)
                // Finder's alias grammar, both halves: the tiny arrow
                // badge on the icon (ingestBadge) AND an italic name —
                // the badge alone is invisible at sidebar sizes (Daniel,
                // 2026-08-04).
                .italic(isAlias)
                .allowsHitTesting(false)
            // `.allowsHitTesting(false)` on the Text (and Image) is
            // load-bearing for CLICKS (#713/#13; re-learned live
            // 2026-08-10): with it, name-presses fall through to the
            // row surface, where List selection + the UnifiedRows tap
            // fallback commit them. The morning's experiment that
            // removed it (chasing drag-by-name) put presses into a
            // path where NEITHER committed — "you can't click on a
            // name, you have to click on row". Reverted. Drag-by-name
            // remains a separate open investigation; do not chase it
            // by re-enabling hit-testing here.
            //
            // No inline double-tap-to-rename gesture: `.simultaneousGesture
            // (TapGesture(count: 2))` causes SwiftUI to hold every single
            // click for ~0.5s waiting for a potential second click, which
            // blocks List's native selection binding. Symptom: first click
            // does nothing; second click does nothing; double-click either
            // renames or nothing; later clicks finally select. #612.
            // Rename is still reachable via right-click → Rename (see
            // SidebarItemContextMenu).
        }
    }

    @ViewBuilder
    private var iconView: some View {
        if childrenLoading {
            ProgressView()
                .controlSize(.small)
                .scaleEffect(0.8)
                .frame(width: 16, alignment: .center)
                .tint(.accentColor)
                .accessibilityLabel("Loading items")
        } else if workflowRunning {
            ZStack {
                Circle()
                    .fill(Color.purple.opacity(isPulsing ? 0.4 : 0.15))
                    .frame(width: 20, height: 20)
                    .animation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true), value: isPulsing)
                ProgressView()
                    .controlSize(.small)
                    .scaleEffect(0.8)
                    // The List's tint is the selection FILL colour (#4371);
                    // restate the accent here so an in-flight row still spins
                    // in the user's accent rather than inheriting grey.
                    .tint(.accentColor)
            }
            .frame(width: 20, height: 20)
            .onAppear { isPulsing = true }
            .onDisappear { isPulsing = false }
        } else if documentProcessing {
            // Per-doc / folder spinner — REPLACES the icon while in flight.
            // Earlier version was a tiny corner overlay that the user
            // couldn't see at glance ("spinner is not on the right of the
            // folder, or replacing the icon"). Matches the workflow-row
            // spinner visual so users get one consistent "this is in
            // flight" signal across all sidebar rows. (#785)
            ProgressView()
                .controlSize(.small)
                .scaleEffect(0.8)
                .frame(width: 16, alignment: .center)
                // See above (#4371): the List tint is a fill colour, not an
                // accent, so progress restates its own.
                .tint(.accentColor)
        } else if let progress = containerProgress {
            // The container's CONTENTS are being worked on (#4417). A
            // determinate ring, deliberately unlike the leaf spinner: a
            // container is not being processed, and this is the one row where
            // a summary of the children makes sense.
            ProgressView(value: progress)
                .progressViewStyle(.circular)
                .controlSize(.small)
                .scaleEffect(0.8)
                .frame(width: 16, alignment: .center)
                .tint(.secondary)
                .help(containerSummary ?? "")
                .accessibilityLabel(containerSummary ?? "")
        } else if let badgeSymbol, let badgeColor {
            // #603: visible per-mode badges driven by metadata.ingest_mode
            // exposed in 8eb002cf. LINK shows a Finder-style alias arrow,
            // MOVE shows an arrow-into-box, COPY shows no badge (default).
            ZStack(alignment: .bottomTrailing) {
                // Defensive: empty icon strings spam the SF Symbols
                // log ("No symbol named '' found in system symbol set")
                // every render. Fall back to a generic doc icon when an
                // upstream factory forgets to set one. (#1015)
                Image(systemName: icon.isEmpty ? "doc" : icon)
                    .foregroundStyle(iconTint)
                // #4098: `.caption2` instead of `.system(size: 11)` — a
                // hardcoded point size does not track the user's text-size or
                // accessibility settings, which is a standing hard rule here.
                // caption2 is ~11pt at the default setting, so the intended
                // look is unchanged and now scales.
                //
                // The backing circle SIZES ITSELF from the symbol (padding +
                // `.background`) rather than a fixed 13pt frame, so it grows
                // with the glyph instead of letting it clip out at larger text
                // sizes. Deliberately not `@ScaledMetric`: a self-sizing
                // background needs no separate scale factor to keep in step,
                // and nothing else in this app uses that property yet.
                Image(systemName: badgeSymbol.isEmpty ? "questionmark.circle" : badgeSymbol)
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(.white, badgeColor)
                    .padding(1)
                    .background(Circle().fill(.background))
                    .offset(x: 4, y: 4)
            }
            .frame(width: 16, alignment: .center)
        } else if isDefaultWorkflowFolder {
            // Locked "Default Workflows" container/subfolders: a colored,
            // gear-badged folder icon so they read as system/default and
            // not user-editable (#11). Purple matches the workflow-running
            // accent used above, keeping the sidebar's workflow visual
            // language consistent. `.hierarchical` keeps the badge legible.
            Image(systemName: icon.isEmpty ? "folder.badge.gearshape" : icon)
                .symbolRenderingMode(.hierarchical)
                .foregroundStyle(.purple)
                .frame(width: 16, alignment: .center)
        } else {
            // Defensive empty-icon guard — see comment above. (#1015)
            Image(systemName: icon.isEmpty ? "doc" : icon)
                .foregroundStyle(iconTint)
                .frame(width: 16, alignment: .center)
        }
    }
}
