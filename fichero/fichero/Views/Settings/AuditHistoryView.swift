import FicheroAPIClient
import SwiftUI

// MARK: - Global Audit / History Viewer (#2085)

/// A global "who changed what" viewer over the action-registry audit log.
///
/// Lifts the per-entity `EntityDetailView+Audit` pattern to a library-wide list:
/// a native `List` of audit rows on the left, a detail pane (actor, target,
/// change summary) on the right, and an Undo button for reversible rows. All
/// networking flows through `AuditStore` (generated OpenAPI client only).
///
/// The store is passed in rather than read from `@Environment` so this view is
/// safe to host inside the Settings scene, which only injects `appState` +
/// `libraryManager` (any other env object traps on render — see #2051).
struct AuditHistoryView: View {
    let store: AuditStore
    @State private var selection: String?

    var body: some View {
        HStack(spacing: 0) {
            listPane
                .frame(width: 300)
            Divider()
            detailPane
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .task { await store.load() }
    }

    // MARK: List pane

    @ViewBuilder
    private var listPane: some View {
        if store.isLoading && store.entries.isEmpty {
            ProgressView("Loading history…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = store.loadError, store.entries.isEmpty {
            ContentUnavailableView(
                "Couldn’t load history",
                systemImage: "exclamationmark.triangle",
                description: Text(error)
            )
        } else if store.entries.isEmpty {
            ContentUnavailableView(
                "No history yet",
                systemImage: "clock",
                description: Text("Changes you make will appear here.")
            )
        } else {
            List(selection: $selection) {
                ForEach(store.entries, id: \.id) { entry in
                    row(entry).tag(entry.id)
                }
            }
        }
    }

    private func row(_ entry: Components.Schemas.AuditLogEntry) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: icon(for: entry))
                .foregroundStyle(tint(for: entry))
                .frame(width: 16)
            VStack(alignment: .leading, spacing: 2) {
                Text(entry.actionName)
                    .font(.callout)
                    .strikethrough(entry.undone, color: .secondary)
                relativeText(entry.createdAt)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            Text(entry.actor)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 2)
    }

    // MARK: Detail pane

    @ViewBuilder
    private var detailPane: some View {
        if let selection, let entry = store.entries.first(where: { $0.id == selection }) {
            detail(entry)
        } else {
            ContentUnavailableView(
                "Select a change",
                systemImage: "clock.arrow.circlepath",
                description: Text("Pick a row to see what changed and who changed it.")
            )
        }
    }

    private func detail(_ entry: Components.Schemas.AuditLogEntry) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                detailHeader(entry)
                Divider()
                metadataRows(entry)
                targetsSection(entry)
                if let statusMessage = store.statusMessage {
                    Text(statusMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
        }
    }

    private func detailHeader(_ entry: Components.Schemas.AuditLogEntry) -> some View {
        HStack(spacing: 10) {
            Image(systemName: icon(for: entry))
                .font(.title2)
                .foregroundStyle(tint(for: entry))
            VStack(alignment: .leading, spacing: 2) {
                Text(entry.actionName)
                    .font(.headline)
                relativeText(entry.createdAt)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if store.canUndo(entry) {
                Button {
                    Task { await store.undo(entry.id) }
                } label: {
                    if store.undoingId == entry.id {
                        ProgressView().controlSize(.small)
                    } else {
                        Label("Undo", systemImage: "arrow.uturn.backward")
                    }
                }
                .disabled(store.undoingId != nil)
            }
        }
    }

    @ViewBuilder
    private func metadataRows(_ entry: Components.Schemas.AuditLogEntry) -> some View {
        LabeledContent("Actor", value: entry.actor)
        LabeledContent("Action", value: entry.actionName)
        LabeledContent("When", value: entry.createdAt)
        if entry.undone {
            LabeledContent("Status") {
                Label("Undone", systemImage: "arrow.uturn.backward.circle")
                    .foregroundStyle(.secondary)
            }
        }
        if let inverseOf = entry.inverseOf, !inverseOf.isEmpty {
            LabeledContent("Reverses", value: inverseOf)
        }
    }

    @ViewBuilder
    private func targetsSection(_ entry: Components.Schemas.AuditLogEntry) -> some View {
        if !entry.targetIds.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text("Targets")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                ForEach(entry.targetIds, id: \.self) { target in
                    Text(target)
                        .font(.caption)
                        .textSelection(.enabled)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    // MARK: Styling helpers

    /// Domain prefix of the action name, e.g. `"entity"` from `"entity.merge"`.
    private func domain(of entry: Components.Schemas.AuditLogEntry) -> String {
        entry.actionName.split(separator: ".").first.map(String.init) ?? entry.actionName
    }

    private func icon(for entry: Components.Schemas.AuditLogEntry) -> String {
        if entry.undone { return "arrow.uturn.backward.circle" }
        switch domain(of: entry) {
        case "entity": return "person.text.rectangle"
        case "claim": return "text.quote"
        case "document": return "doc"
        case "note": return "note.text"
        case "annotation": return "highlighter"
        case "action": return "bolt"
        default: return "clock.arrow.circlepath"
        }
    }

    private func tint(for entry: Components.Schemas.AuditLogEntry) -> Color {
        entry.undone ? .gray : .accentColor
    }

    /// Best-effort relative time from the backend's ISO-8601 `created_at`,
    /// falling back to the raw string if it can't be parsed.
    private func relativeText(_ iso: String) -> Text {
        if let date = Self.fractionalFormatter.date(from: iso)
            ?? Self.plainFormatter.date(from: iso) {
            return Text(date, style: .relative)
        }
        return Text(iso)
    }

    private static let fractionalFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static let plainFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()
}

// MARK: - Settings host

/// Settings → History tab. Reads the audit store off the current library via the
/// `libraryManager` env object (the only stores the Settings scene injects), so
/// it never trips the #2051 missing-env-object trap.
struct AuditHistorySettingsTab: View {
    @Environment(LibraryManager.self) var libraryManager

    var body: some View {
        Group {
            if let library = libraryManager.globalLibrary {
                AuditHistoryView(store: library.auditStore)
            } else {
                ContentUnavailableView(
                    "No library open",
                    systemImage: "clock",
                    description: Text("Open a library to see its change history.")
                )
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
