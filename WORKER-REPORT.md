## 2026-06-28

- Updated `docs/contributor/backend-development-standards.md` to document the
  centralized LLM call path that shipped in #1825.
- Verified against merged code in:
  `fichero-engine/src/fichero/llm.py`,
  `fichero-engine/src/fichero/workflows/tools/agent.py`,
  `fichero-engine/src/fichero/workflows/tools/multi_agent.py`,
  and `fichero-engine/src/fichero/providers.py`.
- Documented three grounded points:
  workflow/tool callers now route through `chat_workflow(...)`, which
  dispatches into the central `chat(...)` / `chat_structured(...)` /
  `chat_with_tools(...)` path in `llm.py`;
  LangChain is the runtime provider integration layer for chat/tool calls;
  LiteLLM is used here for model discovery and pricing metadata, not request
  routing;
  `omlx` / MLX is the OpenAI-compatible local-server path reached through
  `langchain_openai.ChatOpenAI`.
- Ran:
  `~/.venv/bin/mkdocs build --strict`
  -> passed
