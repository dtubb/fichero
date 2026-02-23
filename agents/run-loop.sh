#!/bin/bash
# Ralph Loop — Visible iTerm2 Windows with Streaming Output
#
# Usage:
#   ./agents/run-loop.sh                  # default: 10 iterations
#   ./agents/run-loop.sh 5                # custom max iterations
#   ./agents/run-loop.sh 10 --force       # skip completion check
#
# Each iteration opens an iTerm2 window with real-time streaming output.
# Auto-exits when Claude finishes, then opens the next iteration.

set -euo pipefail

MAX_ITERATIONS="${1:-10}"
FORCE="${2:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/agents/logs"
PROMPT_FILE="$SCRIPT_DIR/loop-prompt.txt"
SIGNAL_DIR="$PROJECT_DIR/agents/.signals"

mkdir -p "$LOG_DIR" "$SIGNAL_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'
log() { echo -e "$1"; }

log ""
log "${BOLD}${BLUE}══════════════════════════════════════════════════${NC}"
log "${BOLD}${BLUE}  Ralph Loop — Streaming iTerm2 Windows${NC}"
log "${BOLD}${BLUE}  Max iterations: ${MAX_ITERATIONS}${NC}"
log "${BOLD}${BLUE}══════════════════════════════════════════════════${NC}"

# Check/create prompt file
if [ ! -f "$PROMPT_FILE" ]; then
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
        remaining=$(grep -E '^\| *Remaining *\|' "$PROJECT_DIR/agents/progress.md" 2>/dev/null | grep -o '[0-9]*' | head -1 || echo "?")
        [ "$remaining" = "0" ] && return 0
    fi
    return 1
}

show_progress() {
    if [ -f "$PROJECT_DIR/agents/progress.md" ]; then
        log "  ${CYAN}Progress:${NC}"
        grep -E '^\| *(Completed|Remaining|Blocked|In Progress) *\|' "$PROJECT_DIR/agents/progress.md" 2>/dev/null | while read -r line; do
            log "    $line"
        done
    fi
}

# ── Main loop ───────────────────────────────────────────
LAST_ITERATION=0

for i in $(seq 1 "$MAX_ITERATIONS"); do
    LAST_ITERATION=$i
    log ""
    log "${BOLD}${YELLOW}── Iteration $i / $MAX_ITERATIONS ──${NC}"

    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    LOG_FILE="$LOG_DIR/iteration_${i}_${TIMESTAMP}.log"
    SIGNAL_FILE="$SIGNAL_DIR/iter_${i}_done"
    rm -f "$SIGNAL_FILE"

    if [ "$FORCE" != "--force" ] && check_all_done; then
        log "${GREEN}  All tasks complete! (Remaining | 0)${NC}"
        break
    fi

    show_progress

    # Copy prompt to temp file (avoids quoting issues in heredoc)
    PROMPT_TMP=$(mktemp /tmp/ralph_prompt_XXXXXX)
    cp "$PROMPT_FILE" "$PROMPT_TMP"

    # Create runner script for the iTerm2 window
    RUNNER=$(mktemp /tmp/ralph_iter_XXXXXX)
    chmod +x "$RUNNER"

    # Write runner — variables from THIS shell expand, inner $ are escaped
    cat > "$RUNNER" << RUNNER_EOF
#!/bin/bash
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Ralph Loop — Iteration $i / $MAX_ITERATIONS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$PROJECT_DIR"
PROMPT=\$(cat "$PROMPT_TMP")

# Stream Claude output in real-time using stream-json
# -p auto-exits when done, stream-json streams as tokens arrive
# jq extracts readable text and tool names for display
claude -p "\$PROMPT" \\
    --dangerously-skip-permissions \\
    --verbose \\
    --output-format stream-json \\
    --include-partial-messages \\
    2>"$LOG_FILE.stderr" \\
    | tee "$LOG_FILE" \\
    | while IFS= read -r line; do
        type=\$(echo "\$line" | jq -r '.type // empty' 2>/dev/null)
        case "\$type" in
            stream_event)
                evt=\$(echo "\$line" | jq -r '.event.type // empty' 2>/dev/null)
                case "\$evt" in
                    content_block_delta)
                        dt=\$(echo "\$line" | jq -r '.event.delta.type // empty' 2>/dev/null)
                        if [ "\$dt" = "text_delta" ]; then
                            printf '%s' "\$(echo "\$line" | jq -r '.event.delta.text')"
                        fi
                        ;;
                    content_block_start)
                        bt=\$(echo "\$line" | jq -r '.event.content_block.type // empty' 2>/dev/null)
                        if [ "\$bt" = "tool_use" ]; then
                            tn=\$(echo "\$line" | jq -r '.event.content_block.name // empty' 2>/dev/null)
                            printf '\n\033[0;36m[%s]\033[0m ' "\$tn"
                        fi
                        ;;
                esac
                ;;
            result)
                echo ""
                err=\$(echo "\$line" | jq -r '.is_error // false' 2>/dev/null)
                if [ "\$err" = "true" ]; then
                    echo "  [ERROR]"
                else
                    echo "  [DONE]"
                fi
                ;;
        esac
    done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Iteration $i complete — closing in 3s"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

touch "$SIGNAL_FILE"
sleep 3
RUNNER_EOF

    # Open in iTerm2 window
    osascript << APPLE_EOF &
tell application "iTerm2"
    set newWindow to (create window with default profile)
    tell current session of newWindow
        set name to "Ralph #$i"
        write text "bash '$RUNNER'"
    end tell
    repeat
        delay 5
        try
            do shell script "test -f '$SIGNAL_FILE' && echo done"
            exit repeat
        end try
    end repeat
    delay 4
    close newWindow
end tell
APPLE_EOF

    log "  ${GREEN}Opened iTerm2 window: Ralph #${i}${NC}"

    # Wait for signal
    wait_count=0
    while [ ! -f "$SIGNAL_FILE" ]; do
        sleep 2
        wait_count=$((wait_count + 1))
        if [ $((wait_count % 15)) -eq 0 ]; then
            log "  ${CYAN}⏳ Running... ($((wait_count * 2))s)${NC}"
        fi
    done
    wait 2>/dev/null || true

    rm -f "$RUNNER" "$SIGNAL_FILE" "$PROMPT_TMP"

    # Check log for ALL_COMPLETE
    if grep -q "ALL_COMPLETE" "$LOG_FILE" 2>/dev/null; then
        log "  ${GREEN}Claude reports ALL_COMPLETE — stopping${NC}"
        break
    fi

    if [ "$FORCE" != "--force" ] && check_all_done; then
        log "  ${GREEN}All tasks complete after iteration $i!${NC}"
        break
    fi

    log "  ${GREEN}Iteration $i done. Log: $LOG_FILE${NC}"
    sleep 2
done

log ""
log "${BOLD}${BLUE}══════════════════════════════════════════════════${NC}"
log "${BOLD}${BLUE}  Finished after $LAST_ITERATION iteration(s)${NC}"
show_progress
log "${BOLD}${BLUE}  Logs: agents/logs/${NC}"
log "${BOLD}${BLUE}══════════════════════════════════════════════════${NC}"

rm -rf "$SIGNAL_DIR"
