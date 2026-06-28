# Worker Report

## 2026-06-28

- Documented the shipped chat retrieval UI from `#2758` in [docs/user/interface-tour.md](/Users/danieltubb/code/fichero-worktrees/ms-docs/docs/user/interface-tour.md).
- Verified the behavior against `ChatView+Extensions.swift`, `MessageCard.swift`, `SidebarChatTypes.swift`, `RetrievalInfoTests.swift`, and the backend retrieval path in `fichero-engine/src/fichero/api/routes/chat.py` plus `fichero-engine/src/fichero/retrieval/graph_rag.py`.
- Captured current behavior only:
  - assistant replies can show a retrieval summary when library search ran
  - citations can list source documents with relevance percentages
  - card and map chat layouts expose the same retrieval/source state in compact forms
  - retrieval/source metadata is not yet restored after conversation reload
- Gate: `~/.venv/bin/mkdocs build --strict` passed.
