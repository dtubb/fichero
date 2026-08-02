import SwiftUI

// MARK: - Tab views & subviews
// Split into an extension to keep the primary type body small (SwiftLint
// type_body_length / file_length). Members are `internal` so sibling-file
// extensions can reference them.

extension ResearchTasksPane {

    // MARK: - Tasks tab

    @ViewBuilder
    var tasksTab: some View {
        VStack(spacing: 0) {
            planPicker
            if let brief = selectedPlanBrief {
                planBriefSection(brief)
            }
            Divider()
            if researchStore.tasks.isEmpty {
                ContentUnavailableView(
                    "No Tasks",
                    systemImage: "checklist",
                    description: Text("Add a task below or run the research workflow.")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List {
                    ForEach(researchStore.tasks) { task in
                        taskRow(task)
                        if expandedTaskIds.contains(task.id) {
                            stepsSection(task)
                        }
                    }
                }
                .listStyle(.plain)
            }
            composer(placeholder: "Add a task…", text: $newTaskText) { submitTask() }
        }
    }

    /// The selected plan's agent-generated brief, when it has one (#1729).
    var selectedPlanBrief: ResearchPlanBrief? {
        guard let id = selectedPlanId else { return nil }
        return researchStore.plans.first(where: { $0.id == id })?.brief
    }

    /// "Start research with AI" — name + term. The term is what makes the
    /// backend run its plan agent; without it this is a blank todo list (#1729).
    @ViewBuilder
    var planComposerSheet: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Start Research with AI")
                .font(.headline)
            Text("Fichero researches the term and suggests archives, locations, and search terms in other languages.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            TextField("Plan name", text: $newPlanName)
                .textFieldStyle(.roundedBorder)
            TextField("Research term (e.g. Marshall diaries)", text: $newPlanTerm)
                .textFieldStyle(.roundedBorder)
                .onSubmit { Task { await generatePlanWithAI() } }

            if let failure = researchStore.planFailure {
                // Icon + detail on demand — never a raw error dumped inline.
                Label("Couldn't generate the plan", systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(.orange)
                    .help(failure)
            }

            HStack {
                if researchStore.isGeneratingPlan {
                    ProgressView()
                        .controlSize(.small)
                    Text("Researching…")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button("Cancel") { isPlanComposerPresented = false }
                Button("Generate Plan") { Task { await generatePlanWithAI() } }
                    .keyboardShortcut(.defaultAction)
                    .disabled(
                        researchStore.isGeneratingPlan
                            || newPlanTerm.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    )
            }
        }
        .padding(16)
        .frame(width: 380)
    }

    /// Archives / locations / multilingual terms / summary from the agent.
    @ViewBuilder
    func planBriefSection(_ brief: ResearchPlanBrief) -> some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 6) {
                if !brief.summary.isEmpty {
                    Text(brief.summary)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                briefList("Archives", systemImage: "building.columns", values: brief.archives)
                briefList("Locations", systemImage: "mappin.and.ellipse", values: brief.locations)
                ForEach(brief.sortedMultilingualTerms, id: \.language) { entry in
                    briefList(
                        entry.language.uppercased(),
                        systemImage: "character.bubble",
                        values: entry.terms
                    )
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, 4)
        } label: {
            Label("Research Plan", systemImage: "sparkles")
                .font(.subheadline)
        }
        .padding(.horizontal, 8)
        .padding(.bottom, 6)
    }

    @ViewBuilder
    func briefList(_ title: String, systemImage: String, values: [String]) -> some View {
        if !values.isEmpty {
            VStack(alignment: .leading, spacing: 2) {
                Label(title, systemImage: systemImage)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                Text(values.joined(separator: " · "))
                    .font(.caption)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    var planPicker: some View {
        HStack(spacing: 8) {
            Image(systemName: "list.bullet.rectangle")
                .foregroundStyle(.secondary)
            Menu {
                ForEach(researchStore.plans) { plan in
                    Button {
                        Task { await selectPlan(plan.id) }
                    } label: {
                        Label(plan.name, systemImage: plan.id == selectedPlanId ? "checkmark" : "")
                    }
                }
                if let id = selectedPlanId {
                    Divider()
                    Button("Mark Plan Active") { Task { await researchStore.activatePlan(id) } }
                }
                Divider()
                Button("New Plan") { Task { await createPlan() } }
                Button("Start Research with AI…") { presentPlanComposer() }
            } label: {
                Text(currentPlanName)
                    .font(.subheadline)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .menuStyle(.borderlessButton)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
    }

    var currentPlanName: String {
        if let id = selectedPlanId, let plan = researchStore.plans.first(where: { $0.id == id }) {
            return plan.name
        }
        return "All Tasks"
    }

    func taskRow(_ task: ResearchTask) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Button {
                Task { await researchStore.cycleTaskStatus(task, to: nextStatus(task.status)) }
            } label: {
                Image(systemName: taskIcon(task.status))
                    .foregroundStyle(taskColor(task.status))
                    .frame(width: 16)
            }
            .buttonStyle(.plain)
            // The icon IS the status, so a fixed label would hide the whole
            // point of the control. It announces where the task is now and
            // where activating it will move it.
            .accessibilityLabel(
                "Status: \(task.status.label). Activate to set \(nextStatus(task.status).label)"
            )
            VStack(alignment: .leading, spacing: 2) {
                Text(task.name)
                    .font(.body)
                if !task.description.isEmpty {
                    Text(task.description)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
                Text(task.status.label)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            Spacer()
            Button {
                Task { await toggleSteps(task) }
            } label: {
                Image(systemName: expandedTaskIds.contains(task.id) ? "chevron.down" : "chevron.right")
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.plain)
            .help(expandedTaskIds.contains(task.id) ? "Hide this task's steps" : "Show this task's steps")
            .accessibilityLabel(
                expandedTaskIds.contains(task.id)
                    ? "Hide steps for \(task.name)"
                    : "Show steps for \(task.name)"
            )
        }
        .padding(.vertical, 2)
    }

    @ViewBuilder
    func stepsSection(_ task: ResearchTask) -> some View {
        let steps = researchStore.stepsByTask[task.id] ?? []
        ForEach(steps) { step in
            HStack(spacing: 8) {
                Button {
                    Task { await researchStore.toggleStep(task: task, step: step) }
                } label: {
                    Image(systemName: step.status == .completed ? "checkmark.circle.fill" : "circle")
                        .foregroundStyle(step.status == .completed ? .green : .secondary)
                }
                .buttonStyle(.plain)
                // Names its step AND carries the state as a value, so the
                // checkmark is not the only thing that says "done".
                .accessibilityLabel(step.label)
                .accessibilityValue(step.status == .completed ? "Completed" : "Not completed")
                Text(step.label).font(.caption)
                Spacer()
                Text(step.tool.label).font(.caption2).foregroundStyle(.tertiary)
            }
            .padding(.leading, 28)
        }
        Button {
            Task { await researchStore.addStep(toTask: task) }
        } label: {
            Label("Add step", systemImage: "plus.circle")
                .font(.caption)
        }
        .buttonStyle(.plain)
        .padding(.leading, 28)
    }
}
