"""The vLLM offline-batch reader (`compute.hpc.vllm-offline-reader`): one model load, one call per page."""
from __future__ import annotations

import sys
import types

from PIL import Image

from fichero_server.remote_read import runner
from fichero_server.remote_read.package import ReadStep


def _fake_vllm(monkeypatch, answers):
    calls = {"loaded": [], "chats": []}

    class LLM:
        def __init__(self, **kw):
            calls["loaded"].append(kw)

        def chat(self, messages, sampling_params=None):
            calls["chats"].append(len(messages))
            return [types.SimpleNamespace(outputs=[types.SimpleNamespace(text=answers.pop(0))]) for _ in messages]

    mod = types.ModuleType("vllm")
    mod.LLM, mod.SamplingParams = LLM, lambda **kw: kw
    monkeypatch.setitem(sys.modules, "vllm", mod)
    return calls


def test_every_line_of_a_page_goes_in_one_batched_call_and_the_model_loads_once(monkeypatch):
    calls = _fake_vllm(monkeypatch, ['["uno"]', '["dos"]', "[null]", '["x"]'])
    step = {"model": "/m/student", "prompt": "Read the line.", "tensor_parallel": 2}
    ask = runner.vllm_batch_asker(step)
    pics = [Image.new("RGB", (40, 10)) for _ in range(3)]
    assert ask(pics) == ["uno", "dos", None]  # a line with no writing is None
    ask(pics[:1])
    assert len(calls["loaded"]) == 1 and calls["loaded"][0]["tensor_parallel_size"] == 2
    assert calls["chats"] == [3, 1]


def test_the_step_says_which_engine_and_the_package_carries_it():
    step = ReadStep(reader="vlm", card="c", model="m", prompt="p", engine="vllm")
    assert step.describe()["engine"] == "vllm"
    assert "engine" not in ReadStep(reader="kraken", card="c", model_file="/x/y.mlmodel").describe()
