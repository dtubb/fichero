"""Prompt evaluation runner — see evals/README.md (#817).

Run a tool's prompt against a set of fixed scenarios, score each output
against the rule-based checks in the matching criteria YAML, and write
a markdown report under results/.

Usage:
    PYTHONPATH=fichero-engine/src .venv/bin/python -m evals.run \\
        --tool catalogue \\
        --scenarios book_preface_tubb_2020,court_file_choco_1930_bonilla \\
        --provider openrouter --model qwen/qwen3-vl-235b-a22b-thinking

When --scenarios is omitted, runs every scenario that has a criteria
file for the named tool.

Exit code: 0 if every check passed; 1 if any failed (CI-friendly).
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent
SCENARIOS_DIR = ROOT / "scenarios"
CRITERIA_DIR = ROOT / "criteria"
RESULTS_DIR = ROOT / "results"


@dataclass
class CheckResult:
    kind: str
    passed: bool
    detail: str
    rationale: str


@dataclass
class ScenarioResult:
    tool: str
    scenario: str
    output: str
    checks: list[CheckResult]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)


# =============================================================================
# Check implementations
# =============================================================================


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text))


def _apply_check(check: dict[str, Any], output: str) -> CheckResult:
    kind = check["kind"]
    rationale = check.get("rationale", "")

    if kind == "contains":
        value = check["value"]
        ok = value in output
        return CheckResult(kind, ok, f"contains {value!r}", rationale)

    if kind == "not_contains":
        value = check["value"]
        ok = value not in output
        detail = (
            f"forbidden substring {value!r} absent" if ok
            else f"FORBIDDEN substring {value!r} found in output"
        )
        return CheckResult(kind, ok, detail, rationale)

    if kind == "regex_match":
        pattern = check["value"]
        ok = bool(re.search(pattern, output))
        return CheckResult(kind, ok, f"regex {pattern!r}", rationale)

    if kind == "regex_no_match":
        pattern = check["value"]
        ok = not bool(re.search(pattern, output))
        return CheckResult(kind, ok, f"regex {pattern!r} absent", rationale)

    if kind == "word_count_between":
        lo = int(check["min"])
        hi = int(check["max"])
        wc = _word_count(output)
        ok = lo <= wc <= hi
        return CheckResult(
            kind, ok,
            f"word count {wc} {'in' if ok else 'OUTSIDE'} [{lo}, {hi}]",
            rationale,
        )

    if kind == "starts_with":
        # Accept either a string or a list of acceptable openers.
        raw = check["value"]
        prefixes = [raw] if isinstance(raw, str) else list(raw)
        head = output.lstrip()[:200]
        matched = next((p for p in prefixes if head.startswith(p)), None)
        ok = matched is not None
        detail = (
            f"opens with {matched!r}" if ok
            else f"opens with {head[:60]!r} (none of {prefixes})"
        )
        return CheckResult(kind, ok, detail, rationale)

    if kind == "ratio_to_gold":
        gold = check["value"]
        threshold = float(check.get("min", 0.6))
        ratio = difflib.SequenceMatcher(None, gold, output).ratio()
        ok = ratio >= threshold
        return CheckResult(
            kind, ok,
            f"similarity {ratio:.2f} {'≥' if ok else '<'} {threshold}",
            rationale,
        )

    return CheckResult(
        kind, False, f"unknown check kind {kind!r}", rationale,
    )


# =============================================================================
# Tool runners
# =============================================================================


async def _run_catalogue(source: str, provider: str, model: str) -> str:
    """Invoke the catalogue narrative path with the given source text."""
    from fichero.llm import LLMConfig
    from fichero.workflows.tools.catalogue import (
        _build_prompt, _generate_resumen,
    )
    from fichero.lang_detect import resolve_output_language

    output_language = resolve_output_language(None, source, default="English")
    llm_config = LLMConfig(provider=provider, model=model)
    return await _generate_resumen(
        text=source,
        output_language=output_language,
        llm_config=llm_config,
        claim_context="",
    )


_TOOL_RUNNERS = {
    "catalogue": _run_catalogue,
}


# =============================================================================
# CLI
# =============================================================================


def _load_criteria_for(tool: str, scenarios: list[str] | None) -> list[dict]:
    """Return matching criteria dicts. When scenarios is None, every
    file `{tool}_*.yaml` in criteria/ is loaded."""
    out: list[dict] = []
    for path in sorted(CRITERIA_DIR.glob(f"{tool}_*.yaml")):
        criteria = yaml.safe_load(path.read_text())
        if scenarios and criteria.get("scenario") not in scenarios:
            continue
        out.append(criteria)
    return out


def _load_scenario(name: str) -> str:
    path = SCENARIOS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")
    return path.read_text()


async def _evaluate(
    tool: str, scenario_names: list[str] | None,
    provider: str, model: str,
) -> list[ScenarioResult]:
    runner = _TOOL_RUNNERS.get(tool)
    if runner is None:
        raise ValueError(
            f"No runner for tool {tool!r}. "
            f"Add one to evals/run.py:_TOOL_RUNNERS."
        )

    criteria_list = _load_criteria_for(tool, scenario_names)
    if not criteria_list:
        raise ValueError(
            f"No criteria files matched tool={tool!r} "
            f"scenarios={scenario_names!r}"
        )

    results: list[ScenarioResult] = []
    for criteria in criteria_list:
        scenario = criteria["scenario"]
        source = _load_scenario(scenario)
        try:
            output = await runner(source, provider, model)
        except Exception as exc:
            output = f"<RUNNER ERROR: {exc}>"
        checks = [_apply_check(c, output) for c in criteria["checks"]]
        results.append(
            ScenarioResult(tool=tool, scenario=scenario,
                           output=output, checks=checks)
        )
    return results


def _render_report(
    results: list[ScenarioResult], provider: str, model: str,
) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    total_checks = sum(len(r.checks) for r in results)
    passed_checks = sum(sum(1 for c in r.checks if c.passed) for r in results)
    lines: list[str] = [
        f"# Eval report — {now}",
        "",
        f"- Provider/model: `{provider}/{model}`",
        f"- Scenarios: {len(results)}",
        f"- Checks: {passed_checks}/{total_checks} passed",
        "",
    ]
    for r in results:
        status = "✅" if r.passed else "❌"
        lines.append(f"## {status} {r.scenario}")
        lines.append("")
        for check in r.checks:
            mark = "✓" if check.passed else "✗"
            lines.append(f"- {mark} **{check.kind}** — {check.detail}")
            if not check.passed and check.rationale:
                lines.append(f"  - _why it matters:_ {check.rationale}")
        lines.append("")
        lines.append("<details><summary>Output</summary>")
        lines.append("")
        lines.append("```")
        lines.append(r.output)
        lines.append("```")
        lines.append("")
        lines.append("</details>")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evals.run", description=__doc__)
    parser.add_argument("--tool", required=True, choices=list(_TOOL_RUNNERS))
    parser.add_argument(
        "--scenarios",
        help="Comma-separated scenario names (default: all for the tool)",
    )
    parser.add_argument(
        "--provider", default="apple",
        help="LLM provider (default: apple)",
    )
    parser.add_argument(
        "--model", default="apple-intelligence",
        help="LLM model (default: apple-intelligence)",
    )
    parser.add_argument(
        "--out",
        help="Output markdown path (default: results/<timestamp>.md)",
    )
    args = parser.parse_args(argv)

    scenarios = (
        [s.strip() for s in args.scenarios.split(",") if s.strip()]
        if args.scenarios else None
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    results = asyncio.run(_evaluate(args.tool, scenarios, args.provider, args.model))
    report = _render_report(results, args.provider, args.model)

    out_path = (
        Path(args.out) if args.out else
        RESULTS_DIR / (
            f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_"
            f"{args.provider}_{args.model.replace('/', '_')}_{args.tool}.md"
        )
    )
    out_path.write_text(report)
    print(f"\nReport written to {out_path}")

    failed = [r for r in results if not r.passed]
    if failed:
        print(
            f"\n{len(failed)} scenario(s) failed:",
            *(f"  {r.scenario}" for r in failed), sep="\n",
        )
        return 1
    print("\nAll scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
