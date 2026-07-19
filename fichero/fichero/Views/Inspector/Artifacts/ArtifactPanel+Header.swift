import SwiftUI

extension ArtifactPanel {
    // MARK: - Header

    @ViewBuilder
    var header: some View {
        HStack(spacing: 8) {
            Image(systemName: iconName)
                .foregroundStyle(.secondary)
                .font(.system(size: 13))
            Text(title)
                .font(.subheadline)
                .fontWeight(.medium)
            if let subtitle = subtitle {
                Text("·")
                    .foregroundStyle(.tertiary)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            if isAIUnreviewed {
                // Consistent with the artifact-row badge (#3325 step 4): AI
                // output that a human hasn't vetted is flagged, not passed off
                // as fact (#2151/#2152).
                Image(systemName: "sparkles")
                    .font(.system(size: 11))
                    .foregroundStyle(.purple.opacity(0.7))
                    .help("AI-generated · not yet reviewed")
                    .accessibilityLabel("AI-generated, not reviewed")
            }
            Spacer()
            // Save indicator (subtle): spinner while saving, green check when
            // idle and saved. No mode toggle — V2 panels are always editable
            // (user feedback 2026-04-27 after preferring V1's always-on
            // behavior). Just type. Auto-saves on the debounce.
            if onSave != nil {
                if saver.isSaving {
                    ProgressView().controlSize(.small)
                } else if saveError == nil {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 11))
                        .foregroundStyle(.green.opacity(0.7))
                        .help("Saved")
                }
            }
            if onDelete != nil {
                Button {
                    confirmingDelete = true
                } label: {
                    Image(systemName: "trash")
                        .font(.system(size: 11))
                }
                .buttonStyle(.borderless)
                .foregroundStyle(.secondary)
                .accessibilityLabel("Delete artifact")
                .help("Delete this artifact")
            }
        }
    }

    var deleteMessage: String {
        switch kind {
        case .artifact(let artifact):
            return "\(title) from \(artifact.provider ?? "unknown") will be removed."
        case .pageContent:
            return "Page content will be cleared."
        }
    }
}
