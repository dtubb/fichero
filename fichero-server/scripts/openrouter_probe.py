#!/usr/bin/env python3
"""OpenRouter readiness probe for the A/B harness (#5894): light (one free catalogue GET and one 1-token text call).

  1. The key, the engine's way (`ab_kraken_cloud.ensure_provider_key`: app-supplied, the keychain, the environment, then
     ~/.config/fichero/ab.env). A locked or unreachable keychain (over SSH) is said in words. Never prints a key.
  2. GET https://openrouter.ai/api/v1/models (free): picks, with the date, the cheap tier (Claude Haiku, Gemini Flash), the
     strong tier (Claude Opus, Gemini Pro) and the largest hosted Qwen VL; each needs a vision input and a registry price.
  3. A 1-token text call (max_tokens=1, a text-only prompt) on the cheapest pick; its cost is logged.

  python fichero-server/scripts/openrouter_probe.py [--no-call]
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import re
import sys
import urllib.request
from pathlib import Path

CATALOGUE = "https://openrouter.ai/api/v1/models"
CHAT = "https://openrouter.ai/api/v1/chat/completions"


def _harness():
    path = Path(__file__).with_name("ab_kraken_cloud.py")
    spec = importlib.util.spec_from_file_location("ab_kraken_cloud", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _version(model_id: str) -> tuple:
    """The numbers in an id, so 'claude-haiku-4.5' outranks 'claude-3-haiku'."""
    return tuple(int(n) for n in re.findall(r"\d+", model_id.split("/", 1)[1]))


def sees_images(model: dict) -> bool:
    return "image" in ((model.get("architecture") or {}).get("input_modalities") or [])


def price(model: dict) -> tuple[float, float]:
    p = model.get("pricing") or {}
    return float(p.get("prompt") or 0), float(p.get("completion") or 0)


def newest(models: list[dict], vendor: str, tier: str) -> dict | None:
    """The newest (highest version) vision model of a vendor's tier, e.g. ('anthropic', 'haiku')."""
    found = [m for m in models if m["id"].startswith(vendor + "/") and tier in m["id"].lower() and sees_images(m)
             and ":" not in m["id"] and "preview" not in m["id"].lower()]
    return max(found, key=lambda m: (_version(m["id"]), m["id"]), default=None)


def largest_qwen_vl(models: list[dict]) -> dict | None:
    """The largest hosted Qwen VL: the most parameters named in its id ('235b'), else the dearest."""
    def size(m: dict) -> float:
        named = [float(n) for n in re.findall(r"(\d+(?:\.\d+)?)b", m["id"].lower())]
        return max(named, default=0.0)

    found = [m for m in models if m["id"].startswith("qwen/") and sees_images(m) and "vl" in m["id"].lower()
             and ":free" not in m["id"]]
    return max(found, key=lambda m: (size(m), price(m)[1]), default=None)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-call", action="store_true", help="skip the 1-token call (key lookup and catalogue only)")
    args = ap.parse_args()
    ab = _harness()
    today = datetime.date.today().isoformat()

    try:
        source = ab.ensure_provider_key("openrouter")
    except SystemExit as exc:
        print(f"KEY: {exc}")
        return 2
    print(f"KEY: found via {source}")

    with urllib.request.urlopen(urllib.request.Request(CATALOGUE, headers={"User-Agent": "fichero-probe"}), timeout=30) as r:
        models = json.load(r)["data"]
    print(f"CATALOGUE {today}: {len(models)} models")
    picks = {
        "cheap Claude (Haiku)": newest(models, "anthropic", "haiku"),
        "cheap Gemini (Flash)": newest(models, "google", "flash"),
        "strong Claude (Opus)": newest(models, "anthropic", "opus"),
        "strong Gemini (Pro)": newest(models, "google", "pro"),
        "hosted Qwen VL (largest)": largest_qwen_vl(models),
    }
    missing = 0
    for label, model in picks.items():
        if model is None:
            print(f"  {label}: none found")
            missing += 1
            continue
        pin, pout = price(model)
        known = ab.cost_of("openrouter", model["id"], 1, 1) is not None
        print(f"  {label}: openrouter:{model['id']}  ${pin * 1e6:.2f} / ${pout * 1e6:.2f} per M tokens  "
              f"registry price: {'yes' if known else 'MISSING (add it before any real call)'}")
        missing += not known
    if args.no_call:
        return 1 if missing else 0

    cheapest = min((m for m in picks.values() if m), key=lambda m: price(m)[1])
    from fichero_server.llm import get_api_key

    key = get_api_key("openrouter")
    body = json.dumps({"model": cheapest["id"], "max_tokens": 1,
                       "messages": [{"role": "user", "content": "Reply with one word: ok"}]}).encode()
    request = urllib.request.Request(CHAT, data=body, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as r:
            answer = json.load(r)
    except Exception as exc:  # noqa: BLE001 -- the reason is the output; the key is never in it
        print(f"CALL: {type(exc).__name__}: {ab.scrub(str(exc))[:200]}")
        return 3
    usage = answer.get("usage") or {}
    pin, pout = price(cheapest)
    cost = usage.get("cost", usage.get("prompt_tokens", 0) * pin + usage.get("completion_tokens", 0) * pout)
    print(f"CALL on {cheapest['id']}: 1-token answer OK; usage {usage.get('prompt_tokens')} in / "
          f"{usage.get('completion_tokens')} out; cost ${cost:.6f}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
