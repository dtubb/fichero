#!/bin/bash
MAX_ITERATIONS="$1"
PROJECT_DIR="$2"
PROMPT_FILE="$3"
LOG_DIR="$4"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

cd "$PROJECT_DIR"

echo ""
echo -e "${BOLD}${BLUE}══════════════════════════════════════════════${NC}"
echo -e "${BOLD}${BLUE}  Fichero Loop — max $MAX_ITERATIONS iterations${NC}"
echo -e "${BOLD}${BLUE}  Ctrl-B d to detach | Ctrl-C to stop${NC}"
echo -e "${BOLD}${BLUE}══════════════════════════════════════════════${NC}"

for i in $(seq 1 "$MAX_ITERATIONS"); do
    echo ""
    echo -e "${BOLD}${YELLOW}── Iteration $i / $MAX_ITERATIONS ──${NC}"

    # Check remaining tasks
    if [ -f "$PROJECT_DIR/agents/progress.md" ]; then
        remaining=$(grep 'Remaining' "$PROJECT_DIR/agents/progress.md" 2>/dev/null | grep -o '[0-9]*' | tail -1 || echo "?")
        if [ "$remaining" = "0" ]; then
            echo -e "${GREEN}All tasks complete! (Remaining=0)${NC}"
            break
        fi
        grep -E '(Completed|Remaining|Blocked|In Progress)' "$PROJECT_DIR/agents/progress.md" 2>/dev/null | head -5
    fi

    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    LOG_FILE="$LOG_DIR/iter_${i}_${TIMESTAMP}.log"

    echo -e "${BLUE}Starting Claude...${NC}"
    echo ""

    # Run Claude with full permissions, output visible in this terminal
    # Use script(1) to force a pseudo-tty so Claude streams properly
    # --dangerously-skip-permissions: no permission prompts (safe in this loop context)
    script -q "$LOG_FILE" claude -p "$(cat "$PROMPT_FILE")" \
        --dangerously-skip-permissions \
        --verbose || true

    echo ""

    # Check stop signals in log
    if grep -q "ALL_COMPLETE" "$LOG_FILE" 2>/dev/null; then
        echo -e "${GREEN}ALL_COMPLETE — done!${NC}"
        break
    fi

    # Re-check progress
    if [ -f "$PROJECT_DIR/agents/progress.md" ]; then
        remaining=$(grep 'Remaining' "$PROJECT_DIR/agents/progress.md" 2>/dev/null | grep -o '[0-9]*' | tail -1 || echo "?")
        if [ "$remaining" = "0" ]; then
            echo -e "${GREEN}All tasks complete!${NC}"
            break
        fi
    fi

    if grep -q -E "FIXED|DONE" "$LOG_FILE" 2>/dev/null; then
        echo -e "${GREEN}FIXED — restarting in 3s for next task...${NC}"
    else
        echo -e "${YELLOW}No FIXED signal — restarting in 5s...${NC}"
        sleep 2
    fi

    sleep 3
done

echo ""
echo -e "${BOLD}${BLUE}Loop finished.${NC}"
