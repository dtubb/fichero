import SwiftUI

/// Sidebar content for the Mind Palace mode: the rooms list (CRUD via
/// `/rooms`), a stacks disclosure for the selected room, and the 3D/2D toggle.
/// Coordinates with the main canvas (`MindPalaceContainer`) through
/// `MindPalaceState.shared`.
struct RoomListView: View {
    @ObservedObject private var state = MindPalaceState.shared

    @State private var rooms: [MindPalaceRoom] = []
    @State private var stacks: [MindPalaceStack] = []
    @State private var isLoading = false
    @State private var loadError: String?
    @State private var showNewRoomPrompt = false
    @State private var newRoomName = ""

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()

            if let loadError {
                ContentUnavailableView(
                    "Couldn't Load Rooms",
                    systemImage: "exclamationmark.triangle",
                    description: Text(loadError)
                )
            } else {
                List(selection: roomSelection) {
                    // Phase 3 (#1297 follow-up): pinned pseudo-room that
                    // loads the whole-library projection (documents +
                    // entities + links) instead of a stored room's nodes.
                    Section("Library") {
                        Label("Whole Library", systemImage: "globe")
                            .tag(wholeLibraryRoomId)
                            .help("Spatial view of every document and entity in this library.")
                    }

                    Section("Rooms") {
                        ForEach(rooms) { room in
                            Label(room.name, systemImage: "cube.transparent")
                                .tag(room.id)
                                .contextMenu {
                                    Button("Delete Room", role: .destructive) {
                                        Task { await deleteRoom(room) }
                                    }
                                }
                        }
                    }

                    if !stacks.isEmpty {
                        Section("Stacks") {
                            ForEach(stacks) { stack in
                                Label(
                                    stack.name ?? "Stack",
                                    systemImage: "square.stack.3d.up"
                                )
                                .badge(stack.nodeIds.count)
                            }
                        }
                    }
                }
                .listStyle(.sidebar)
            }

            Divider()
            renderModeToggle
        }
        .background(Color(platformColor: .windowBackgroundColor))
        .task { await loadRooms() }
        .onChange(of: state.selectedRoomId) { _, _ in
            Task { await loadStacks() }
        }
        .alert("New Room", isPresented: $showNewRoomPrompt) {
            TextField("Room name", text: $newRoomName)
            Button("Cancel", role: .cancel) { newRoomName = "" }
            Button("Create") { Task { await createRoom() } }
        }
    }

    /// Binding that mirrors the selected room into shared state.
    private var roomSelection: Binding<String?> {
        Binding(
            get: { state.selectedRoomId },
            set: { state.selectRoom($0) }
        )
    }

    private var header: some View {
        HStack {
            Text("Mind Palace").font(.headline).foregroundStyle(.primary)
            Spacer()
            if isLoading { ProgressView().controlSize(.small) }
            Button {
                newRoomName = ""
                showNewRoomPrompt = true
            } label: {
                Image(systemName: "plus")
            }
            .buttonStyle(.borderless)
            .help("New room")
        }
        .padding(.horizontal, 12)
        .frame(height: 44)
    }

    private var renderModeToggle: some View {
        Picker("View", selection: $state.renderMode) {
            ForEach(SpatialRenderMode.allCases, id: \.self) { mode in
                Label(mode.label, systemImage: mode.icon).tag(mode)
            }
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .padding(8)
    }

    // MARK: - Data

    private func loadRooms() async {
        guard let service = activeMindPalaceService() else { return }
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            rooms = try await service.listRooms()
            if state.selectedRoomId == nil, let first = rooms.first {
                state.selectRoom(first.id)
            }
            await loadStacks()
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func loadStacks() async {
        guard let roomId = state.selectedRoomId, let service = activeMindPalaceService() else {
            stacks = []
            return
        }
        stacks = (try? await service.listStacks(roomId: roomId)) ?? []
    }

    private func createRoom() async {
        let name = newRoomName.trimmingCharacters(in: .whitespacesAndNewlines)
        newRoomName = ""
        guard !name.isEmpty, let service = activeMindPalaceService() else { return }
        do {
            let room = try await service.createRoom(name: name)
            await loadRooms()
            if let room { state.selectRoom(room.id) }
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func deleteRoom(_ room: MindPalaceRoom) async {
        guard let service = activeMindPalaceService() else { return }
        do {
            try await service.deleteRoom(roomId: room.id)
            if state.selectedRoomId == room.id { state.selectRoom(nil) }
            await loadRooms()
        } catch {
            loadError = error.localizedDescription
        }
    }
}
