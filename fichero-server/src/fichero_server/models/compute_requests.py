"""Request models of the compute routes (#5398, #4642): training, a palaeographer's reasons, the reasons A/B,
reading at scale. Here, importing only pydantic, so a route module builds its OpenAPI schema without importing
the subsystem that does the work (#3950, `test_lazy_engine_imports`); the subsystems import them from here.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class _TrainRequest(BaseModel):
    """What every training card asks: which pages teach, which teacher, which test."""

    scope_ids: list[str] = Field(description="Folders or pages whose teacher-read lines are the lessons.")
    teacher: str = Field(description="The model whose line readings are the lessons, e.g. google/gemini-3-flash-preview.")
    held_out_ids: list[str] = Field(default_factory=list, description="Pages kept home as the test; never sent.")
    display_name: str | None = None
    pages_may_leave: bool = Field(False, description="The person's yes for these pages to go to Hugging Face.")
    not_for_release: bool = Field(True, description="The trained model may not be released.")
    release_note: str | None = None


class TrainKrakenRequest(_TrainRequest):
    """The Kraken card: a recognition model fine-tuned with `ketos train`."""

    base: str | None = Field(None, description="The Kraken reader to start from (a model id); none trains from nothing.")
    name: str = Field("reader", description="A short name for the trained reader's file.")
    flavor: str = Field("t4-small", description="Hugging Face hardware.")
    timeout: str = Field("4h", description="The Job's time limit; always sent (the service's default is 30 minutes).")


class TrainVisionLoraRequest(_TrainRequest):
    """The vision-model card: a LoRA on a vision-language model, landed on this Mac as MLX 4-bit."""

    base_repo: str = Field("Qwen/Qwen3-VL-8B-Instruct", description="The bf16 base on the Hub: any image-text-to-text "
                           "model (Qwen3-VL 8B by default; Qwen2.5-VL 7B, chandra and others are valid).")
    base_licence: str | None = Field(None, description="The base's licence, carried on the card; none: from Fichero's "
                                     "list of vision bases, or 'not checked'.")
    keep_merged_here: bool = Field(False, description="Also keep the merged Hugging Face weights on this Mac "
                                   "(~17 GB for 8B); they are always kept in the job's bucket.")
    language: str | None = Field(None, description="The pages' language, given to the student as the line reader gives it.")
    name: str = Field("student", description="A short name: the model lands as fichero-trained/<name>.")
    flavor: str | None = Field(None, description="Hugging Face hardware; none chooses the cheapest that fits a 7B LoRA.")
    timeout: str = Field("8h", description="The Job's time limit; always sent.")
    epochs: int = Field(2, ge=1, le=20)
    rank: int = Field(16, ge=2, le=256)
    arm: Literal["answer", "why", "thinking", "review"] = Field(
        "answer", description="What the student learns to write (#4642): the checked transcription alone, with "
        "a palaeographer's reasons, with its thinking, or a review of a draft. Reasons come from the episode "
        "ledger (training.reasons); the answer is always the checked text.")
    max_trace_cer: float = Field(0.10, ge=0.0, le=1.0, description="A palaeographer's reasons are kept only where "
                                 "its own reading of the line is within this CER of the checked one.")
    all_lines: bool = Field(False, description="Train an A/B arm on every line it has, not only the lines every "
                            "reasoning arm covers.")


class TrainKrakenHereRequest(_TrainRequest):
    """The Kraken card, trained on this Mac. Nothing leaves it."""

    base: str | None = Field(None, description="The Kraken reader to start from (a model id); none trains from nothing.")
    name: str = Field("reader", description="A short name for the trained reader's file.")
    epochs: int | None = Field(None, ge=1, description="A fixed number of epochs; none stops when it stops improving.")
    batch_size: int = Field(4, ge=1, le=64, description="Lines per step; small keeps memory down on a 16 GB Mac.")


class GatherReasonsRequest(BaseModel):
    scope_ids: list[str] = Field(description="Folders or pages whose checked lines are asked about.")
    checked: str = Field(description="The model id of the CHECKED pass (its lines and their right readings).")
    provider: str = Field(description="The teacher's provider, e.g. openrouter, gemini, omlx.")
    model: str = Field(description="The teacher: a reasoning vision model, e.g. Qwen3-VL-8B-Thinking.")
    held_out_ids: list[str] = Field(default_factory=list, description="Pages kept as the test: never asked about.")
    language: str | None = None
    prompt_file: str | None = Field(None, description="The recipe's prompt file; none uses Fichero's own.")


class ContenderSpec(BaseModel):
    label: str
    provider: str
    model: str
    arm: Literal["answer", "why", "thinking"] = Field("answer", description="How it is asked: as it was trained.")
    role: Literal["student", "teacher", "baseline"] = "student"


class ReasonsABRequest(BaseModel):
    checked: str = Field(description="The model id of the CHECKED pass: the right readings.")
    held_out_ids: list[str] = Field(description="The held-out checked pages: no arm trained on them.")
    contenders: list[ContenderSpec] = Field(min_length=2, description="The answer-only student, the reasoning "
                                            "students, the teacher and a cheap baseline.")
    language: str | None = None
    noise_band: float = Field(0.005, ge=0.0, le=1.0, description="A reasoning student is adopted only if it beats "
                              "the answer-only one by more than this CER.")


class ReadAtScaleRequest(BaseModel):
    scope_ids: list[str] = Field(description="Folders or pages to read: images here, or pages imported by reference over IIIF.")
    reader: str = Field("kraken", description="`kraken` (a Kraken reader on this Mac) or `vlm` (a vision model).")
    card: str = Field(description="The reader: a Kraken reader id, a trained vision model (`fichero-trained/<name>`, "
                      "its Hugging Face build), or a Hub repo.")
    language: str | None = None
    shard_size: int = Field(50, ge=1, le=10000)
    longest: int = Field(2000, ge=256, le=10000, description="Pixels on the longer side each image is read at.")
    flavor: str = Field("t4-small", description="Hugging Face hardware for each shard.")
    timeout: str = Field("2h", description="Each shard's time limit; always sent.")
    max_in_flight: int = Field(10, ge=1, le=500, description="Shards running at once.")
    pass_name: str | None = None
    pages_may_leave: bool = Field(False, description="The person's yes for these pages (or their IIIF addresses) to go "
                                  "to Hugging Face.")
