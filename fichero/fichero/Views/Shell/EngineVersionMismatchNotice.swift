import SwiftUI

/// The window banner for a stale embedded engine (Daniel, 2026-09-01:
/// "We need a launch engine version check, so that's flagged").
///
/// Deliberately modelled on `ExpandedSearchNotice` — same shape, same padding,
/// same dismiss affordance — rather than a new alert system. It differs in two
/// ways, both because it reports a defect rather than explaining a feature:
/// it is amber, and its dismissal is per-session (`AppState`), not persisted.
/// A build whose engine is stale must say so again the next time you launch it.
///
/// It never appears on its own: `AppState.engineVersionWarning` is non-nil only
/// when the engine that answered `/api/health` disagrees with the versions this
/// build stamped into its own `Info.plist` at embed time.
struct EngineVersionMismatchNotice: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        if let warning = appState.engineVersionWarning, !appState.engineVersionWarningDismissed {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(.orange)
                    .accessibilityHidden(true)

                VStack(alignment: .leading, spacing: 2) {
                    Text(Self.title)
                        .font(.subheadline)
                        .fontWeight(.semibold)
                    Text(warning)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 8)

                Button {
                    appState.engineVersionWarningDismissed = true
                } label: {
                    Image(systemName: "xmark")
                        .imageScale(.small)
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
                .help("Hide this warning until the next launch")
                .accessibilityLabel("Close")
                .accessibilityIdentifier("engineVersionMismatchNotice.close")
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(Color.orange.opacity(0.14))
            )
            .padding(.horizontal, 12)
            .padding(.top, 6)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("engineVersionMismatchNotice")
        }
    }

    nonisolated static let title = "Engine Version Mismatch"
}
