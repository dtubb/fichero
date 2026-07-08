---
name: choose-next
description: Manager picks the next work batch to delegate — reads agents/ROADMAP.md + GitHub milestones/issues, finds the highest-incomplete tier with ready work, and returns 1 big issue OR 3–10 small same-milestone issues sized for a worker's context.
---

# /choose-next

Deterministic front of the manager loop: decide WHAT to delegate next, in the
right order. Do not implement — just select and hand off.

## Steps

1. **Read the roadmap (source of truth for order):**
   ```bash
   sed -n '1,140p' agents/ROADMAP.md
   ```
   The tiers are: 0 Gates/Verify → 1 Infrastructure → 2 Right-approaches (observable) →
   3 Features → 3b Domain → 4 Mactastic → 5 Testing → 6 Profiling → 7 UI-consistency.
   **Pick the lowest-numbered tier that still has incomplete, ready work.**

2. **Find ready issues in that tier's milestone(s):**
   ```bash
   gh issue list --milestone "<milestone>" --state open --limit 40 \
     --json number,title,labels --jq '.[] | "\(.number)\t\(.title)"'
   ```
   Skip anything with `status:in-progress` or an assignee (already claimed).
   Prefer issues whose guardrail/KNOWN_VIOLATIONS count is non-zero (real work).

3. **Size the batch** (worker-context economy):
   - **1 big issue** (a keystone / cross-cutting EPIC slice), OR
   - **3–10 small issues in the SAME milestone** (so the worker reuses context).
   Never mix milestones in one worker.

4. **Tag the batch** with the model + lane it needs:
   - cheap default: **Sonnet** (frontend Swift) / **codex 5.4-mini** (backend/tooling)
   - escalate to **Opus / codex 5.5** only for keystones (new stores, action layer,
     high-blast-radius).

5. **Output** (for the manager to hand to `/dispatch-worker`):
   - tier + milestone, the issue numbers, big-vs-batch, model, a one-line objective.

## Notes
- If the highest-incomplete tier is Tier 0 (gates), prefer building the missing
  guardrail/verify piece — gates first protect everything else.
- A verify run that auto-filed issues (see the gardener / verify_report.py) has
  already put fresh errors in the right milestone; this skill just picks them up.
