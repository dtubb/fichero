# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = ["torch>=2.5", "torchvision", "transformers>=4.57,<5", "peft>=0.15", "accelerate>=1.3", "pillow>=11"]
# ///
"""Fine-tune a vision model with LoRA INSIDE a Hugging Face Job (#5398, `compute.tune.lora`). Shipped
with Fichero; sent as the Job's script by `training.hf_jobs`, never edited per run.

    --data   a training set with line pairs (`training.line_pairs`): pairs.jsonl and lines/
    --out    out/adapter (always: `compute.tune.adapter-always-returns`) and out/merged (the base with
             the adapter merged in, bf16, which the Mac converts for MLX: `compute.tune.convert-for-mlx`)
    --base   the bf16 base model on the Hub (Qwen/Qwen3-VL-8B-Instruct by default; any image-text-to-text
             model transformers loads, e.g. Qwen/Qwen2.5-VL-7B-Instruct or datalab-to/chandra)

Each pair is one line picture, the line reader's own instruction for one picture, and the answer; the
loss is on the answer only. `--arm` chooses what the answer holds in a reasons set (#4642): the checked
transcription alone, with the palaeographer's reasons, with its thinking, or a review of a draft. Nothing here is one model family's: the model is loaded by
`AutoModelForImageTextToText`, and the chat is written by the processor's own template. A few pairs are kept aside and their loss is printed after
each epoch. Exits non-zero with nothing to train on.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys

#: The parts of the language model the adapter learns. In the Qwen-VL families (Qwen2.5-VL, Qwen3-VL and
#: the models built on them) the vision tower's layers have other names (qkv, proj, fc), so it is left as
#: it is.
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def load_pairs(data_dir: str) -> list[dict]:
    path = os.path.join(data_dir, "pairs.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def select(pairs: list[dict], arm: str = "answer", *, all_lines: bool = False) -> list[dict]:
    """The pairs this student learns from, as (image, prompt, answer). A pair with `arms` (a reasons set,
    `training.line_pairs`) gives that arm's prompt and answer; an A/B arm keeps only the lines every
    reasoning arm covers (`in_every_arm`) unless `all_lines`, so the arms differ by the reasons alone.
    The `review` arm is its own task and takes every line it has."""
    chosen = []
    for pair in pairs:
        if "arms" not in pair:
            if arm == "answer":
                chosen.append(pair)
            continue
        if arm not in pair["arms"]:
            continue
        if arm != "review" and not all_lines and not pair.get("in_every_arm", True):
            continue
        chosen.append({**pair, **pair["arms"][arm]})
    return chosen


def split(pairs: list[dict], aside: float = 0.02, seed: int = 0) -> tuple[list[dict], list[dict]]:
    """Training pairs and a few kept aside for a loss to watch; at least one aside when there are 50+."""
    shuffled = pairs[:]
    random.Random(seed).shuffle(shuffled)
    n = max(1, int(len(shuffled) * aside)) if len(shuffled) >= 50 else 0
    return shuffled[n:], shuffled[:n]


def messages(pair: dict, *, with_answer: bool) -> list[dict]:
    """The chat the student sees: the picture and the instruction; the teacher's answer to learn."""
    chat = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": pair["prompt"]}]}]
    if with_answer:
        chat.append({"role": "assistant", "content": [{"type": "text", "text": pair["answer"]}]})
    return chat


def answer_only(labels: list[int], prompt_length: int) -> list[int]:
    """Labels with the prompt's tokens masked (-100): the loss is on the answer alone."""
    return [-100] * min(prompt_length, len(labels)) + labels[prompt_length:]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--base", default="Qwen/Qwen3-VL-8B-Instruct")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--accumulate", type=int, default=8)
    parser.add_argument("--arm", default="answer", help="answer, why, thinking or review (a reasons set's arm)")
    parser.add_argument("--all-lines", action="store_true", help="an A/B arm on every line it has, not only "
                        "the lines every arm covers")
    args = parser.parse_args()

    pairs = select(load_pairs(args.data), args.arm, all_lines=args.all_lines)
    print(f"{len(pairs)} line pairs for the {args.arm} arm", flush=True)
    if not pairs:
        sys.exit(f"no line pairs for the {args.arm} arm under {args.data}")
    train, aside = split(pairs)

    import torch
    from peft import LoraConfig, get_peft_model
    from PIL import Image
    from transformers import AutoModelForImageTextToText, AutoProcessor

    processor = AutoProcessor.from_pretrained(args.base)
    model = AutoModelForImageTextToText.from_pretrained(args.base, torch_dtype=torch.bfloat16, device_map="cuda")
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model = get_peft_model(model, LoraConfig(r=args.rank, lora_alpha=2 * args.rank, lora_dropout=0.05,
                                             target_modules=TARGET_MODULES, task_type="CAUSAL_LM"))
    model.print_trainable_parameters()

    def encode(pair: dict) -> dict:
        image = Image.open(os.path.join(args.data, pair["image"])).convert("RGB")
        full = processor.apply_chat_template(messages(pair, with_answer=True), tokenize=False)
        prompt = processor.apply_chat_template(messages(pair, with_answer=False), tokenize=False,
                                               add_generation_prompt=True)
        batch = processor(text=[full], images=[image], return_tensors="pt")
        prompt_length = processor(text=[prompt], images=[image], return_tensors="pt")["input_ids"].shape[1]
        batch["labels"] = torch.tensor([answer_only(batch["input_ids"][0].tolist(), prompt_length)])
        return {k: v.to("cuda") for k, v in batch.items()}

    trainable = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=args.lr)
    for epoch in range(1, args.epochs + 1):
        model.train()
        random.Random(epoch).shuffle(train)
        running = 0.0
        for step, pair in enumerate(train, 1):
            loss = model(**encode(pair)).loss / args.accumulate
            loss.backward()
            running += loss.item()
            if step % args.accumulate == 0 or step == len(train):
                optimizer.step()
                optimizer.zero_grad()
            if step % 200 == 0:
                print(f"epoch {epoch} step {step}/{len(train)} loss {running * args.accumulate / step:.4f}", flush=True)
        if aside:
            model.eval()
            with torch.no_grad():
                held = sum(model(**encode(pair)).loss.item() for pair in aside) / len(aside)
            print(f"epoch {epoch} loss on {len(aside)} pairs kept aside: {held:.4f}", flush=True)

    model.save_pretrained(os.path.join(args.out, "adapter"))
    merged = model.merge_and_unload()
    merged.save_pretrained(os.path.join(args.out, "merged"), safe_serialization=True, max_shard_size="5GB")
    processor.save_pretrained(os.path.join(args.out, "merged"))
    print("saved adapter and merged model", flush=True)


if __name__ == "__main__":
    main()
