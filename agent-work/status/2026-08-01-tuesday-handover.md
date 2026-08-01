# Tuesday handover — 2026-08-01 autonomous run

Five-minute read. The build you are testing carries ~60 closed issues and three
lanes of fixes. Four sections: what to click, what to decide, what needs your
data or device, what changed under you.

## 1. What to click, in priority order

Each item: exact steps → the specific failure to look for.

1. **Delete, both paths** (#4448, #4453, #4454 — the crash family)
   - Right-click → Delete a *document* in the sidebar. Look for: crash (the
     07-30 crash), or the item surviving.
   - Delete the *currently selected* item, then quit and relaunch. Look for:
     crash at launch (a stale selection id used to persist and trap).
   - Try Delete on a *structural* row (a library header / section). Look for:
     a confirmation that then does nothing — that row should no longer offer
     Delete at all.
2. **Import, all three doors** (#4449, #4452)
   - Bottom-bar ⬇ button, right-click a folder → "Import Files Here…", and
     File menu → Import with the *library pane* (not sidebar) focused.
   - Look for: a dead click (picker never appears), or files landing at the
     library ROOT when you imported into a folder.
3. **Run a workflow scoped right** (#4396, #4450, #4419)
   - Select ONE PDF, run Catalogue. Look for: the whole folder processing.
   - In a NON-global library, run a default workflow (Transcribe) from the
     sidebar context menu — on an *image* too. Look for: "Workflow not found
     in this library", or the Run Workflow submenu simply missing.
4. **OCR text boxes** (#4418) — toggle boxes on a PDF page *and* an image.
   - Look for: boxes **vertically mirrored** (a y-flip — geometry is
     cropBox-based; a mirror means an origin bug), or offset by a margin
     (cropBox origin dropped).
   - Note: geometry exists only for imports made AFTER the capture landed
     (`ingest.py:731`) — re-import a test PDF first or boxes are legitimately
     absent.
5. **Drag and drop** (#4401, #4458)
   - Drag a *transcribed* document to another folder, same library. Look for:
     a copy appearing instead of a move, or a refusal.
   - Drag a file from Finder onto the content pane, then onto a sidebar row.
     Then CLICK sidebar rows normally. Look for: clicks that stop landing —
     the content-pane drop target was reverted once already for exactly that
     hit-testing risk (#4458 is the retry).
6. **Canvas selection** (#4436, #4409) — ⌘-click two items on the canvas.
   Look for: the second click *replacing* the selection instead of adding, or
   the blue flash on every selection.
7. **Translate an artifact** (#4306) — right-click an artifact in a
   non-global library → Translate. Look for: an instant error (it used to run
   against the global library's database; if it errors now, read the message
   — "document not found" means the fix missed, a provider message is a
   different, real question).
8. **Search with accents** (#4363) — search `Choco` from the keyboard;
   expect `Chocó` hits with highlights on the right characters. Then search
   `Chocó`; expect the same set.
9. **The island and breadcrumb** (#4416) — open a page; look for
   `fichero_upload_….pdf` anywhere, or "Page 1" printed twice.
10. **Stop a run** (#4402, #4346) — start Catalogue on a few files, press
    Stop mid-node. Look for: the run continuing, or spinners that never stop
    (Activity AND the sidebar rows).

## 2. Decisions only you can make

- **#4460 — shift-click extends along *what* order on a spatial canvas?**
  Recommendation: document order (stable, matches list modes). Objection,
  fairly: on a 2D canvas nothing *looks* like document order, so users may
  expect spatial proximity — the fallback is to make shift-drag marquee the
  primary multi-select and let shift-click stay simple.
- **#2440 — which palette did you mean?** The issue predates two theming
  passes; lane-import could not tell whether "palette" meant the sidebar
  tint set or the canvas node colors. One sentence from you resolves it.
- **#3961 — dead `DocumentHierarchy`.** Never used in production, only by
  its own tests. Recommendation: delete it (its tests are testing nothing
  the app runs). Objection: it may be the intended shape for #4399
  multi-level cataloguing — if so, say "keep, it's the #4399 skeleton" and
  it gets an issue reference instead of deletion.

## 3. Needs your data, device, or eyes

- **#2464** — reproduces only against the ICANH library. Note: the root
  causes referenced in the issue predate several reorgs; treat its analysis
  as stale and re-observe.
- **#3382** — the layout fault (unlike its siblings, this one is not log
  noise). Needs your screen and a window resize.
- **#3980** — launch profiling: needs Instruments on your machine; the
  numbers in the issue are from Dev, not release.
- **#4303 / #4304** — MLX provider and embeddings-model download,
  end-to-end with real network/models.
- **#4331** — iOS TestFlight: install and launch. The crash fix
  (view-type depth vs the 1 MB iOS stack) is in this build; launch alone is
  the test.
- **Tuesday-verify closes**: most of section 1's issues are already fixed
  and commented with SHAs — a working click closes them, a failing one
  reopens with fresh evidence.

## 4. What changed under you

- **The environment-forwarding rule was found to be FALSE and withdrawn**
  (9d30fd8bd, 5966c3a7c): fourteen ceremonial forwards were reverted; the
  real boundary is *toolbar hosting*, and the guard now watches that — it
  fires on the NEXT unforwarded store, not just the last one that crashed.
- **`gate part <area>`** was silently running ZERO legs (then exiting green
  on red). Fixed twice over; it now runs the full guardrail sweep and its
  exit code means what it says. Also: **30 of 63 guardrail scripts could
  pass against an empty tree** — all now exit 2 ("could not check") when
  their scan roots are missing.
- **The perf ratchet is live**: every engine test's elapsed time is held to
  its best-ever, contended samples refused. Peak-memory / query-count /
  size / warning-count ratchets (#4440–#4446) are queued next.
- **The 77 GB temp leak that filled your disk is fixed**: a killed test run
  can no longer leak its basetemp, every machine self-heals at the next
  run, and the gate refuses to START below 20 GB free instead of dying an
  hour in. (The volume had 44 GB free on Saturday — closer than anyone
  knew.)
- **Dev engines**: `--reload` is now opt-in (a merge can never restart your
  session's engine again), and script-launched engines die with their
  terminal instead of becoming immortal. An engine with no owner says so
  loudly in its log.
- **Defaults are app-level now** (#4450): every library offers the shipped
  workflows; your own workflows stay where you made them.
