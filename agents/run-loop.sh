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
#   3. Claude outputs <promise>FIXED</promise>
#
# State between iterations flows through:
#   - agents/progress.md (task tracker)
#   - GitHub issues (locking + status)
#   - git commits (code changes)

set -euo pipefail

MAX_ITERATIONS="${1:-10}"
DRY_RUN="${2:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/agents/logs"
PROMPT_FILE="$SCRIPT_DIR/loop-prompt.txt"

# Create logs directory
mkdir -p "$LOG_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Fichero Refactoring Loop — Fresh Context Per Iteration${NC}"
echo -e "${BLUE}  Max iterations: ${MAX_ITERATIONS}${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Check if prompt file exists
if [ ! -f "$PROMPT_FILE" ]; then
    echo -e "${RED}Error: $PROMPT_FILE not found${NC}"
    echo "Creating default prompt file..."
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
    echo -e "${GREEN}Created $PROMPT_FILE${NC}"
fi

check_all_done() {
    if [ -f "$PROJECT_DIR/agents/progress.md" ]; then
        remaining=$(grep -oP 'Remaining \| \K\d+' "$PROJECT_DIR/agents/progress.md" 2>/dev/null || echo "?")
        if [ "$remaining" = "0" ]; then
            return 0  # all done
        fi
    fi
    return 1  # not done
}

for i in $(seq 1 "$MAX_ITERATIONS"); do
    echo ""
    echo -e "${YELLOW}━━━ Iteration $i / $MAX_ITERATIONS ━━━${NC}"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    LOG_FILE="$LOG_DIR/iteration_${i}_${TIMESTAMP}.log"

    # Check if all tasks are already done
    if check_all_done; then
        echo -e "${GREEN}All tasks complete! (Remaining | 0 in progress.md)${NC}"
        break
    fi

    # Show current progress
    if [ -f "$PROJECT_DIR/agents/progress.md" ]; then
        echo -e "${BLUE}Current status:${NC}"
        grep -E '(Completed|Remaining|Blocked|In Progress)' "$PROJECT_DIR/agents/progress.md" 2>/dev/null | head -5
    fi

    if [ "$DRY_RUN" = "--dry-run" ]; then
        echo -e "${YELLOW}[DRY RUN] Would run: claude -p <prompt>${NC}"
        continue
    fi

    # Run Claude with fresh context — pipe prompt via stdin
    echo -e "${BLUE}Starting Claude (fresh context)...${NC}"
    PROMPT=$(cat "$PROMPT_FILE")

    # Run and tee to log file, capture output for completion check
    OUTPUT=$(claude -p "$PROMPT" --allowedTools '*' 2>&1 | tee "$LOG_FILE") || true

    # Check if Claude signaled all complete
    if echo "$OUTPUT" | grep -q "ALL_COMPLETE"; then
        echo -e "${GREEN}Claude reports ALL_COMPLETE — stopping loop${NC}"
        break
    fi

    # Check progress file again after iteration
    if check_all_done; then
        echo -e "${GREEN}All tasks complete after iteration $i!${NC}"
        break
    fi

    echo -e "${GREEN}Iteration $i complete. Log: $LOG_FILE${NC}"

    # Brief pause between iterations
    sleep 2
done

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Loop finished after $i iteration(s)${NC}"
if [ -f "$PROJECT_DIR/agents/progress.md" ]; then
    grep -E '(Completed|Remaining)' "$PROJECT_DIR/agents/progress.md" 2>/dev/null | head -2
fi
echo -e "${BLUE}  Logs: $LOG_DIR/${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
