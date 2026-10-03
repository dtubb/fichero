"""The vision-model LoRA trainer that runs inside a Hugging Face Job (#5398, `compute.tune.lora`).

The GPU half (torch, transformers, peft) runs only there; these pin the parts that decide WHAT the
student learns, which run anywhere: the chat it sees, the loss on the answer alone, the pairs kept
aside, and the refusal to train on nothing.
"""
from __future__ import annotations

import json
import sys

import pytest

from fichero_server.training import hf_vision_lora_train as trainer


def test_the_loss_is_on_the_teachers_answer_alone():
    """WHY: with the prompt in the loss the student spends its training learning to repeat the
    instruction, which it is always given, instead of reading the line."""
    assert trainer.answer_only([11, 12, 13, 14, 15], 3) == [-100, -100, -100, 14, 15]
    assert trainer.answer_only([11, 12], 5) == [-100, -100]


def test_the_student_sees_the_picture_then_the_line_readers_instruction():
    """WHY: the student must be asked exactly what the line reader asks, so it can take the
    teacher's place: one picture, then the instruction, and the teacher's JSON answer to learn."""
    pair = {"image": "lines/a.jpg", "prompt": "Each of the 1 images ...", "answer": '["Yten mas"]'}
    chat = trainer.messages(pair, with_answer=True)
    assert [part["type"] for part in chat[0]["content"]] == ["image", "text"]
    assert chat[0]["content"][1]["text"] == pair["prompt"] and chat[1]["content"][0]["text"] == pair["answer"]
    assert len(trainer.messages(pair, with_answer=False)) == 1


def test_a_few_pairs_are_kept_aside_the_same_way_every_run():
    """WHY: a loss on pairs it never trained on is the only sign, inside the Job, that the student is
    learning rather than memorising; the same seed keeps two runs comparable
    (`compute.tune.proven-on-huggingface-first`)."""
    pairs = [{"n": i} for i in range(200)]
    train, aside = trainer.split(pairs)
    assert len(aside) == 4 and len(train) == 196 and trainer.split(pairs) == (train, aside)
    assert trainer.split(pairs[:10])[1] == []


def test_nothing_to_train_on_fails_the_job(tmp_path, monkeypatch):
    """WHY: a Job that 'succeeds' on no data returns a copy of the base model as if it had learned."""
    monkeypatch.setattr(sys, "argv", ["train", "--data", str(tmp_path), "--out", str(tmp_path / "out")])
    with pytest.raises(SystemExit, match="no line pairs"):
        trainer.main()


def test_pairs_are_read_as_line_pairs_writes_them(tmp_path):
    (tmp_path / "pairs.jsonl").write_text(json.dumps({"image": "lines/a.jpg", "prompt": "p", "answer": "[]"}) + "\n")
    assert trainer.load_pairs(str(tmp_path)) == [{"image": "lines/a.jpg", "prompt": "p", "answer": "[]"}]
