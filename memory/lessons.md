# Lessons Learned

(Updated after corrections and mistakes)

## General

- Always check git branch before starting work -- must be on `codex/restructure-api-swiftui`
- Always run /build-and-test before marking anything complete
- Generated files are strictly read-only -- never edit manually

## Backend / Frontend Contracts

- **Envelope pattern is now universal**: All list endpoints return `{items: [...], count: N}` (standardized in #1075)
- **DocumentStore uses APIClient, not FicheroClient**: When writing contract tests that instantiate DocumentStore, use the `APIClient` wrapper type, not `FicheroClient` from generated client
- **DocumentListResponse must be decoded, not bare array**: Swift code calling `api.get("/documents")` must decode `DocumentListResponse` and use `.items`, not `[Document]` directly

## Autoloop

- **Worker timeout kills commits**: Default 60-180s timeout insufficient for multi-file fixes. Use `cascade_loop.py --timeout 7200` for complex issues.
- **Free model works**: `openai/gpt-oss-120b:free` is reliable. Avoid reasoning models (poolside/laguna-m.1:free) - they return empty responses.
- **Vision issues need specs**: Issues labeled `needs-design` must have detailed requirements before free workers can attempt them.
