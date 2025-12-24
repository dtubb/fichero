# Fichero Roadmap

*December 2025*

## -1. Side Bar
- [ ] Add contextual menus
- [ ] Add delete button for items.
- [ ] Add a bottom menu with +, -, and a wheel for settings. like in devon think, e.g. bottom screen shot.png
- [ ] for sidebar, except drag and drop to add to the libray.
- [ ] accept drag and drop to reorder items.

## 0. Workflow Editor
- [ ] Fix the add workflow editor. add folder editor. etc in the sidebar.
- [ ] Make sure we can save and reload.
- [ ] Tool tips for the hover over the icons. 
- [ ] Workout how each popover is constructed.
- [ ] Expose prompts for the various tools, as relevent.
- [ ] Implement tools from past processes.


## 1. Activity Monitor & Task Runner
- [ ] Backend: async task queue with state (pending/running/done/failed)
- [ ] UI: sidebar section showing running tasks, progress, logs
- [ ] Real-time updates (SSE or polling)
- [ ] Start/stop/cancel controls

## 2. Workflow Execution
- [ ] Run workflows, monitor progress
- [ ] Output storage & merging back to library
- [ ] Compare outputs (side-by-side columns)
- [ ] Compare models/prompts on same input

## 3. Multi-Interface Access
- [ ] **CLI**: full access to all features
- [ ] **AppleScript**: scriptable app, Shortcuts support
- [ ] **MCP Server**: expose Fichero tools to other AIs

## 4. MCP Tools in Node Editor
- [ ] Connect to external MCP servers
- [ ] Use tools like Tinderbox, Bookends, web search in workflows
- [ ] Browse & configure MCP tools in inspector

## 5. Apple Platform
- [ ] **Localization**: String catalogs, multiple languages
- [ ] **Accessibility**: VoiceOver, keyboard nav, Dynamic Type

## 6. Comparison UI
- [ ] Multi-column comparison view
- [ ] Diff highlighting
- [ ] Human rating/evaluation interface

## 7. Export
- [ ] Export to Word, PDF, JSON
- [ ] Batch export with templates
- [ ] Export workflow outputs to library

## 8. Tinderbox and DevonThink Connection

## 9. Claude Code Connection

---

### Open Questions
- Where do workflow outputs live before merging?
- Async architecture: in-process vs worker process?
- How to update frontend status efficiently?
