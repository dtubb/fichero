# Autonomous run — 2026-08-02 → Tuesday morning

Daniel is on vacation and will not check in until Tuesday. Release authority
granted (GitHub and TestFlight). This file is the durable copy of the plan;
the cron jobs driving it are session-only and die with the tmux session.

## Loops

- **15 min** (`27aa59c3`) — merge lane branches, unblock with a DECISION not a
  question, keep EXACTLY TWO lanes fed, retire before spawning.
- **4 hours** (`bdbdd3d6`) — consolidated build on merged integration (lanes
  cannot build; mechanical breaks accumulate), push to main if green, check
  disk against the 20 GB preflight floor, and ask the question that matters:
  **are the lanes finding the CLASS or patching instances?**

## Two lanes, never more

Daniel: *"no more than two workers at a time… mostly opus, fabel for hard stuff."*

- **lane-crash2 (opus)** — crashes, data integrity, startup, across ALL
  milestones. #4331 first (is the iOS launch crash still live in the build we
  shipped Saturday?), then #110 Connection & Startup, #188 Importer, #116 Sidebar.
- **lane-plan (fabel)** — verify CLI + MCP against a live engine (#4465), then
  write the week plan.

## The three things filed from Daniel's own words, 2026-08-02

- **#4463 — a fifth file mode, MANAGED.** Fichero owns file layout inside an
  iCloud folder, iTunes-style; that folder then becomes a sync channel for iOS.
  **The honest tension, and the thing most likely to eat a year:** this is a
  SECOND consistency model. Today is one server-authoritative engine, one
  writer, clients observing. iCloud sync is two devices both writing offline
  with no authority present. Daniel's own instinct is right — an append-only
  log of INTENTS, not synced database state. Two devices syncing a DuckDB file
  through iCloud is a corrupted database. Managed mode is useful on its own
  first, and is the prerequisite either way.
- **#4464 — every surface supports every interaction.** Not "add VoiceOver":
  one table of surface × interaction × expected behaviour, a test per cell, one
  shared implementation per column. Already proven necessary: three selection
  grammars, four import paths, two drop handlers, two meanings of "folder" in
  one delete menu. Start with the document-inspector lists — Daniel reports a
  live defect there (icons not clickable, operations not working).
- **#4465 — nobody has run the CLI or MCP.** Unit tests passing and a binary
  that works are different claims, and this codebase produced twelve
  "mechanism built, nothing feeding it" defects this week.

## Standing rules for this run

- Lanes never build. The manager builds, every 4 hours and before any release.
- Nobody runs `pytest tests/perf` outside the gate — it seeded this machine to
  11 GB free twice.
- An absence is not an answer. Five times this week a check reported success
  while measuring nothing.
- Fix the class, not the instance.
- Anything needing a live click or a device goes on the Tuesday list, not a guess.

## What Tuesday should look like

The iOS crash question ANSWERED. CLI and MCP either working or with a filed
failure list. A dispatchable week plan. Steady closure on #110/#188/#116 with
SHA evidence. A green build, and a release cut if there is anything worth
testing. Plus `2026-08-01-tuesday-handover.md`, which still stands: ten
click-checks, three decisions only Daniel can make, four items needing live data.
