import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

// MARK: - Run trees (#5415): the Activity table's run → step → page rows

extension ActivityStore {
    /// Fetch one run's tree once, when its row is first shown. Later reads
    /// come from the change stream (`applyActivityEvent`), never a poll.
    func loadRunTree(threadId: String) async {
        guard runTrees[threadId] == nil, !runsWithoutTree.contains(threadId) else { return }
        await fetchRunTree(threadId: threadId)
    }

    /// Read one run's tree and patch that ONE key. A failed read keeps what
    /// the row showed; a run the engine has no tree for is remembered.
    private func fetchRunTree(threadId: String) async {
        guard !treeFetchesInFlight.contains(threadId) else { return }
        treeFetchesInFlight.insert(threadId)
        defer { treeFetchesInFlight.remove(threadId) }
        do {
            if let tree = try await activityService.getJobTree(id: threadId) {
                if treeReadFailures[threadId] != nil { treeReadFailures[threadId] = nil }
                if runTrees[threadId] != tree { runTrees[threadId] = tree }
                if tree.kind == Self.recipeRunKind { await readRecipeRunFolders(jobId: threadId) }
            } else {
                runsWithoutTree.insert(threadId)
            }
        } catch {
            log.debug("ActivityStore: tree for \(threadId, privacy: .public) failed \(error.localizedDescription, privacy: .public)")
            treeReadFailures[threadId] = "Couldn't read this row: \(await Self.engineCause(of: error))"
        }
    }

    /// Why the details of a row cannot be shown, in words, when its tree read failed (never a blank pane; nil while it is
    /// merely not read yet). The run's thread is the part of a step's id before the colon.
    func detailsReadFailure(forJobId jobId: String) -> String? {
        if let failure = treeReadFailures[jobId] { return failure }
        guard let colon = jobId.lastIndex(of: ":") else { return nil }
        return treeReadFailures[String(jobId[..<colon])]
    }

    /// A recipe run's folders from its status (`GET /api/recipes/project/runs/{id}`), patched on its ONE key.
    /// A failed read keeps what was shown.
    private func readRecipeRunFolders(jobId: String) async {
        do {
            guard let status = try await activityService.getRecipeRunStatus(jobId: jobId),
                  let folders = RecipeRunFolders(status) else { return }
            if recipeRunFolders[jobId] != folders { recipeRunFolders[jobId] = folders }
        } catch {
            log.debug("ActivityStore: recipe run \(jobId, privacy: .public) status failed \(error.localizedDescription, privacy: .public)")
        }
    }

    /// Pause or resume one row's job (`activity.pause.per-job`) and set the
    /// state the engine answers on that ONE node in place. `runThreadId` is
    /// the run whose tree holds it. Returns what went wrong, in words, or nil.
    func setJobPaused(jobId: String, paused: Bool, runThreadId: String?) async -> String? {
        do {
            let state = try await activityService.setJobPaused(id: jobId, paused: paused)
            patchJobState(state, jobId: jobId, runThreadId: runThreadId)
            await rereadJobOfItsOwn(jobId)
            return nil
        } catch {
            return error.localizedDescription
        }
    }

    /// Stop one row's job and what is under it (the audited `job.cancel`).
    func cancelJob(jobId: String, runThreadId: String?) async -> String? {
        do {
            let state = try await activityService.cancelJob(id: jobId)
            patchJobState(state, jobId: jobId, runThreadId: runThreadId)
            await rereadJobOfItsOwn(jobId)
            return nil
        } catch {
            return error.localizedDescription
        }
    }

    /// Run a failed or stopped row's job again (`job.retry`, #5356): the state
    /// the engine answers is set on that ONE node in place, and a job of its
    /// own is re-read by the jobs poll. Returns the engine's refusal, in its
    /// words, or nil.
    func retryJob(jobId: String, runThreadId: String?) async -> String? {
        do {
            let answer = try await activityService.retryJob(id: jobId)
            let listed = backgroundJobs.contains { $0.id == jobId }
            if let old = answer.replaces, old != answer.id {
                // A retried workflow run is a NEW run (#5555's read-again path): the old row becomes it, in place,
                // and nothing is set on the old id, which the engine no longer lists.
                replaceRetriedRun(old, with: answer.id, state: answer.state)
            } else {
                patchJobState(answer.state, jobId: jobId, runThreadId: runThreadId)
            }
            if listed { await refreshBackgroundJobs() }
            return nil
        } catch {
            return error.localizedDescription
        }
    }

    /// Each step waiting on a failed download takes the next candidate of its chain (#5352). Returns the
    /// engine's first refusal, in its words, or nil.
    func useNextCandidate(steps: [String], card: String) async -> String? {
        do {
            for step in steps { try await activityService.useCandidate(step: step, card: card) }
            return nil
        } catch {
            return error.localizedDescription
        }
    }

    /// Read the pages a finished run did not do (#5555): the engine starts one
    /// new run; the run list picks it up on the next resync. Returns what went
    /// wrong, in words, or nil.
    func readPagesAgain(runThreadId: String) async -> String? {
        do {
            _ = try await activityService.readPagesAgain(threadId: runThreadId)
            await resync()
            return nil
        } catch {
            return error.localizedDescription
        }
    }

    func scheduleTreeRead(threadId: String) {
        pendingTreeReads[threadId]?.cancel()
        pendingTreeReads[threadId] = Task { [weak self] in
            guard let delay = self?.treeReadDelay else { return }
            try? await Task.sleep(for: delay)
            guard !Task.isCancelled, let self else { return }
            self.pendingTreeReads[threadId] = nil
            await self.fetchRunTree(threadId: threadId)
        }
    }

    // MARK: - The details of one row (#5561)

    /// The project's name, for the details' heading; nil for the always-there project, which has
    /// no name (`ActivityRun.projectLabel`).
    var projectName: String? { ActivityRun.projectLabel(library?.displayName) }

    /// A row's node, read from the record the table reads (`activity.details.one-record`):
    /// its node in a loaded tree, else a job of its own from the jobs poll.
    /// `nil` until its tree is loaded (`loadDetails`).
    func node(jobId: String) -> ActivityJobNode? {
        if let root = runTrees[jobId] { return root }
        for root in runTrees.values {
            if let found = root.node(withId: jobId) { return found }
        }
        return backgroundJobs.first { $0.id == jobId }.map(ActivityJobNode.init(job:))
    }

    /// The recipe runs (#5576) whose stages include the run `threadId`: their
    /// trees are read again when that run changes, so a stage's pages done and
    /// left follow live in the recipe run's details.
    func recipeRunTrees(holdingStage threadId: String) -> [String] {
        runTrees.compactMap { key, tree in
            tree.kind == "run-a-recipe" && tree.children.contains { $0.id == threadId } ? key : nil
        }
    }

    /// The engine's kind for a recipe run (`recipes/runner.KIND`).
    nonisolated static let recipeRunKind = "run-a-recipe"

    /// Follow the project's running recipe run on the strip (#5576): the first
    /// one the jobs poll lists running, waiting or paused (never the row that
    /// stands for several waiting ones), its tree read once. Later reads are
    /// the poll's and the change stream's; when it ends and leaves the list its
    /// tree is read once more, which carries what it made (#5577).
    func followProjectRun(in jobs: [ActivityJob]) async {
        guard let live = jobs.first(where: { job in
            job.taskType == Self.recipeRunKind && job.parentId == nil && !job.id.hasPrefix("waiting:")
                && (job.state.isActive || job.state == .waiting) && !putAwayRunIds.contains(job.id)
        }) else { return }
        await adoptProjectRun(live.id)
    }

    /// When the project opens (#5576, `source.onboard.auto.lands-on-the-run`): the
    /// run the strip would be showing had the app stayed open. The newest recipe
    /// run still running, waiting or paused; else the newest run that ended, unless
    /// the person closed its summary. Read once from the project's recipe runs
    /// (newest first); from then on the jobs poll follows it as any other.
    func restoreProjectRun() async {
        guard projectRunId == nil else { return }
        let runs: [Components.Schemas.RecipeRunStatus]
        do {
            runs = try await activityService.getProjectRecipeRuns()
        } catch {
            log.debug("ActivityStore: recipe runs read failed \(error.localizedDescription, privacy: .public)")
            return
        }
        let ended: Set<String> = ["done", "failed", "cancelled"]
        let live = runs.first(where: { !ended.contains($0.state) && !putAwayRunIds.contains($0.jobId) })
        // Only the newest ended run: an older one never takes the place of a summary the person closed.
        let newestEnded = runs.first(where: { ended.contains($0.state) })
        let run = live ?? newestEnded.flatMap { putAwayRunIds.contains($0.jobId) ? nil : $0 }
        guard let run, projectRunId == nil else { return }
        await adoptProjectRun(run.jobId)
    }

    /// The strip shows `id`: its tree read once, as the record its words come from.
    private func adoptProjectRun(_ id: String) async {
        if projectRunId != id { projectRunId = id }
        await loadRunTree(threadId: id)
    }

    /// A recipe run's stage (a workflow run) whose row on the jobs poll moved
    /// re-reads the recipe run's tree, so the project's strip and its details
    /// follow the stage's pages (#5576), as a change-stream frame naming it does.
    func rereadRecipeRuns(holdingStagesChangedFrom before: [String: ActivityJob], to jobs: [ActivityJob]) {
        for job in jobs where before[job.id] != job {
            for key in recipeRunTrees(holdingStage: job.id) { scheduleTreeRead(threadId: key) }
        }
    }

    /// The person put the strip away: that run is not shown on it again, nor
    /// after a relaunch (#5576).
    func putAwayProjectRun() {
        guard let id = projectRunId else { return }
        putAwayRunIds.insert(id)
        projectRunId = nil
        guard let putAwayKey else { return }
        let kept = (defaults.stringArray(forKey: putAwayKey) ?? []).filter { $0 != id } + [id]
        defaults.set(Array(kept.suffix(Self.putAwayKept)), forKey: putAwayKey)
    }

    /// The key of the tree that holds `jobId`: its run's thread id, or the
    /// job's own id for a job of its own.
    func treeKey(containing jobId: String) -> String? {
        if runTrees[jobId] != nil { return jobId }
        return runTrees.first { $0.value.node(withId: jobId) != nil }?.key
    }

    /// Read the tree a row's details need, once: a step's run (its id is
    /// `<run>:<step>`), else the job's own. Later reads are the table's own
    /// (the change stream, the jobs poll): the details open no stream or poll.
    func loadDetails(jobId: String) async {
        guard treeKey(containing: jobId) == nil else { return }
        if let colon = jobId.lastIndex(of: ":") {
            await loadRunTree(threadId: String(jobId[..<colon]))
            if treeKey(containing: jobId) != nil { return }
        }
        await loadRunTree(threadId: jobId)
    }

    /// The kind a waiting or paused kind row stands for (`waiting:<kind>`, `paused:<kind>`); nil for any other row.
    static func queuedKind(ofRowId id: String) -> String? {
        for prefix in ["waiting:", "paused:"] where id.hasPrefix(prefix) && id.count > prefix.count {
            return String(id.dropFirst(prefix.count))
        }
        return nil
    }

    /// What the pages list is re-read on: the kind row's own count, state and reason, so it follows the queue as it
    /// drains (the details' `logKey` has no node for a kind row, so it only changes with the row's phase).
    func queueKey(forRowId id: String) -> String {
        guard let job = backgroundJobs.first(where: { $0.id == id }) else { return id }
        return [id, "\(job.current)", "\(job.total)", String(describing: job.state), job.reason ?? ""].joined(separator: "|")
    }

    /// How many more queued pages the row stands for than the list holds. A kind row's total is done plus queued, so
    /// the ones still to go are `total - current`, less what the list already shows (## 492).
    func queuedPagesNotListed(rowId id: String, listed: Int) -> Int {
        guard let job = backgroundJobs.first(where: { $0.id == id }) else { return 0 }
        return max(0, (job.total - job.current) - listed)
    }

    /// Read the pages queued behind a kind's row; the details call it when the row's count changes. A failed read
    /// keeps the pages already shown.
    func loadQueuedItems(rowId: String, limit: Int = 50) async {
        guard let kind = Self.queuedKind(ofRowId: rowId) else { return }
        do {
            let items = try await activityService.listQueuedItems(kind: kind, limit: limit)
            if queuedItems[kind] != items { queuedItems[kind] = items }
        } catch {
            log.debug("ActivityStore: pages of \(kind, privacy: .public) failed \(error.localizedDescription, privacy: .public)")
        }
    }

    /// Read one row's log; the details call it when the row's node changes.
    /// A failed read keeps the lines already shown.
    func loadJobLog(jobId: String, developer: Bool = false, problemsOnly: Bool = false) async {
        do {
            let lines = try await activityService.getJobLog(id: jobId, developer: developer, problemsOnly: problemsOnly) ?? []
            if jobLogs[jobId] != lines { jobLogs[jobId] = lines }
            // Whether the log has a problem is known from a read of all the lines; a Problems read is all problems.
            let problems = problemsOnly ? !lines.isEmpty : ActivityLogFilter.hasProblems(lines)
            if jobLogHasProblems[jobId] != problems { jobLogHasProblems[jobId] = problems }
            let count = problemsOnly ? lines.count : lines.filter { ActivityLogFilter.problemLevels.contains($0.level) }.count
            if !developer, jobLogProblemCount[jobId] != count { jobLogProblemCount[jobId] = count }
        } catch {
            log.debug("ActivityStore: log for \(jobId, privacy: .public) failed \(error.localizedDescription, privacy: .public)")
        }
    }

    /// The old run's rows become the new run's, where they stood: its jobs-list row, its run row, its tree (dropped, to
    /// be read for the new run), the project's run strip and the details' selection.
    private func replaceRetriedRun(_ old: String, with new: String, state: String) {
        let jobs = Self.swapping(backgroundJobs, old: old, new: new, state: state)
        if jobs != backgroundJobs { backgroundJobs = jobs }
        let swappedRuns = Self.swapping(runs, old: old, new: new, state: state)
        if swappedRuns.map(\.id) != runs.map(\.id) { runs = swappedRuns }
        if runTrees[old] != nil { runTrees[old] = nil }
        if projectRunId == old { projectRunId = new }
        let selection = ActivityWindowSelectionState.shared
        if selection.selection?.jobId == old {
            selection.select(ActivitySelection(jobId: new, libraryId: selection.selection?.libraryId))
        }
    }

    private func patchJobState(_ state: String, jobId: String, runThreadId: String?) {
        guard let runThreadId, let tree = runTrees[runThreadId],
              let changed = tree.settingState(state, of: jobId) else { return }
        runTrees[runThreadId] = changed
    }

    /// A job of its own (the import's row, a kind's counted row, #5621) has no
    /// tree node to patch: the jobs read gives its state after Pause or Stop.
    private func rereadJobOfItsOwn(_ jobId: String) async {
        if backgroundJobs.contains(where: { $0.id == jobId }) {
            await refreshBackgroundJobs()
        }
    }

    /// Set how background work runs on this Mac (`activity.mode.start-stop`,
    /// #5621): the one engine action behind the main toolbar's Start / Stop
    /// button and the Activity window's. The mode the engine answers is set
    /// in place (the pause with it), then the jobs read follows. Returns what
    /// went wrong, in words, or nil.
    func setBackgroundMode(_ mode: ActivityMode) async -> String? {
        do {
            let now = try await activityService.setBackgroundMode(mode)
            modeAnswers += 1
            if backgroundMode != now { backgroundMode = now }
            if backgroundPaused != (now == .paused) { backgroundPaused = now == .paused }
            await refreshBackgroundJobs()
            return nil
        } catch {
            return error.localizedDescription
        }
    }
}
