# Claude Code adapter: the six answers

1. **System prompt**: appended with `--append-system-prompt "$(cat <scratch>/prompt.md)"`: run inside a `sh -c` wrapper that takes the file and the brief as arguments, so the text is never on the tmux line.
2. **MCP servers**: an `mcp.json` under the scratch path, passed with `--strict-mcp-config --mcp-config=<file>`; nothing else loads.
3. **Model and provider**: `--model <name>`; Anthropic only. No base URL.
4. **Permission mode**: `--dangerously-skip-permissions`, inside the worker user's jail (the OS user and the land gate are the sandbox).
5. **Hooks**: a PreToolUse hook (`scripts/harness_policy_hook.py`) in the generated `settings.json`, and the commit-msg hook.
   `--setting-sources ""` loads no user, project or local settings, only `--settings <generated file>`.
   There is no flag that turns off `CLAUDE.md` loading: the prompt tells the worker those files are not its rules.
6. **Session read**: the Claude Code JSONL, read by `session.parse_session` (tokens and turns, no price).
