#!/usr/bin/env bash
# Usage: scripts/check_pytest_pin.sh <python>   (any machine: the gate, the M4 script, the iMac's own script)
# Exit 0 when <python> has a pytest that runs the suite; 2, with the line to fix it, when it has pytest 9.2.0 (fails
# test_perf_disk_reclaim, #6320) or no pytest-asyncio (every async test errors). 9.0.x and 9.1.x run it. GATE_ALLOW_PYTEST=1 runs anyway.
py="${1:?usage: check_pytest_pin.sh <python>}"
[[ -n "${GATE_ALLOW_PYTEST:-}" ]] && exit 0
pt="$("$py" -c 'import pytest; print(pytest.__version__)' 2>/dev/null)"
if [[ -z "$pt" ]]; then echo "gate: $py has no pytest: $py -m pip install 'pytest==9.1.1' 'pytest-asyncio==1.4.0'" >&2; exit 2; fi
if [[ "$pt" == "9.2.0" ]]; then echo "gate: pytest is 9.2.0 and fails test_perf_disk_reclaim: $py -m pip install 'pytest==9.1.1' (GATE_ALLOW_PYTEST=1 to run anyway)" >&2; exit 2; fi
"$py" -c 'import pytest_asyncio' 2>/dev/null || { echo "gate: $py has no pytest-asyncio: $py -m pip install 'pytest-asyncio==1.4.0'" >&2; exit 2; }
