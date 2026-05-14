# Workflow Execution Architecture — Design Proposal

> **Status:** DRAFT — needs Daniel's approval before any code.
> **Date:** 2026-05-14 · **Branch:** 0.0.2
> **Drives:** #1000 (backend freezes during runs) and the path to 500 folders × 500 files.

---

## The problem

Today a workflow runs as `asyncio.create_task(_run_workflow_in_background(...))` (`core.py:218`) — on the **FastAPI main event loop**. Inside it, `app.astream_events(...)` (`runner.py:545`) drives every tool node as a coroutine on that same loop.

Any tool node that does **synchronous blocking work** — a long DuckDB query, a sync embedding call, an fm-bridge subprocess wait — blocks the entire loop. While blocked: `/api/health` stops answering, the SwiftUI app's requests time out, and the app blanks (#1000). It also means workflows can't run concurrently and there's no story for batch scale.

Daniel's target: run reliably over **500 folders × 500 files ≈ 250k documents**. That makes this not a bug fix but an architecture question, and the binding constraint is the database.

## The binding constraint: DuckDB is single-writer

DuckDB allows **one** read-write process. Within a process, a `Connection` is **not thread-safe**. So you cannot "just parallelise" `db.save()` across threads or processes — you get lock contention, and across processes, hard failures.

**The correct shape: parallelise the compute, serialise the persistence.**
Many workers do the expensive parallel work (LLM calls, OCR, embedding) concurrently → they hand finished rows to a **single DB-writer** that owns the connection → the writer batches them. Full parallelism where it helps; zero contention where it would hurt.

---

## Proposed architecture — phased

Four phases. **Each phase ships working, testable software on its own.** Phase 1 is the immediate #1000 fix and is the only phase ready to execute today; Phases 2–4 are the scale path and need the design decisions below confirmed first.

### Phase 1 — Move workflow execution off the main event loop (#1000)

**Goal:** the API loop never blocks, no matter what a tool node does.

**Approach:** run `_run_workflow_in_background` on a **dedicated worker thread with its own event loop** (`threading.Thread` → `asyncio.run(...)`), instead of `asyncio.create_task` on the main loop.

**The one hard part — the SSE event queue.** `_running_workflows[thread_id]["events"]` is an `asyncio.Queue`, and `asyncio.Queue` is **bound to the loop that created it** — it cannot be safely `put`/`get` across two loops. Options, in order of preference:
- **A. `janus.Queue`** — a queue with both a sync and an async face, purpose-built for exactly this thread↔loop handoff. Adds one small dependency. *Recommended.*
- **B. Plain `queue.Queue` + `loop.call_soon_threadsafe`** — the worker thread pushes events; the main loop's SSE streamer is woken via `call_soon_threadsafe`. No new dependency, more wiring.
- **C. Keep the queue on the main loop, only marshal `put`s** via `call_soon_threadsafe` from the worker thread. Least change, but every `await event_queue.put(...)` in `runner.py` (there are many) becomes a cross-loop call — error-prone.

**DECISION NEEDED #1:** janus dependency (A) vs. no-dependency wiring (B)?

**Scope:** `core.py` (swap `create_task` for the thread spawn), `runner.py` (queue handoff), the SSE streaming endpoint that drains the queue, cancellation path (`_remove_workflow_state` / cancel must signal across the thread boundary). Bounded — one workflow per thread, no pool yet.

**Acceptance:** while a workflow with a deliberately-blocking node runs, `GET /api/health` keeps returning 200; SSE events still stream; cancel still works.

### Phase 2 — Single-writer DB queue

**Goal:** all DB writes from workflow execution go through one owner — safe under any amount of compute concurrency.

**Approach:** a **DB-writer task** that owns the library's DuckDB connection and consumes a write queue. Tool nodes stop calling `db.save(...)` directly; they enqueue write requests (`{kind, payload}`) and `await` an ack. The writer applies them in order, batched.

**DECISION NEEDED #2:** scope of "all writes." Workflow tool writes clearly route through it. Do interactive API writes (user edits an entity, deletes a doc) also route through it, or keep their current direct path? Recommendation: **start with workflow-execution writes only** — that's where the fan-out concurrency is — and leave interactive single-writes direct for now, since within one process DuckDB serialises them and they're low-volume.

**Acceptance:** a workflow fanning out N parallel extractions produces correct, complete rows with no lock errors; writer is the only thing holding the write connection.

### Phase 3 — Batched writes + backpressure

**Goal:** don't melt at 250k files.

- **Batched writes** — the writer flushes every K rows or T milliseconds, not row-by-row. (`extract_all` currently does per-item `db.save()` — that becomes per-batch.)
- **Backpressure** — bounded queues + a worker semaphore so we never have 250k coroutines/rows in flight at once. `extract_all` already has `FICHERO_EXTRACT_MAX_IN_FLIGHT` (default 3) — generalise that idea to the run level.

**Acceptance:** a synthetic 10k-file run completes with bounded memory and steady throughput.

### Phase 4 — Resumability / checkpointing

**Goal:** a run that dies at file 180k of 250k resumes, doesn't restart.

LangGraph already has a checkpointer (DuckDB-backed — `db.py:1179` `_migrate_checkpoint_tables`). This phase is: make per-file/per-folder progress durable and the run re-entrant — on restart, skip files whose rows already exist.

**DECISION NEEDED #3:** granularity of the resume unit — per file, or per folder? Per-file is more robust but more checkpoint writes.

**Acceptance:** kill the backend mid-run; restart; the run resumes and the final row count matches a clean run.

---

## Recommendation

1. **Ship Phase 1 now** as the bounded #1000 fix — it stops the freeze, it's verifiable, and it's a prerequisite for everything else. Needs DECISION #1.
2. **Phases 2–4 are a milestone** ("Workflow execution at scale" or similar) — sequence them after Phase 1, each its own PR. Need DECISIONS #2 and #3 before Phase 2 starts.
3. Do **not** fold Phases 2–4 into a #1000 bug fix — that's how you get a fragile rewrite.

## Open decisions (need Daniel)

| # | Decision | Recommendation |
|---|---|---|
| 1 | SSE queue across loops: `janus` dependency vs. no-dep wiring | `janus` — small, purpose-built, less error-prone |
| 2 | Single-writer scope: workflow writes only, or all writes | Workflow-execution writes only to start |
| 3 | Resume granularity: per-file vs. per-folder | Per-file |

## Beyond workflows — other blocking-call hotspots

Daniel's question: "are there other things that need to be on async/off-loop calls so we don't freeze the UI?" Yes. Any FastAPI route handler (or dependency) that does synchronous blocking work on the main loop has the same failure mode as #1000 — it freezes `/api/health` and blanks the app. Candidates to audit (Phase 1 fixes workflow execution; this is a separate sweep):

- **Mermaid PNG render** (#1025) — `draw_mermaid_png()` does a *synchronous* HTTP POST to mermaid.ink inside the route handler. A slow/hanging upstream blocks the loop. (Fixing #1025 by rendering in-app removes this entirely.)
- **fm-bridge subprocess calls** — `llm.py` spawns fm-bridge and waits. If that wait is synchronous (not `await`ed via `asyncio.create_subprocess_exec`), it blocks.
- **Long DuckDB queries** — full-library scans (`db.query(KnowledgeClaim)` over a large KG, the cascade-delete in #1021, graph rebuilds) run synchronously. Fine for small libraries; at 250k docs they need `run_in_executor`.
- **Embedding calls** — fastembed/LanceDB indexing is CPU-bound and synchronous. #1004 already moved the KG embed endpoints to a worker thread; audit the rest.
- **Kreuzberg extraction** at ingest — synchronous, CPU-heavy.

**Recommended:** a one-time audit task — grep every `async def` route handler for synchronous blocking calls (`requests.`, `subprocess.run`, un-`await`ed DB scans, embedding calls) and wrap them in `run_in_executor`. Track as its own issue alongside the Phase 2 milestone.

## Once approved

Phase 1 becomes a bite-sized executable plan in `docs/superpowers/plans/`. Phases 2–4 get folded into a milestone with their own plans.
