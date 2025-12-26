#!/bin/bash

TASK="Follow instructions in @ai/AI_README.md"

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
ITALIC='\033[3m'
NC='\033[0m' # No Color

echo -e "${CYAN}=== Starting AI Task ===${NC}"
echo ""

claude --print \
       --verbose \
       --output-format stream-json \
       --dangerously-skip-permissions \
       "$TASK" | jq -r --unbuffered '
           if .type == "stream_event" and .event.type == "content_block_delta" then
               .event.delta.text // empty
           elif .type == "stream_event" and .event.type == "content_block_start" and .event.content_block.type == "tool_use" then
               "\n\u001b[3m\u001b[33m🔧 " + .event.content_block.name + "\u001b[0m\n"
           elif .type == "result" then
               "\u001b[35m\n💰 Cost: $" + (.total_cost_usd | tostring) + " | Tokens: " + (.usage.output_tokens | tostring) + "\u001b[0m"
           else
               empty
           end
       '

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ Task completed${NC}"
else
    echo -e "${RED}✗ Task failed${NC}"
fi