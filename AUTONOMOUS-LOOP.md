# Autonomous Loop Setup — Curator + Worker Pattern

## Overview

The autonomous loop runs N issues from the GitHub backlog using a **curator/worker split**:

1. **Curator** (Sonnet 4.5): Ranks 80 open issues, produces `queue.md` (20 issues) + `digest.md` (2k brief)
2. **Workers** (Haiku 4.5): Pop one pending issue per iteration, use jcodemunch tools to explore/implement, commit + close
3. **Loop**: Curator → N workers → Curator → N workers → ...

## Quick Start

### Single test iteration (debug)

```bash
cd ~/code/fichero-0.0.2
~/code/fichero-skills/bin/worker-loop.sh . 1
```

### 3-5 iterations (validate flow)

```bash
HAIKU_MODEL=claude-haiku-4-5-20251001 ~/code/fichero-skills/bin/worker-loop.sh . 5
```

### Full batch (20 workers)

```bash
~/code/fichero-skills/bin/batch-loop.sh . 1 20
```

## Scripts

All scripts are in `~/code/fichero-skills/bin/`:

| Script | Purpose | Env Vars |
|--------|---------|----------|
| **curator.sh** | Rank issues, write queue.md + digest.md | `CURATOR_MODEL`, `QUEUE_SIZE`, `MILESTONE` |
| **worker-loop.sh** | Run N Haiku iterations | `HAIKU_MODEL`, `CURATE_EVERY` |
| **batch-loop.sh** | Run BATCHES × WORKERS_PER_BATCH full cycles | `CURATOR_MODEL`, `HAIKU_MODEL`, `SLEEP_BETWEEN` |
| **agent-autonomous-loop.py** | Core: invokes Claude CLI with skill, N iterations | (called by worker-loop.sh) |

## Output Files

- `agent-work/queue.md` — YAML-formatted issues (status: pending/in_progress/done/blocked)
- `agent-work/digest.md` — Curated 2k brief for workers (invariants, commands, pitfalls)
- `HISTORY/curator.md` — Curator run log (timestamps, queue size, digest size)
- `HISTORY-worker.md` — Worker session log (issue #, status, commit hash)

## Skills

**Curator**: Uses jcodemunch tools (search_symbols, get_file_outline, find_references, get_blast_radius, get_class_hierarchy) to:
- Map issues to files
- Estimate blast radius (est_tokens)
- Rank by dependency order + small-first heuristic
- Skip: needs-human-test, blocked-external, wontfix labels

**Worker** (`/fs_autoloop:session-worker`): Mandatory jcodemunch-first pattern:
1. Load digest.md + first pending block from queue.md
2. Mark issue as in_progress
3. Use jcodemunch ONLY for code exploration (no Read/Grep/Glob on .py/.ts/.swift)
4. Implement approach, run tests, ruff check
5. Commit + push + close issue
6. Call `/session-end-worker` to mark status in queue

## Token Budgets

**Curator pass** (Sonnet, ~7k tokens):
- 80 raw issues: ~2k tokens
- jcodemunch introspection: ~2k tokens
- Queue + digest output: ~3k tokens
- Cost: ~$0.20-0.40

**Worker iteration** (Haiku, ~15-30k tokens):
- digest.md + issue block: ~3k tokens
- jcodemunch exploration: ~5-10k tokens
- Implementation + tests: ~7-15k tokens
- Cost: ~$0.05-0.10 per issue

## Status Protocol

Queue entries use `status` field:
- `pending` — not yet claimed
- `in_progress` — worker is working on it (status marked by worker to avoid double-claim)
- `done` — completed, includes commit hash + completed_at timestamp
- `blocked` — blocked with reason in `blocked_reason` field

Curator sees ALL statuses when re-ranking. Only carries forward `pending` + `blocked` (unless blocker resolved). Omits `done` from next queue.

## Next: Full 3-Batch Run

When ready to scale:

```bash
# Run 3 batches of 5 workers each (15 issues total)
~/code/fichero-skills/bin/batch-loop.sh ~/code/fichero-0.0.2 3 5
```

Expected time: ~10-15 min (curator 2-3 min, workers 5-10 min, sleep 60s between batches).

## Debugging

**Worker hung?**
```bash
ps aux | grep claude | grep haiku
pkill -9 -f "claude.*haiku"
```

**Queue stuck?**
```bash
tail agent-work/queue.md
# Mark issue as blocked:
sed -i '/issue: NNN/,/status:/ s/status: pending/status: blocked/' agent-work/queue.md
```

**Rerun curator (re-rank issues):**
```bash
MILESTONE=0.0.2 ~/code/fichero-skills/bin/curator.sh ~/code/fichero-0.0.2
```
