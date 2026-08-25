"""Explicit maintenance passes — run on request, never as import side effects.

Each pass separates a pure ``plan_*`` (read-only, reportable) from an
``apply_*`` (the writes), because these run against real archives.
"""
