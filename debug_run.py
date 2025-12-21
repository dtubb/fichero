#!/usr/bin/env python3
"""Run Fichero with debugpy for VS Code debugging.

Usage:
    1. Run this script: python debug_run.py
    2. In VS Code, select "Fichero: Attach to Running App" and press F5
    3. Set breakpoints in your code
    4. The app will pause when hitting breakpoints

Options:
    --wait    Wait for debugger to attach before starting app
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Start debugpy listener
import debugpy
debugpy.listen(("localhost", 5678))
print("Debugpy listening on localhost:5678")

# Check for --wait flag
if "--wait" in sys.argv:
    print("Waiting for debugger to attach...")
    debugpy.wait_for_client()
    print("Debugger attached!")

# Now start the app
from fichero import main
main()
