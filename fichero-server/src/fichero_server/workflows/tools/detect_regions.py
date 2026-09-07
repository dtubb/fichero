"""
Detect Regions Tool

Bboxes-first (Daniel, 2026-08-11): every transcribe workflow gets bounding
boxes BEFORE the transcriber runs. This tool is that first pass — on-device
Apple Vision OCR with geometry (no LLM, no network), persisted per page as
a ``regions`` artifact whose ``ocr_geometry`` carries normalized top-left-
origin line/word boxes. The preview overlay reads the same OCRGeometryResult
shape it already reads from transcription artifacts, and downstream
transcribers can crop to or attribute spans against the detected regions
regardless of which provider transcribes.

Reuses process_vision's Apple branch wholesale — per-file bounded fan-out,
PDF page propagation, artifact upsert — by forcing an apple provider config;
the node's own llm_config is deliberately ignored (this step must stay
local and free even in an all-cloud workflow).
"""

from __future__ import annotations

import logging
from typing import Any

from fichero_server.workflows.types import DataType, PortDef, State
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.llm_base import BASE_OUTPUT_PORTS
from fichero_server.workflows.tools.vision_base import (
    VISION_INPUT_PORTS,
    VisionToolConfig,
    process_vision,
)
from fichero_server.llm import LLMConfig

logger = logging.getLogger(__name__)

TOOL_CONFIG = VisionToolConfig(
    artifact_type="regions",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=True,
)

DETECT_REGIONS_CONFIG = {
    "language": {
        "type": "string",
        "default": "en",
        "description": (
            "Recognition locale hint for Apple Vision (an OCR hint, not a "
            "claim about the document)"
        ),
    },
    "provider": {
        "type": "string",
        "default": "apple",
        "enum": ["apple", "vlm", "kraken"],
        "description": (
            "apple: free on-device Vision OCR (measured boxes). vlm: send the "
            "page to the vision model chosen in the Run Workflow menu (e.g. an "
            "OpenRouter model) and ask IT for word boxes — for hands Apple "
            "cannot read. VLM boxes are claimed, not measured; replies whose "
            "box text is absent from their own transcription are rejected "
            "whole rather than rendered. kraken: on-device neural LINE "
            "segmentation (a polygon + baseline per line, no text) for "
            "historical hands Apple Vision localises badly — needs the Kraken "
            "runtime installed from Settings."
        ),
    },
}


@register_tool(
    name="detect_regions",
    parallelism="elementwise",
    display_name="Detect Regions",
    description=(
        "Finds WHERE the words are, on-device and free. Apple Vision reads the "
        "page locally to locate line and word boxes, so it does produce text — "
        "that text is a by-product of finding the boxes, not a transcription: "
        "it never replaces the page's transcript, and no model is called. Runs "
        "before a transcriber so every box exists up front."
    ),
    category="vision",
    icon="rectangle.dashed.badge.record",
    color="purple",
    uses_llm=False,
    supports_batch=True,
    input_ports=VISION_INPUT_PORTS,
    # The pass-through outputs the body already returns. Without the port
    # DECLARATIONS a preset cannot draw the edge the docstring describes:
    # "Edge references unknown source port 'documents'" is a validation error,
    # so a chain that annotates and then consumes the annotation could not be
    # shipped as a preset at all.
    output_ports=BASE_OUTPUT_PORTS + [
        PortDef(
            id="files", name="Files", port_type="output", data_type=DataType.ARRAY,
            description="The input files, untouched — this step annotates.",
        ),
        PortDef(
            id="documents", name="Documents", port_type="output",
            data_type=DataType.JSON,
            description="The input documents, untouched — this step annotates.",
        ),
    ],
    config_schema=DETECT_REGIONS_CONFIG,
    config_defaults={"language": "en"},
    sort_order=4,
    tested=True,
)
async def detect_regions(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Detect text regions with Apple Vision and persist them as artifacts."""
    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])

    # Set only when this run SUBSTITUTES the configured Vision tier default for
    # an absent run/step choice — so a default that cannot serve fails loud and
    # named below, never as an opaque "All parallel branches failed" (Fix A,
    # Daniel 2026-09-07 no-silent-substitution).
    configured_default: LLMConfig | None = None

    provider = inputs.get("provider", "apple")
    use_vlm = provider == "vlm"
    use_kraken = provider == "kraken"
    if use_kraken:
        # Kraken's own neural segmenter — no LLM, no prompt. It reads nothing;
        # the baseline/polygon geometry is the whole output.
        prompt = ""
        effective_llm = LLMConfig(provider="kraken", model="kraken-blla")
    elif use_vlm:
        # The boxes prompt is transcribe's own (function-local import: the
        # two tools import each other, both late, so neither loads first).
        from fichero_server.workflows.tools.transcribe import (  # noqa: PLC0415
            _build_prompt,
        )
        prompt = _build_prompt(inputs.get("language", "auto"), return_boxes=True)
        effective_llm = llm_config
        # "Missing" is not the only unusable config here (Daniel, 2026-09-01:
        # "Detect Regions with a VLM on Apple Vision fails"). Apple Vision is
        # RECOGNITION-only: it ignores the prompt and returns plain OCR text,
        # so the boxes prompt built just above is never asked and the geometry
        # parser downstream gets a transcript where it expects JSON — a silent
        # regions artifact with no boxes rather than an error. This tool
        # registers supports_apple_vision=True (its Apple branch is the whole
        # point), which disarms every downstream refusal, so the substitution
        # has to happen HERE.
        from fichero_server.llm import (  # noqa: PLC0415
            is_recognition_only_vision_model,
        )
        if not effective_llm.provider or is_recognition_only_vision_model(
            effective_llm.provider, effective_llm.model or ""
        ):
            # The tool registers uses_llm=False (true for the Apple default),
            # so the builder never resolves a vision default for VLM mode —
            # resolve the Settings vision tier here instead.
            from fichero_server.llm import (  # noqa: PLC0415
                resolve_model_alias_for_capability,
            )
            prov, mod = resolve_model_alias_for_capability(
                "$vision_medium", "", required_capability="vision"
            )
            if is_recognition_only_vision_model(prov, mod or ""):
                # The configured Vision tier is ITSELF Apple Vision. Say so
                # rather than running a VLM preset on a model that cannot
                # answer a prompt — the failure it produced was a regions
                # artifact that looked fine and had no geometry.
                raise ValueError(
                    "Detect Regions (VLM) needs a vision model that can answer "
                    "a prompt, but the configured Vision default is Apple "
                    "Vision — on-device OCR, which returns recognized text and "
                    "ignores the prompt. Set a vision-capable LLM as the Vision "
                    "default in Settings, pin one on this step, or run the "
                    "plain Detect Regions preset, which uses Apple Vision's own "
                    "geometry."
                )
            effective_llm = LLMConfig(provider=prov, model=mod)
            # This is the configured tier DEFAULT, not a model the user picked
            # for this run. If it cannot serve (e.g. an unpicked local MLX model
            # that isn't installed), fail loud and named after the call rather
            # than letting it die as a bare "not installed" branch error. When
            # the run/step DID pick a model it reaches this node via the R-11
            # override (validation.apply_run_model_override) and never enters
            # this branch — Gemini is used, full stop.
            configured_default = effective_llm
    else:
        # The Apple branch never sends a prompt to a model; kept explicit so
        # the local path cannot silently inherit a transcription prompt.
        prompt = ""
        # Forced local provider — see module docstring.
        effective_llm = LLMConfig(provider="apple", model="apple-vision")

    result = await process_vision(
        files=files,
        documents=documents,
        prompt=prompt,
        llm_config=effective_llm,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        vision_mode="kraken" if use_kraken else ("llm" if use_vlm else "apple"),
        # The user explicitly chose a VLM for BOXES — honour the request for
        # any vision model; the orphan-rejection guard is the safety net, not
        # a provider allow-list (2026-08-23, "some of these documents are
        # hard hard to read").
        return_boxes=use_vlm,
        force_return_boxes=use_vlm,
        language=inputs.get("language", "en"),
        max_image_dimension=inputs.get("max_image_dimension", 2048),
        force_ocr=True,
        temperature=None,
        max_tokens=None,
        output_format="text",
        output_options={},
        reference_values=None,
        match_mode="prefer",
        context=None,
        input_metadata=inputs.get("metadata"),
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=False,
    )

    # Fix A: when this run substituted the configured Vision default (no model
    # was picked for the run or the step) and that default could not serve any
    # file, fail LOUD and NAMED. process_vision swallows a provider/runtime
    # error into per-file result["error"], which otherwise surfaces only as the
    # builder's opaque "All parallel branches failed ... not installed" — with
    # no hint that the model was the CONFIGURED DEFAULT, not the user's pick.
    if configured_default is not None:
        branch_errors = [
            r.get("error")
            for r in result.get("results", [])
            if isinstance(r, dict) and r.get("error")
        ]
        produced = any(
            isinstance(r, dict) and not r.get("error")
            for r in result.get("results", [])
        )
        if branch_errors and not produced:
            raise ValueError(
                f"Detect Regions (VLM) used the configured Vision default "
                f"'{configured_default.provider}/{configured_default.model}' "
                f"because no model was selected for this run, but it could not "
                f"serve the request: {branch_errors[0]}. Select a vision-capable "
                f"model in the Run Workflow menu, pin one on this step, or make "
                f"the configured Vision default available (for a local MLX model, "
                f"enable it and download it in Settings)."
            )

    # Pass the inputs through untouched so a transcriber chains directly
    # after this node: detect_regions annotates, it does not transform.
    result["files"] = files
    result["documents"] = documents
    return result
