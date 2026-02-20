ralph-loop "Read agents/plan.md for the overall project plan.

Read /progress.md to check task status and identify the next uncompleted task.

Use agent teams for complex multi-step work or sub-agents for focused subtasks. Default to Sonnet/Haiku agents only (never Opus unless explicitly required for the task).

Use GitHub MCP tools to manage issues. Follow the locking mechanism: check for and create GitHub issues with status:in-progress to prevent concurrent orchestrators from selecting the same task.

Read agents/AGENTS.md to understand xCode usage patterns and agent orchestration best practices.

Complete one task at a time. After completing a task:
1. Verify all tests pass
2. Update /progress.md with task completion status
3. Update GitHub issue status from in-progress to complete
4. Output <promise>FIXED</promise>
5. STOP

If a task cannot be completed, document blockers in the GitHub issue and /progress.md before stopping." \
--completion-promise "FIXED" \
--max-iterations 10