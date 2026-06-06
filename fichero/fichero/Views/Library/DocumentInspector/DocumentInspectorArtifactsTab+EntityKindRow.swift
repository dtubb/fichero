import FicheroAPIClient
import SwiftUI

// MARK: - EntityKindRow

/// One row inside an EntityKindBlock. The **name** is tappable —
/// clicking fires a scoped entity search (e.g. `person:"…"`) via the
/// `.ficheroEntitySearchRequested` notification, same path Keyword
/// lozenges use. Aliases / page reference / context render as plain
/// selectable text below for ⌘C. (#882)
struct EntityKindRow: View {
    let item: GroupedItem
    let kind: EntityKind
    var onNavigateToSource: ((String) -> Void)?
    var onClaimSelect: ((String, String?, String?, String?, Int?, Int?) -> Void)?

    @EnvironmentObject private var claimFocusState: ClaimFocusState
    @Environment(KGFocusState.self) private var kgFocusState
    @AppStorage("editor.fontSize") private var defaultFontSize: Double = 13
    @State private var claimForEditing: Components.Schemas.KnowledgeClaim?
    @State private var showDeleteConfirmation = false
    @State private var rowError: String?

    private var bodyTextFont: Font {
        .system(size: CGFloat(defaultFontSize))
    }

    private var secondaryTextFont: Font {
        .system(size: CGFloat(max(defaultFontSize - 1, 10)))
    }

    var body: some View {
        // Layout:
        //   line 1: [name button]  (aka alias1, alias2)  (p. label)   → arrow  [select claim]
        //   line 2: context  (when non-empty, non-redundant)
        // Name is its own Button so a tap doesn't have to compete with
        // textSelection on the rest of the row.
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Button(action: focusPrimaryClaim) {
                    Text(item.displayName)
                        .font(bodyTextFont)
                        .fontWeight(.medium)
                        .foregroundStyle(
                            claimFocusState.isClaimSelected(item.claimId) ? Color.accentColor : Color.primary
                        )
                }
                .buttonStyle(.plain)
                .help("Focus \"\(item.displayName)\"")
                .accessibilityHint("Focuses this \(kind.label.lowercased())")

                trailingText
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)

                if let confidence = item.confidence {
                    Text(String(format: "%.2f", confidence))
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.secondary.opacity(0.12))
                        .clipShape(Capsule())
                        .help("Claim confidence")
                }

                // Claim selection button for bidirectional sync
                if let onClaimSelect = onClaimSelect {
                    Button(action: {
                        focusPrimaryClaim()
                        onClaimSelect(
                            item.claimId,
                            item.sourceExcerpt,
                            item.sourceDocumentId,
                            item.sourcePageLabel,
                            nil,
                            nil
                        )
                    }, label: {
                        Image(systemName: claimFocusState.isClaimSelected(item.claimId) ? "star.fill" : "star")
                            .font(.system(size: 12))
                            .foregroundStyle(
                                claimFocusState.isClaimSelected(item.claimId) ? Color.accentColor : Color.secondary
                            )
                    })
                    .buttonStyle(.plain)
                    .help(
                        claimFocusState.isClaimSelected(item.claimId)
                            ? "Claim selected for highlighting"
                            : "Select claim for highlighting"
                    )
                }

                if let sourceId = item.sourceDocumentId,
                   let navigate = onNavigateToSource {
                    Button {
                        navigate(sourceId)
                    } label: {
                        Image(systemName: "arrow.right.circle")
                            .font(.body)
                            .foregroundStyle(Color.accentColor)
                    }
                    .buttonStyle(.plain)
                    .help("Go to source")
                }
            }

            if !item.context.isEmpty,
               item.context != item.displayName,
               !item.displayName.contains(item.context) {
                Text(item.context)
                    .font(bodyTextFont)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }

            // Verbatim source quote — only when distinct from both the
            // displayName and the curated context. Tap runs a library
            // search for the exact text (#893).
            if let excerpt = item.sourceExcerpt,
               !excerpt.isEmpty,
               excerpt != item.displayName,
               excerpt != item.context {
                Button {
                    NotificationCenter.default.post(
                        name: .ficheroEntitySearchRequested,
                        object: nil,
                        userInfo: ["name": excerpt]
                    )
                } label: {
                    Text("\u{201C}\(excerpt)\u{201D}")
                        .font(secondaryTextFont)
                        .italic()
                        .foregroundStyle(.secondary)
                        .lineLimit(3)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
                .help("Search the library for this quote")
            }

            // Additional SVO claims for the same entity (#1109).
            // Each renders as an indented context + excerpt pair, visually
            // subordinate to the primary claim above.
            if !item.extraClaims.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(item.extraClaims, id: \.claimId) { extra in
                        if !extra.context.isEmpty,
                           extra.context != item.displayName,
                           extra.context != item.context {
                            Text(extra.context)
                                .font(bodyTextFont)
                                .foregroundStyle(.secondary)
                                .textSelection(.enabled)
                        }
                        if let excerpt = extra.sourceExcerpt,
                           !excerpt.isEmpty,
                           excerpt != extra.context,
                           excerpt != item.displayName {
                            Button {
                                NotificationCenter.default.post(
                                    name: .ficheroEntitySearchRequested,
                                    object: nil,
                                    userInfo: ["name": excerpt]
                                )
                            } label: {
                                Text("\u{201C}\(excerpt)\u{201D}")
                                    .font(secondaryTextFont)
                                    .italic()
                                    .foregroundStyle(.secondary)
                                    .lineLimit(3)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                            .buttonStyle(.plain)
                            .help("Search the library for this quote")
                        }
                    }
                }
                .padding(.leading, 8)
            }

            if let rowError {
                Text(rowError)
                    .font(.caption2)
                    .foregroundStyle(.red)
            }
        }
        .padding(.vertical, 2)
        .contentShape(Rectangle())
        .onTapGesture {
            focusPrimaryClaim()
        }
        .contextMenu {
            Button("Edit claim…") {
                loadClaimForEditing()
            }
            Button("Delete claim…", role: .destructive) {
                showDeleteConfirmation = true
            }
        }
        .alert("Delete claim?", isPresented: $showDeleteConfirmation) {
            Button("Delete", role: .destructive) { deleteClaim() }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This removes the claim from the knowledge graph. Related entities stay in place.")
        }
        .sheet(isPresented: Binding(
            get: { claimForEditing != nil },
            set: { if !$0 { claimForEditing = nil } }
        )) {
            if let claimForEditing {
                EditClaimSheet(claim: claimForEditing) { updated in
                    self.claimForEditing = nil
                    NotificationCenter.default.post(
                        name: .ficheroClaimUpdated,
                        object: updated.id,
                        userInfo: ["claim": updated]
                    )
                }
            }
        }
    }

    private func focusPrimaryClaim() {
        kgFocusState.focusClaim(
            claimId: item.claimId,
            entityId: item.entityId,
            sourceDocumentId: item.sourceDocumentId,
            sourcePageLabel: item.sourcePageLabel
        )
    }

    /// Aliases + page reference rendered as one selectable text run,
    /// sitting beside the tappable name on line 1.
    private var trailingText: Text {
        var text = Text("")
            .font(secondaryTextFont)
            .foregroundStyle(.secondary)
        if !item.aliases.isEmpty {
            // swiftlint:disable:next shorthand_operator
            text = text
                + Text(" (aka " + item.aliases.joined(separator: ", ") + ")")
                .font(secondaryTextFont)
                .foregroundStyle(.secondary)
        }
        if let pageRef = pageReference {
            // swiftlint:disable:next shorthand_operator
            text = text
                + Text("  (\(pageRef))")
                .font(secondaryTextFont)
                .foregroundStyle(.secondary)
        }
        return text
    }

    /// Scholarly-style page reference: prefer the recorded label
    /// (e.g. "page 4", "folio 12r"); strip a leading "page " so we can
    /// abbreviate it to "p. 4". Returns nil when no label is available
    /// (don't fabricate a reference from nothing).
    private var pageReference: String? {
        guard let raw = item.sourcePageLabel?.trimmingCharacters(in: .whitespaces),
              !raw.isEmpty
        else { return nil }
        let lower = raw.lowercased()
        if lower.hasPrefix("page "), let numericPart = lower.split(separator: " ").last {
            return "p. \(numericPart)"
        }
        return raw
    }

    private func loadClaimForEditing() {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        rowError = nil
        Task {
            do {
                claimForEditing = try await library.entityService.getClaim(item.claimId)
            } catch {
                rowError = error.localizedDescription
            }
        }
    }

    private func deleteClaim() {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        rowError = nil
        Task {
            do {
                try await library.entityService.deleteClaim(item.claimId)
                NotificationCenter.default.post(name: .ficheroClaimDeleted, object: item.claimId)
            } catch {
                rowError = error.localizedDescription
            }
        }
    }
}
