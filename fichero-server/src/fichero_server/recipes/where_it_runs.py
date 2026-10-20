"""Where a candidate can run and what it needs there (`source.onboard.model-search-says-where-it-runs-and-what-it-needs`,
#5976): this Mac, Hugging Face Jobs, each cluster set up here, or the provider of a cloud model. A pure function of the
card and three facts passed in (this Mac's memory, whether a Hugging Face account is set up, the cluster names), so it is
tested without a network. A place a card cannot use says why in words. The cluster is listed for Kraken readers and
vision-language models (the two readers `remote_read` has), but the app's key and sign-in step for a cluster are not built
(#5238): the option says so in `blocked`, and a send stays refused until they are."""
from __future__ import annotations

from typing import Any

from fichero_server.recipes.assemble import Card

THIS_MAC, HF_JOBS, CLUSTER, PROVIDER = "this-mac", "hf-jobs", "cluster", "provider"
HF_NAME = "Hugging Face Jobs"
CLUSTER_BLOCKED = ("sending pages from the app to a cluster waits for the app's key and sign-in step (#5238); "
                   "it is not refused for the model")
NO_HF = "add a Hugging Face token in Settings › AI to run it there"


def _option(place: str, name: str, can: bool, needs: str = "", why: str = "", blocked: str = "") -> dict[str, Any]:
    return {"place": place, "name": name, "can": can, "needs": needs, "why": why, "blocked": blocked}


def _gb(value: float) -> str:
    return f"{value:.0f} GB" if value >= 10 else f"{value:.1f} GB"


def _kind(card: Card) -> str:
    from fichero_server.recipes.discovery import REMOTE_RUNS_ON

    if not card.runs_here:
        return "unrunnable"
    if card.runs_on.startswith("cloud:") and card.runs_on != REMOTE_RUNS_ON:
        return "cloud"
    if card.runs_on == REMOTE_RUNS_ON:
        return "vlm"
    pin = card.pin
    if set(pin) & {"zenodo", "kraken_hf", "trained", "kraken_version", "builtin"}:
        return "kraken"
    if pin.get("hf"):
        return "mlx"
    return "other"


def places_it_can_run(card: Card, *, this_mac_gb: float | None, hf_ready: bool,
                      clusters: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
    """The options, in the order this Mac, Hugging Face Jobs, each cluster."""
    kind = _kind(card)
    if kind == "unrunnable":
        why = card.cannot_run_because or "this build cannot run it yet"
        return [_option(THIS_MAC, "this Mac", False, why=why), _option(HF_JOBS, HF_NAME, False, why=why),
                *[_option(CLUSTER, c, False, why=why) for c in clusters]]
    if kind == "cloud":
        provider = card.runs_on.split(":", 1)[1]
        return [_option(PROVIDER, provider, True, needs="an account and key at the provider; the pages leave this Mac")]
    size = f"about {_gb(card.size_gb)} to download" if card.size_gb else "size not stated"
    if kind == "kraken":
        return [_option(THIS_MAC, "this Mac", True, needs=f"Kraken, which ships with Fichero; {size}"),
                _option(HF_JOBS, HF_NAME, hf_ready, needs="a Hugging Face account; Kraken runs in the Job",
                        why="" if hf_ready else NO_HF),
                *[_option(CLUSTER, c, True, needs="Kraken installed in the job's environment; a login to the cluster",
                          blocked=CLUSTER_BLOCKED) for c in clusters]]
    if kind == "vlm":
        needs = f"a GPU with room for about {_gb(card.size_gb)} of weights" if card.size_gb else "a GPU; size not stated"
        return [_option(THIS_MAC, "this Mac", False, why="it has no MLX build, and this Mac runs MLX builds"),
                _option(HF_JOBS, HF_NAME, hf_ready, needs=needs, why="" if hf_ready else NO_HF),
                *[_option(CLUSTER, c, True, needs=needs + "; transformers or vLLM", blocked=CLUSTER_BLOCKED)
                  for c in clusters]]
    if kind == "mlx":
        needs = f"{_gb(card.memory_gb)} of unified memory" if card.memory_gb else "memory not stated"
        fits = not (card.memory_gb and this_mac_gb is not None and card.memory_gb > this_mac_gb)
        why = "" if fits else f"needs {_gb(card.memory_gb)}; this Mac has {_gb(this_mac_gb or 0)}"
        mlx_only = "an MLX build runs only on a Mac"
        return [_option(THIS_MAC, "this Mac", fits, needs=needs, why=why),
                _option(HF_JOBS, HF_NAME, False, why=mlx_only),
                *[_option(CLUSTER, c, False, why=mlx_only) for c in clusters]]
    return [_option(THIS_MAC, "this Mac", True, needs=size)]
