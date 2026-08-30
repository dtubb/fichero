import SwiftUI

/// The capability bar — verbs that can act on what is selected, above the
/// content (2026-08-28).
///
/// Fichero ships ~90 tools and ~50 workflows and showed none of them outside
/// the node editor, so nothing ever told a user what the app could do to the
/// page in front of them. This bar is a projection of the selection through
/// each workflow's server-declared `accepted_inputs`: select a page and the
/// vision verbs appear, select a passage and only the verbs taking text do.
/// The decision itself lives in `WorkflowBarPolicy`, with no SwiftUI in it, so
/// it is tested without a window.
///
/// Deliberately NOT a second window-spanning toolbar row: it acts on the
/// CONTENT selection, and a full-width row would sit above the sidebar and
/// inspector too, claiming a scope it does not have.
///
/// Items follow the NATIVE toolbar grammar (Daniel, 2026-08-28): a larger
/// centred glyph with a small label beneath it, not a glyph with the label
/// beside it. Vertical stacking is what lets a dozen verbs read as a toolbar
/// rather than as a sentence, and it is the shape of both Fichero's own
/// Library/Preview/Reader/Chat items and Preview's markup bar.
struct WorkflowBar: View {
    let workflows: [WorkflowSidebarItem]
    let target: WorkflowBarPolicy.Target
    /// Folder order and glyphs as the engine describes them; empty falls
    /// back to the built-in route.
    var folders: [String: WorkflowBarPolicy.FolderPresentation] = [:]
    /// Models a step can be pinned to, as configured in Settings.
    var modelChoices: [WorkflowBarModelChoice] = []
    /// Labels under the glyphs. Off gives a dense icon rail; on names every
    /// verb for someone still learning the vocabulary (Daniel, 2026-08-28).
    var showsLabels: Bool = true
    /// The chain being assembled. Clicking a verb APPENDS to this rather
    /// than running (Daniel, 2026-08-28: "it shouldn't run right away, it
    /// should construct the chain") — the run is one deliberate press of ▶,
    /// which is what makes a paid multi-step job over a folder safe to build.
    @Binding var staged: [StagedWorkflowStep]
    /// Runs the staged chain, in order.
    let onRunChain: () -> Void
    /// True while the chain is running — ▶ becomes a progress affordance.
    var isRunning: Bool = false
    /// Index of the step currently executing, so the rail shows WHERE the
    /// chain is rather than only that it is busy.
    var runningStepIndex: Int?
    /// Opens what a step produced — its run trace, or the document it
    /// wrote. nil disables the gesture rather than pretending.
    var onOpenStep: ((StagedWorkflowStep) -> Void)?
    /// Upper bound on what running this chain would cost. nil = unpriced,
    /// which is shown as such rather than as free.
    var costCeiling: Double?
    /// Every registered tool, for the Tools browser.
    var tools: [ToolInfo] = []
    /// Opens a workflow in the node editor (the popovers' ⓘ). nil hides it.
    var onInspectWorkflow: ((WorkflowSidebarItem) -> Void)?
    /// WHAT the run acts on, named (Daniel, 2026-08-29: "should actually say
    /// what it will run on"): the document's display name for one item,
    /// "3 images" for many. nil falls back to the count-only label.
    var targetDetail: String?
    /// The run's user framing ("this is a historical diary") — shown and
    /// edited at the head of the sentence (Daniel, 2026-08-30).
    var userContext: Binding<String>?
    /// The subject chip's menu (Daniel, 2026-08-29): the scopes the run
    /// COULD be aimed at — Automatic, each resolvable rung, the document's
    /// artifacts by type. Empty leaves the chip a plain label.
    var scopeOptions: [WorkflowBarPolicy.ScopeOption] = []
    /// Writes the chosen scope override (nil = Automatic). nil disables the
    /// menu rather than offering choices that go nowhere.
    var onSelectScope: ((WorkflowBarPolicy.RunScope?) -> Void)?

    /// One item's footprint. Fixed so the verbs sit on an even rhythm the way
    /// toolbar items do, rather than jittering with label length.
    private var itemWidth: CGFloat { showsLabels ? 68 : 34 }

    /// Which family's variant popover is open, if any.
    @State private var openFamily: String?
    @State private var showingTools = false
    /// Where a dragged chip would land.
    @State var dropTargetIndex: Int?
    /// The context (framing) popover (Daniel, 2026-08-30).
    @State var showsContextEditor = false

    private var families: [WorkflowBarPolicy.VerbFamily] {
        WorkflowBarPolicy.families(from: workflows, target: target, folders: folders)
    }

    var body: some View {
        VStack(spacing: 0) {
            verbRow
            // The chain gets its OWN full-width row rather than a slot on the
            // right (Daniel, 2026-08-28: "to right seems a bit small"). An
            // eight-step chain — regions, transcribe, review, entities, SVO,
            // merge, persist, catalogue — has no chance in a corner, and the
            // split is honest besides: the top row is what you CAN do, this one
            // is what you are ABOUT to do.
            if !staged.isEmpty {
                Divider()
                chainRow
            }
        }
        .background(.bar)
        .overlay(alignment: .bottom) { Divider() }
    }

    private var verbRow: some View {
        // Computed ONCE per render: `emptyReason` and the ForEach both need
        // the grouping, and calling the property twice ran the full
        // filter+group+sort of ~50 workflows twice per body evaluation —
        // at its worst exactly while the rail animates (review, 2026-08-29).
        let families = self.families
        return HStack(spacing: 0) {
            if families.isEmpty,
               let reason = WorkflowBarPolicy.emptyReason(from: workflows, target: target) {
                // Centred and quiet (Daniel, 2026-08-29): an empty bar states
                // why in two words, in the middle, rather than muttering a
                // sentence into the left margin.
                Text(reason)
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                    .frame(maxWidth: .infinity, alignment: .center)
            } else {
                // Horizontal scroll rather than clipping: a library with many
                // preset folders overflows any toolbar width, and a verb the
                // user cannot reach is the same as a verb that does not exist.
                // Centred (Daniel, 2026-08-29): the verbs sit in the middle
                // of the bar like a toolbar's principal group, not flushed
                // left. The frame trick centres the content while it fits and
                // degrades to a plain leading scroll once it overflows.
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 2) {
                        ForEach(families) { family in
                            familyItem(family)
                        }
                        // The ~110 individual tools, behind ONE entry: as
                        // top-level items they would drown the dozen workflow
                        // families, and most runs want a workflow anyway.
                        if !tools.isEmpty {
                            Divider().frame(height: 26).padding(.horizontal, 4)
                            toolsItem
                        }
                    }
                    .padding(.horizontal, 8)
                    .frame(maxWidth: .infinity, alignment: .center)
                }
            }

            if let label = targetDetail ?? WorkflowBarPolicy.targetLabel(target) {
                Divider().frame(height: 28).padding(.horizontal, 6)
                // What the run will act on, stated BEFORE it starts — a paid
                // multi-step run over a folder should never be ambiguous about
                // its scope.
                Label(label, systemImage: "scope")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize()
                    .padding(.trailing, 12)
                    .accessibilityLabel("Will run on \(label)")
            }
        }
        .frame(height: 52)
    }

    /// The chain: full width, left-aligned so it reads as a sequence, with the
    /// run control and the step count anchored right.
    private var chainRow: some View {
        // One CENTRED cluster (Daniel, 2026-08-29: "what you are building
        // below in a line that is also centred — right now it's on the far
        // right"): the rail, the run controls and the cost read as one
        // sentence under the verbs rather than being split to the edges.
        HStack(spacing: 8) {
            Spacer(minLength: 0)
            ScrollView(.horizontal, showsIndicators: false) {
                chainRail.padding(.horizontal, 10)
            }
            .fixedSize(horizontal: true, vertical: false)
            .frame(maxWidth: 600)
            HStack(spacing: 6) {
                // Run and Clear live HERE, outside the scrolling rail (review
                // fix, 2026-08-29): inside it, an eight-step chain pushed the
                // play button off-screen — the one control that must never
                // scroll away is the one that starts the run.
                if isRunning {
                    ProgressView()
                        .controlSize(.small)
                        .help("Chain is running")
                        .accessibilityLabel("Chain is running")
                } else {
                    Button(action: onRunChain) {
                        Image(systemName: "play.circle.fill")
                            .font(.title3)
                            .foregroundStyle(target == .nothing
                                             ? Color.secondary : Color.accentColor)
                    }
                    .buttonStyle(.plain)
                    // Pressing play with nothing selected used to silently do
                    // nothing — the guard in runStagedChain returned without a
                    // word (review, 2026-08-29). Disabled WITH the reason on
                    // hover is the honest version.
                    .disabled(target == .nothing)
                    .help(target == .nothing
                          ? "Select a document or folder to run this chain on"
                          : "Run \(staged.count) step(s) in order on the selection")
                    .accessibilityLabel("Run the chain")

                    Button { staged.removeAll() } label: {
                        Image(systemName: "trash")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                    .help("Clear the chain")
                    .accessibilityLabel("Clear the chain")
                }
                if let costCeiling {
                    // A CEILING, said as one: "≤" is the difference between a
                    // promise that can be kept and a guess.
                    Text("est. ≤ \(costCeiling, format: .currency(code: "USD"))")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .monospacedDigit()
                        .help(
                            "Estimated upper bound for this chain over "
                            + "\(staged.count) step(s), priced from the live "
                            + "model registry. Steps whose model cannot be "
                            + "priced are not counted."
                        )
                }
                Text(staged.count == 1 ? "1 step" : "\(staged.count) steps")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .frame(height: 34)
    }

    /// Pin a model to ONE step. Offered per chip because a chain's steps do
    /// not deserve the same model: read a hard hand with the best available,
    /// then count entities in its output with something cheap.
    @ViewBuilder
    func modelMenu(forStepAt index: Int) -> some View {
        Button("Use the workflow's default") {
            guard staged.indices.contains(index) else { return }
            staged[index].providerOverride = nil
            staged[index].modelOverride = nil
            resetOutcome(at: index)
        }
        if !modelChoices.isEmpty {
            Divider()
            ForEach(modelChoices, id: \.model) { choice in
                Button(choice.label) {
                    guard staged.indices.contains(index) else { return }
                    staged[index].providerOverride = choice.provider
                    staged[index].modelOverride = choice.model
                    resetOutcome(at: index)
                }
            }
        }
    }

    /// The Tools entry — the node editor's palette, reachable without opening
    /// the node editor, which was the whole complaint that started this bar.
    @ViewBuilder
    private var toolsItem: some View {
        Button { showingTools.toggle() } label: {
            VStack(spacing: 1) {
                Image(systemName: "wrench.and.screwdriver")
                    .font(.body)
                    .frame(height: 17)
                if showsLabels {
                    Text("Tools")
                        .font(.system(size: 9))
                        .lineLimit(1)
                }
            }
            .frame(width: itemWidth)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help("Browse all \(tools.count) tools and add one to the chain")
        .popover(isPresented: $showingTools, arrowEdge: .bottom) {
            WorkflowToolsPopover(tools: tools) { tool in
                stage(tool: tool)
                showingTools = false
            }
        }
    }

    /// One verb, drawn as a toolbar item: glyph above, small label below.
    ///
    /// Clicking ALWAYS opens the popover (Daniel, 2026-08-29: "when you click
    /// the popover should always come up") — even a single-variant family gets
    /// its context card, because the popover is where the description, the
    /// badges, and the steps & prompts live. Staging happens by choosing a
    /// variant IN the popover; nothing is added blind. The separate chevron
    /// is gone with the two-target confusion it carried.
    ///
    /// A plain `Button` owns the layout deliberately: a `Menu` re-flows its
    /// own label on macOS, which is why the first attempt kept rendering the
    /// name BESIDE the glyph.
    @ViewBuilder
    private func familyItem(_ family: WorkflowBarPolicy.VerbFamily) -> some View {
        Button {
            openFamily = openFamily == family.id ? nil : family.id
        } label: {
            VStack(spacing: 1) {
                Image(systemName: family.symbol)
                    .font(.body)
                    .frame(height: 17)
                if showsLabels {
                    Text(family.title)
                        .font(.system(size: 9))
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                }
            }
            .frame(width: itemWidth)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(helpText(for: family))
        .accessibilityLabel(helpText(for: family))
        .popover(
            isPresented: Binding(
                get: { openFamily == family.id },
                set: { if !$0 { openFamily = nil } }
            ),
            arrowEdge: .bottom
        ) {
            WorkflowVerbPopover(
                family: family,
                onAdd: { workflow in
                    stage(workflow)
                    openFamily = nil
                },
                onInspect: onInspectWorkflow.map { inspect in
                    { workflow in
                        openFamily = nil
                        inspect(workflow)
                    }
                }
            )
        }
    }

    /// Changing a step's model is declaring "try it differently" — the old
    /// verdict no longer applies (Daniel, 2026-08-29: "if I change model on a
    /// bar that has failed, it can reset colors"). The changed step and
    /// everything AFTER it go back to pending; steps before it keep their
    /// greens, since their runs are untouched.
    private func resetOutcome(at index: Int) {
        for laterIndex in staged.indices where laterIndex >= index {
            staged[laterIndex].state = .pending
            staged[laterIndex].threadId = nil
        }
    }

    private func stage(_ workflow: WorkflowSidebarItem) {
        staged.append(StagedWorkflowStep(kind: .workflow(workflow)))
    }

    private func stage(tool: ToolInfo) {
        staged.append(StagedWorkflowStep(kind: .tool(
            name: tool.name,
            displayName: tool.displayName,
            icon: tool.icon,
            usesLLM: tool.usesLLM
        )))
    }

    private func helpText(for family: WorkflowBarPolicy.VerbFamily) -> String {
        let count = family.workflows.count
        return count == 1
            ? "\(family.title) — see what it does and add it to the chain"
            : "\(family.title) — \(count) variants"
    }
}
