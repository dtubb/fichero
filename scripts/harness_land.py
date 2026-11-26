#!/usr/bin/env python3
"""Wrapper: the script lives in the builder package (fichero-builder/fichero_builder/scripts/harness_land.py); this keeps the old path working. Same argv, stdin and exit code."""
import os
import sys
from pathlib import Path

target = Path(__file__).resolve().parents[1] / "fichero-builder" / "fichero_builder" / "scripts" / Path(__file__).name
os.execv(sys.executable, [sys.executable, str(target), *sys.argv[1:]])
