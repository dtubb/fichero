"""Shared by the Pi live tests: start Pi in RPC mode against the fake provider; skipped where `pi` is not installed."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from fichero_builder import pi_rpc
from tests import _fake_openai


def live(tmp_path, command: str, *, crash: bool = False, policy: bool = True):
    pi_bin = shutil.which("pi")
    if not pi_bin:
        pytest.skip("pi is not installed")
    base, srv, calls = _fake_openai.serve(command)
    agent = tmp_path / "agent"
    _fake_openai.agent_dir(agent, base)
    wt, scratch = tmp_path / "wt", tmp_path / "scratch"
    wt.mkdir(), scratch.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("FICHERO_PI_")}
    if crash:
        env["FICHERO_PI_POLICY_CRASH"] = "1"
    root = Path(__file__).resolve().parents[2]  # the repo: its harness.toml [policy]
    pi = pi_rpc.start(wt, root=root, scratch=scratch, model="fake-1", provider="fake", session_dir=tmp_path / "sessions",
                      agent_dir=agent, env=env, pi_bin=pi_bin)
    if not policy:
        pi.proc.kill()
        pytest.skip("not used")
    return pi, srv, calls
