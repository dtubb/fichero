# STATE.md — Fichero

## Snapshot

**Branch:** `0.0.2`

## Current Focus

Entity Platform — SwiftUI implementation of five-pane reading layout, KG inspector modes, bidirectional sync.

## Completed This Session

- **#1199** (14eef9d5): Persistent inspector — window-level HStack sibling, stable across all views
- **#1189** (33f0338a): Five-pane reading layout — auto-activates when PDF has page children
- **#1190** (797ff7d0): KG inspector Text mode — bold-name + semicolon SVO prose digest, Text/List toggle
- **Autoloop** updated: now defaults to `pi --provider openrouter --model qwen/qwen3-coder:free` (no more Anthropic models)

## In Progress

- Autoloop running in `tmux:fichero → autoloop` with pi+openrouter (qwen3-coder:free)
- 6 pending backend issues in `agent-work/queue.md`

## Next Session — Start Here

1. **#1197**: Bidirectional three-pane sync — `ClaimFocusState` observable at window level; clicking claim in any pane syncs PDF + content + inspector
2. **#1196**: Page-scoped KG graph in Map tab (~8 nodes default, scope pills)
3. **#1194**: Book reading view
4. **Autoloop** — check queue progress; restart if needed with:
   ```bash
   python3 /Users/danieltubb/code/fichero-skills/agent-autonomous-loop.py \
     /Users/danieltubb/code/fichero-0.0.2 \
     --agent pi --provider openrouter --model qwen/qwen3-coder:free \
     --iterations 20 --max-tasks 1
   ```

## Blocked

- OpenRouter weekly key quota can hard-stop remote vision/extraction runs (`403 Key limit exceeded`) on some libraries.
- 2026-05-24: `/session-start-auto` blocked by dirty source working tree (`fichero/fichero/Models/FeatureManager.swift`, `fichero/fichero/Views/ContentView+Actions.swift`, `fichero/fichero/Views/ContentView.swift`, plus untracked `fichero/fichero/Models/ClaimFocusState.swift`). Clean or commit these changes before autonomous task execution.
