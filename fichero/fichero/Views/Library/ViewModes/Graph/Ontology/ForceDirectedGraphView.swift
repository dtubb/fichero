import FicheroAPIClient
import SwiftUI

// Force-directed graph over entities and their co-occurrence in claims.
//
// Nodes = entities (filtered by `hiddenKinds` upstream), edges = "appear
// together in the same claim" with weight = co-occurrence count. Layout
// is a Coulomb/Hooke simulation that converges in ~4 seconds and then
// freezes — no continued CPU after that. Click within ~18pt of a node to
// select it; the binding flows back to OntologyBrowser so the detail
// pane updates. (#902, partial #889)
// Force-directed physics short names (i, j, dx, dy, fx, fy) live in the
// drawing/interaction methods, which moved to ForceDirectedGraphView+Render.swift
// (#1703) — the identifier_name disable rides with them there.
struct ForceDirectedGraphView: View {
    let entities: [Components.Schemas.KnowledgeEntity]
    @Binding var selectedEntityId: String?
    @Environment(KGFocusState.self) var kgFocusState

    // Simulation state lives in a plain (non-observed) reference type so
    // the per-frame physics writes inside the Canvas render closure don't
    // count as "Modifying state during view update" (#1019, related #998).
    // TimelineView still drives the redraw cadence; `graphRevision` is the
    // observed @State that flips the empty-state branch when a load lands.
    @State var sim = GraphSimulation()
    @State private var graphRevision = 0
    @State private var isLoading = false
    @State private var loadError: String?

    // Viewport state. The simulation runs in fixed centered coordinates;
    // these transforms map sim-space → screen-space. Pinch updates
    // `scale`; drag updates `panOffset`. Gestures use the
    // `inProgress`-style accumulator pattern so updates remain smooth
    // and the final value persists when the gesture ends.
    @SceneStorage("ontology.graph.scale") private var scaleRaw: Double = 1.0
    @SceneStorage("ontology.graph.panX") private var panXRaw: Double = 0
    @SceneStorage("ontology.graph.panY") private var panYRaw: Double = 0
    var scale: CGFloat {
        get { CGFloat(scaleRaw) }
        nonmutating set { scaleRaw = Double(newValue) }
    }
    @State private var scaleAtGestureStart: CGFloat = 1.0
    var panOffset: CGSize {
        get { CGSize(width: panXRaw, height: panYRaw) }
        nonmutating set {
            panXRaw = Double(newValue.width)
            panYRaw = Double(newValue.height)
        }
    }
    @State private var panOffsetAtGestureStart: CGSize = .zero

    private let minScale: CGFloat = 0.4
    private let maxScale: CGFloat = 4.0
    private let neighborLimit = 30
    @State private var hops: Int = 1

    var body: some View {
        ZStack {
            // Read the observed revision so body re-evaluates when a load
            // completes — `sim` itself is a plain class and doesn't notify.
            // `let _ =` (not `_ =`) is required: a bare discard expression
            // isn't a View, but a discard *declaration* is a valid no-op
            // statement inside the @ViewBuilder.
            // swiftlint:disable:next redundant_discardable_let
            let _ = graphRevision
            Color(.controlBackgroundColor)
            if isLoading {
                ProgressView("Loading graph…")
            } else if let err = loadError {
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundStyle(.orange)
                    Text(err).font(.caption).foregroundStyle(.secondary)
                }
            } else if sim.nodes.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "circle.grid.3x3")
                        .font(.system(size: 28))
                        .foregroundStyle(.secondary)
                    Text("No graph data").font(.subheadline)
                    Text("Entities need shared claims to form edges")
                        .font(.caption).foregroundStyle(.secondary)
                }
            } else {
                graphCanvas
            }
        }
        .task(id: entitiesKey) { await load() }
    }

    private var graphCanvas: some View {
        GeometryReader { geo in
            ZStack(alignment: .topLeading) {
                TimelineView(.animation(minimumInterval: 1.0 / 60.0)) { timeline in
                    Canvas { ctx, size in
                        sim.step(in: size, now: timeline.date)
                        drawEdges(ctx: ctx)
                        drawNodes(ctx: ctx)
                    }
                }
                .contentShape(Rectangle())
                .gesture(
                    DragGesture(minimumDistance: 0)
                        .onChanged { value in
                            if value.translation == .zero {
                                panOffsetAtGestureStart = panOffset
                            }
                            panOffset = CGSize(
                                width: panOffsetAtGestureStart.width + value.translation.width,
                                height: panOffsetAtGestureStart.height + value.translation.height
                            )
                        }
                )
                .simultaneousGesture(
                    MagnificationGesture()
                        .onChanged { mag in
                            scale = min(max(scaleAtGestureStart * mag, minScale), maxScale)
                        }
                        .onEnded { _ in scaleAtGestureStart = scale }
                )
                .onTapGesture { location in
                    handleTap(at: location, in: geo.size)
                }

                legend
                    .padding(8)
                viewportControls
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .trailing)
            }
        }
    }

    // Small kind→color legend. Compact so it doesn't crowd the canvas
    // but enough to decode the dots without guessing.
    private var legend: some View {
        VStack(alignment: .leading, spacing: 3) {
            legendRow(kind: .person, label: "Person")
            legendRow(kind: .organization, label: "Org")
            legendRow(kind: .location, label: "Place")
            legendRow(kind: .event, label: "Event")
            legendRow(kind: .concept, label: "Concept")
            legendRow(kind: .other, label: "Other")
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 4)
        .background(
            RoundedRectangle(cornerRadius: 4)
                .fill(Color(.controlBackgroundColor).opacity(0.85))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.secondary.opacity(0.3), lineWidth: 0.5)
        )
    }

    private func legendRow(
        kind: Components.Schemas.EntityTypeOutput,
        label: String
    ) -> some View {
        HStack(spacing: 4) {
            Circle()
                .fill(color(for: kind))
                .frame(width: 7, height: 7)
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    // Compact zoom/reset controls + hop depth. Mirrors the PDF zoom toolbar style.
    private var viewportControls: some View {
        VStack(alignment: .trailing, spacing: 4) {
            HStack(spacing: 4) {
                Button {
                    let next = min(scale * 1.25, maxScale)
                    scale = next
                    scaleAtGestureStart = next
                } label: {
                    Image(systemName: "plus.magnifyingglass")
                }
                .buttonStyle(.plain)
                .help("Zoom in")
                .accessibilityLabel("Zoom In")
                Button {
                    let next = max(scale / 1.25, minScale)
                    scale = next
                    scaleAtGestureStart = next
                } label: {
                    Image(systemName: "minus.magnifyingglass")
                }
                .buttonStyle(.plain)
                .help("Zoom out")
                .accessibilityLabel("Zoom Out")
                Button {
                    scale = 1.0
                    scaleAtGestureStart = 1.0
                    panOffset = .zero
                    panOffsetAtGestureStart = .zero
                } label: {
                    Image(systemName: "arrow.up.left.and.arrow.down.right")
                }
                .buttonStyle(.plain)
                .help("Reset view")
                .accessibilityLabel("Reset View")
            }
            // Hop depth — how many hops from focus to show in the graph.
            HStack(spacing: 4) {
                Button {
                    if hops > 1 { hops -= 1 }
                } label: {
                    Image(systemName: "minus")
                        .font(.caption2)
                }
                .buttonStyle(.plain)
                .disabled(hops <= 1)
                .help("Fewer hops")
                .accessibilityLabel("Fewer Hops")
                Text(hops == 1 ? "1 hop" : "\(hops) hops")
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
                    .help("Neighborhood depth: how many relationship hops from the focus entity to show")
                Button {
                    if hops < 3 { hops += 1 }
                } label: {
                    Image(systemName: "plus")
                        .font(.caption2)
                }
                .buttonStyle(.plain)
                .disabled(hops >= 3)
                .help("More hops")
                .accessibilityLabel("More Hops")
            }
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 4)
        .background(
            RoundedRectangle(cornerRadius: 4)
                .fill(Color(.controlBackgroundColor).opacity(0.85))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.secondary.opacity(0.3), lineWidth: 0.5)
        )
    }

    /// Re-fetch the neighborhood whenever the focus entity changes OR
    /// the upstream entities list changes (i.e. user changed search /
    /// filter). The neighborhood endpoint is bounded + cached on the
    /// backend so this is cheap (sub-100ms on warm cache per #990).
    private var entitiesKey: String {
        let focus = selectedEntityId ?? entities.compactMap(\.id).first ?? ""
        let signature = entities.count
        return "\(focus):\(signature):\(hops)"
    }

    // MARK: - Data loading

    @MainActor
    private func load() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }

        // Focus selection: use the bound selectedEntityId; fall back to
        // the first entity in the filtered set so the view has something
        // to render when nothing is selected. With the focus-neighborhood
        // model the global "draw all entities in a circle" is gone —
        // graph mode shows ONE focus + its k-hop neighbors. (#976/#977)
        guard let focusId = selectedEntityId
                ?? entities.compactMap(\.id).first else {
            sim.nodes = []
            sim.edges = []
            graphRevision += 1
            return
        }
        guard let library = LibraryManager.shared.globalLibrary else {
            loadError = "No library"
            return
        }
        do {
            let response = try await library.entityService.fetchNeighborhood(
                entityId: focusId,
                hops: hops,
                limit: neighborLimit,
                rank: "edge_weight"
            )
            sim.rebuild(from: response)
            graphRevision += 1
        } catch {
            loadError = error.localizedDescription
        }
    }
}
