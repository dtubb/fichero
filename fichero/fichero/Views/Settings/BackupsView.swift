import FicheroAPIClient
import SwiftUI

// MARK: - Backups / Snapshots (#2087)

/// Settings → Backups: list a library's point-in-time snapshots, create a new
/// one, restore an older one (destructive — overwrites the live library), and
/// delete snapshots. All networking flows through `BackupStore` (generated
/// OpenAPI client only).
///
/// The store is passed in rather than read from `@Environment` so this view is
/// safe to host inside the Settings scene, which only injects `appState` +
/// `libraryManager` (any other env object traps on render — see #2051).
///
/// ponytail: there is no backend snapshot-*schedule* endpoint (the only periodic
/// snapshotter is the engine's internal task, not user-configurable over HTTP),
/// so this view deliberately omits any schedule control.
struct BackupsView: View {
    let store: BackupStore

    @State private var reason = ""
    /// Snapshot id awaiting restore confirmation (restore is destructive).
    @State private var pendingRestore: String?

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            content
            if let statusMessage = store.statusMessage {
                Divider()
                Text(statusMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .task { await store.load() }
        .alert(
            "Restore this backup?",
            isPresented: restoreAlertBinding,
            presenting: pendingRestore
        ) { id in
            Button("Restore", role: .destructive) {
                pendingRestore = nil
                Task { await store.restore(id) }
            }
            Button("Cancel", role: .cancel) { pendingRestore = nil }
        } message: { _ in
            Text("This overwrites the current library with the snapshot’s contents. "
                + "The backend keeps a backup of the replaced files, but any changes made "
                + "since the snapshot will be replaced.")
        }
    }

    // MARK: Header (create)

    private var header: some View {
        HStack(spacing: 8) {
            TextField("Reason (optional)", text: $reason)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 260)
            Button {
                let reasonToSend = reason
                reason = ""
                Task { await store.create(reason: reasonToSend) }
            } label: {
                if store.isCreating {
                    ProgressView().controlSize(.small)
                } else {
                    Label("Create Snapshot", systemImage: "plus.circle")
                }
            }
            .disabled(store.isCreating)
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.bar)
    }

    // MARK: Content (list)

    @ViewBuilder
    private var content: some View {
        if store.isLoading && store.snapshots.isEmpty {
            ProgressView("Loading backups…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = store.loadError, store.snapshots.isEmpty {
            ContentUnavailableView(
                "Couldn’t load backups",
                systemImage: "exclamationmark.triangle",
                description: Text(error)
            )
        } else if store.snapshots.isEmpty {
            ContentUnavailableView(
                "No backups yet",
                systemImage: "externaldrive.badge.timemachine",
                description: Text("Create a snapshot to capture this library’s current state.")
            )
        } else {
            List {
                ForEach(store.snapshots, id: \.snapshotPath) { snapshot in
                    row(snapshot)
                }
            }
        }
    }

    private func row(_ snapshot: Components.Schemas.LibrarySnapshot) -> some View {
        HStack(alignment: .center, spacing: 10) {
            Image(systemName: snapshot.isPinned == true ? "pin.fill" : "clock.arrow.circlepath")
                .foregroundStyle(snapshot.isPinned == true ? Color.accentColor : .secondary)
                .frame(width: 16)
            VStack(alignment: .leading, spacing: 2) {
                Text(title(snapshot))
                    .font(.callout)
                HStack(spacing: 8) {
                    Text(dateText(snapshot.createdAt))
                    Text("·")
                    Text(sizeText(snapshot))
                }
                .font(.caption2)
                .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            rowActions(snapshot)
        }
        .padding(.vertical, 2)
    }

    @ViewBuilder
    private func rowActions(_ snapshot: Components.Schemas.LibrarySnapshot) -> some View {
        let snapshotId = snapshot.id
        if store.restoringId == snapshotId || store.deletingId == snapshotId {
            ProgressView().controlSize(.small)
        } else {
            Button("Restore") {
                pendingRestore = snapshotId
            }
            .buttonStyle(.borderless)
            .disabled(snapshotId == nil || store.restoringId != nil || store.deletingId != nil)

            Button(role: .destructive) {
                if let snapshotId { Task { await store.delete(snapshotId) } }
            } label: {
                Image(systemName: "trash")
            }
            .buttonStyle(.borderless)
            .disabled(snapshotId == nil || store.restoringId != nil || store.deletingId != nil)
        }
    }

    // MARK: Helpers

    private var restoreAlertBinding: Binding<Bool> {
        Binding(
            get: { pendingRestore != nil },
            set: { if !$0 { pendingRestore = nil } }
        )
    }

    private func title(_ snapshot: Components.Schemas.LibrarySnapshot) -> String {
        if let reason = snapshot.reason, !reason.isEmpty { return reason }
        return "Manual snapshot"
    }

    private func dateText(_ date: Date?) -> String {
        guard let date else { return "Unknown date" }
        return date.formatted(date: .abbreviated, time: .shortened)
    }

    private func sizeText(_ snapshot: Components.Schemas.LibrarySnapshot) -> String {
        let bytes = Int64((snapshot.duckdbSizeBytes ?? 0) + (snapshot.lanceSizeBytes ?? 0))
        return ByteCountFormatter.string(fromByteCount: bytes, countStyle: .file)
    }
}

// MARK: - Settings host

/// Settings → Backups tab. Reads the backup store off the current library via
/// the `libraryManager` env object (the only stores the Settings scene injects),
/// so it never trips the #2051 missing-env-object trap.
struct BackupsSettingsTab: View {
    @Environment(LibraryManager.self) var libraryManager

    var body: some View {
        Group {
            if let library = libraryManager.globalLibrary {
                BackupsView(store: library.backupStore)
            } else {
                ContentUnavailableView(
                    "No library open",
                    systemImage: "externaldrive.badge.timemachine",
                    description: Text("Open a library to manage its backups.")
                )
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
