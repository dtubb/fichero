#!/bin/bash
# Fichero Refactoring Loop — Fresh Context Per Iteration
#
# Usage:
#   ./agents/run-loop.sh                  # default: 10 iterations
#   ./agents/run-loop.sh 5                # custom max iterations
#   ./agents/run-loop.sh 20 --dry-run     # preview without running
#
# How it stops:
#   1. All tasks in agents/progress.md show "Remaining | 0"
#   2. Max iterations reached
#   3. Claude outputs ALL_COMPLETE
#
# State between iterations flows through:
#   - agents/progress.md (task tracker)
#   - GitHub issues (locking + status)
#   - git commits (code changes)
#
# Works with: regular terminal, tmux, tmux -CC (iTerm2)

set -euo pipefail

MAX_ITERATIONS="${1:-10}"
DRY_RUN="${2:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/agents/logs"
PROMPT_FILE="$SCRIPT_DIR/loop-prompt.txt"

# Create logs directory
mkdir -p "$LOG_DIR"

# Detect if colors are supported (disable in tmux -CC or pipes)
if [ -t 1 ] && [ "${TERM:-}" != "dumb" ] && [ -z "${TMUX_CC:-}" ]; then
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    RED='\033[0;31m'
    BLUE='\033[0;34m'
    NC='\033[0m'
else
    GREEN=''
    YELLOW=''
    RED=''
    BLUE=''
    NC=''
fi

log() {
    echo -e "$1"
}

log "${BLUE}========================================================${NC}"
log "${BLUE}  Fichero Refactoring Loop — Fresh Context Per Iteration${NC}"
log "${BLUE}  Max iterations: ${MAX_ITERATIONS}${NC}"
log "${BLUE}========================================================${NC}"

# Check if prompt file exists
if [ ! -f "$PROMPT_FILE" ]; then
    log "${RED}Error: $PROMPT_FILE not found${NC}"
    log "Creating default prompt file..."
    cat > "$PROMPT_FILE" << 'PROMPT'
Read agents/plan.md for the overall project plan.

Read agents/progress.md to check task status and identify the next uncompleted task.

Use agent teams for complex multi-step work or sub-agents for focused subtasks. Default to Sonnet/Haiku agents only (never Opus unless explicitly required).

Use GitHub MCP tools to manage issues. Follow the locking mechanism: check for and create GitHub issues with status:in-progress to prevent concurrent orchestrators from selecting the same task.

Read agents/AGENTS.md to understand Xcode usage patterns.

Complete one task at a time. After completing a task:
1. Verify build passes (BuildProject)
2. Commit and push to remote
3. Update agents/progress.md with completion status
4. Update GitHub issue status to done and close it
5. Say DONE and exit

If a task cannot be completed, document blockers in the GitHub issue and agents/progress.md before stopping.

If ALL remaining tasks in agents/progress.md are done (Remaining | 0), say ALL_COMPLETE and exit.
PROMPT
    log "${GREEN}Created $PROMPT_FILE${NC}"
fi

check_all_done() {
    if [ -f "$PROJECT_DIR/agents/progress.md" ]; then
        # macOS-compatible grep (no -P flag)
        remaining=$(grep 'Remaining' "$PROJECT_DIR/agents/progress.md" 2>/dev/null | grep -o '[0-9]*' | tail -1 || echo "?")
        if [ "$remaining" = "0" ]; then
            return 0  # all done
        fi
    fi
    return 1  # not done
}

LAST_ITERATION=0

for i in $(seq 1 "$MAX_ITERATIONS"); do
    LAST_ITERATION=$i
    echo ""
    log "${YELLOW}--- Iteration $i / $MAX_ITERATIONS ---${NC}"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    LOG_FILE="$LOG_DIR/iteration_${i}_${TIMESTAMP}.log"

    # Check if all tasks are already done
    if check_all_done; then
        log "${GREEN}All tasks complete! (Remaining | 0 in progress.md)${NC}"
        break
    fi

    # Show current progress
    if [ -f "$PROJECT_DIR/agents/progress.md" ]; then
        log "${BLUE}Current status:${NC}"
        grep -E '(Completed|Remaining|Blocked|In Progress)' "$PROJECT_DIR/agents/progress.md" 2>/dev/null | head -5
    fi

    if [ "$DRY_RUN" = "--dry-run" ]; then
        log "${YELLOW}[DRY RUN] Would run: claude -p <prompt>${NC}"
        continue
    fi

    # Run Claude with fresh context
    log "${BLUE}Starting Claude (fresh context)...${NC}"
    PROMPT=$(cat "$PROMPT_FILE")

    # Write output to log file, capture for completion check
    # Use script(1) to handle pseudo-tty issues in tmux -CC
    OUTPUT=$(claude -p "$PROMPT" --allowedTools '*' --verbose 2>&1 | tee "$LOG_FILE") || true

    # Check if Claude signaled all complete
    if echo "$OUTPUT" | grep -q "ALL_COMPLETE"; then
        log "${GREEN}Claude reports ALL_COMPLETE — stopping loop${NC}"
        break
    fi

    # Check progress file again after iteration
    if check_all_done; then
        log "${GREEN}All tasks complete after iteration $i!${NC}"
        break
    fi

    log "${GREEN}Iteration $i complete. Log: $LOG_FILE${NC}"

    # Brief pause between iterations
    sleep 2
done

echo ""
log "${BLUE}========================================================${NC}"
log "${BLUE}  Loop finished after $LAST_ITERATION iteration(s)${NC}"
if [ -f "$PROJECT_DIR/agents/progress.md" ]; then
    grep -E '(Completed|Remaining)' "$PROJECT_DIR/agents/progress.md" 2>/dev/null | head -2
fi
log "${BLUE}  Logs: $LOG_DIR/${NC}"
log "${BLUE}========================================================${NC}"
