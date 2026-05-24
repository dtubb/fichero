# STATE.md — Fichero

## Snapshot

**Branch:** `0.0.2`

## Current Focus

Entity Platform — SwiftUI implementation of five-pane reading layout, KG inspector modes, bidirectional sync.

## In Progress

- Nothing currently running. Ready to restart with Claude Sonnet as direct worker.

## Next Session — Start Here

1. **Restart autonomous loop** — use Claude Sonnet directly (not cheap cascade):
   ```bash
   tmux new-session -d -s fichero
   tmux send-keys -t fichero "python3 /Users/danieltubb/code/fichero-skills/agent-autonomous-loop.py /Users/danieltubb/code/fichero-0.0.2 --agent claude --iterations 20 --max-tasks 1" Enter
   ```
2. **Priority issues in queue**: #1197 (bidirectional 3-pane sync), #1196 (page-scoped KG graph), #1194 (book reading view), #1191 (entity digest), #1188 (resizable content pane — partial SwiftUI work already committed)
3. **Autoloop model strategy**: Python/backend/architectural → Claude Sonnet directly; narrow scoped SwiftUI polish only → cheap cascade (see MEMORY.md cascade model selection)
4. **queue.md clean**: #1188, #1191, #1194 reset to pending — cascade abandoned them without commits

## Blocked

- OpenRouter weekly key quota can hard-stop remote vision/extraction runs (`403 Key limit exceeded`) on some libraries.
