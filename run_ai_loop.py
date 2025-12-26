#!/usr/bin/env python3
import subprocess
import json
import sys
import re
import time

# Colors
CYAN = '\033[0;36m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
RED = '\033[0;31m'
MAGENTA = '\033[0;35m'
ITALIC = '\033[3m'
NC = '\033[0m'

TASK = "Follow instructions in @ai/AI_README.md"
TODO_FILE = "/Users/dtubb/code/fichero_main/fichero/ai/TODO.md"
MAX_RUNS = 10

def has_unchecked_todos():
    """Check if TODO.md has any unchecked [ ] items"""
    try:
        with open(TODO_FILE, 'r') as f:
            content = f.read()
            # Look for [ ] pattern (unchecked checkbox)
            return bool(re.search(r'\[ \]', content))
    except FileNotFoundError:
        print(f"{RED}Error: TODO.md not found at {TODO_FILE}{NC}")
        return False

run_count = 0

while has_unchecked_todos() and run_count < MAX_RUNS:
    run_count += 1
    print(f"\n{CYAN}=== Run #{run_count} of {MAX_RUNS} ==={NC}\n")
    
    cmd = [
        "claude", "--print",
        "--verbose",
        "--output-format", "stream-json",
        "--include-partial-messages",
        "--dangerously-skip-permissions",
        TASK
    ]
    
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    
    for line in process.stdout:
        try:
            data = json.loads(line)
            
            if data.get("type") == "stream_event":
                event = data.get("event", {})
                
                if event.get("type") == "content_block_delta":
                    text = event.get("delta", {}).get("text", "")
                    sys.stdout.write(text)
                    sys.stdout.flush()
                            
                elif event.get("type") == "content_block_start":
                    if event.get("content_block", {}).get("type") == "tool_use":
                        tool_name = event.get("content_block", {}).get("name", "")
                        print(f"\n{ITALIC}{YELLOW}🔧 {tool_name}{NC}\n")
                        
        except json.JSONDecodeError:
            pass
    
    process.wait()
    
    print()
    if process.returncode == 0:
        print(f"{GREEN}✓ Run #{run_count} completed{NC}")
    else:
        print(f"{RED}✗ Run #{run_count} failed{NC}")
    
    # Small delay between runs
    time.sleep(2)

print()
if not has_unchecked_todos():
    print(f"{MAGENTA}╔════════════════════════════════════════╗{NC}")
    print(f"{MAGENTA}║   All TODO items completed! 🎉        ║{NC}")
    print(f"{MAGENTA}║   Total runs: {run_count:<27} ║{NC}")
    print(f"{MAGENTA}╚════════════════════════════════════════╝{NC}")
else:
    print(f"{YELLOW}╔════════════════════════════════════════╗{NC}")
    print(f"{YELLOW}║   Max runs reached ({MAX_RUNS})               ║{NC}")
    print(f"{YELLOW}║   Some TODO items remain unchecked    ║{NC}")
    print(f"{YELLOW}╚════════════════════════════════════════╝{NC}")