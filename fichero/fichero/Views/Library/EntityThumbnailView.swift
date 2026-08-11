import FicheroAPIClient
import SwiftUI

// MARK: - Entity Thumbnail (split from LibraryThumbnailViews for the
// 400-line file ratchet, 2026-08-09)

struct EntityThumbnailKindStyle {
    let label: String
    let systemName: String
    let tint: Color
}

struct EntityThumbnailView: View {
    let entity: Components.Schemas.KnowledgeEntity
    let isSelected: Bool
    let secondaryText: String
    let kindStyle: EntityThumbnailKindStyle
    var selectedTint: Color = .accentColor
    var scale: CGFloat = 1.0

    #if os(macOS)
    @Environment(\.controlActiveState) private var controlActiveState
    #endif

    /// #1840: de-emphasize the selection tint to gray when the window isn't key
    /// (matching List/NSTableView). macOS-only; iOS keeps the tint.
    private var effectiveSelectedTint: Color {
        // V3 (2026-08-09): NO controlActiveState re-gate — selectedTint is
        // selectionTint from the pane-focus test every row uses; a second
        // key-window gate made a tile grey while the equivalent list row
        // stayed accent. One focus test everywhere.
        selectedTint
    }

    init(
        entity: Components.Schemas.KnowledgeEntity,
        isSelected: Bool,
        secondaryText: String,
        kindStyle: EntityThumbnailKindStyle,
        selectedTint: Color = .accentColor,
        scale: CGFloat = 1.0
    ) {
        self.entity = entity
        self.isSelected = isSelected
        self.secondaryText = secondaryText
        self.kindStyle = kindStyle
        self.selectedTint = selectedTint
        self.scale = scale
    }

    var body: some View {
        VStack(spacing: 6) {
            ZStack {
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color(.windowBackgroundColor))
                    .aspectRatio(3.0 / 4.0, contentMode: .fit)

                VStack(spacing: 10) {
                    ZStack {
                        Circle()
                            .fill(kindStyle.tint.opacity(0.16))
                            .frame(width: 50 * scale, height: 50 * scale)

                        Image(systemName: kindStyle.systemName)
                            .font(.system(size: 24 * scale, weight: .semibold))
                            .foregroundStyle(kindStyle.tint)
                    }

                    Text(kindStyle.label.uppercased())
                        .font(.system(size: 9 * scale, weight: .semibold))
                        .tracking(0.6)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 8)
                }
                .padding(12)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .clipShape(RoundedRectangle(cornerRadius: 6))
            // Finder's icon-view selection (Daniel's screenshot, 2026-08-08,
            // #4563): grey backdrop behind the ICON — see
            // DocumentThumbnailView.
            .padding(3)
            .background(
                RoundedRectangle(cornerRadius: LibrarySelectionStyle.cornerRadius)
                    .fill(isSelected ? LibrarySelectionStyle.fill : Color.clear)
            )

            VStack(spacing: 2) {
                Text(entity.canonicalName)
                    .font(.caption)
                    // Reservation OUTSIDE the pill (2026-08-09) — same fix as
                    // DocumentThumbnailView: the pill must hug the text, not
                    // the reserved empty second line.
                    .lineLimit(2)
                    .truncationMode(.tail)
                    .multilineTextAlignment(.center)
                    // Finder's name pill — accent + white whenever selected;
                    // see DocumentThumbnailView.
                    .foregroundColor(isSelected ? .white : .primary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(
                        RoundedRectangle(cornerRadius: LibrarySelectionStyle.cornerRadius)
                            .fill(isSelected ? Color.accentColor : Color.clear)
                    )
                    .frame(height: 30, alignment: .top)

                Text(secondaryText)
                    .font(.caption2)
                    .lineLimit(2, reservesSpace: true)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(width: 100 * scale)
        .padding(6)
        // No whole-tile wash: Finder highlights the icon and the name pill,
        // never the tile (replaces the #4191 grey tile fill).
        // VoiceOver: one coherent tile, same shape as document tiles (#4160).
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(entity.canonicalName), \(kindStyle.label)")
        .accessibilityValue(secondaryText)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
        .accessibilityIdentifier("libraryEntityTile.\(entity.stableInspectorId)")
    }
}
