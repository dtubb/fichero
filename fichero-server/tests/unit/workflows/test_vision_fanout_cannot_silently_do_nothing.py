"""A vision fanout that calls nothing must FAIL, not pass quietly (#4504).

#4497 added `language=` to `vision()`. Five test doubles did not follow, so
every call raised `TypeError: unexpected keyword argument`. The fanout's broad
`except Exception` caught it, logged a warning, and returned an empty page for
each file — so the run completed, the suite's own doubles were never invoked,
and five tests failed with confusing symptoms ("expected overlap, peak
in-flight was 0", "assert ['', ''] == ['review 1', 'review 2']") that named the
consequence rather than the cause. It sat on main for hours.

Two things are pinned here, because fixing the doubles alone would leave the
mechanism that hid the breakage:

1. A malformed CALL raises. There is no fallback that makes a wrong call right,
   and degrading it to an empty page converts a caller bug into a green run
   over zero transcriptions — the "complete mechanism with nothing feeding it"
   shape this project keeps hitting (#4467, and a harness that no-opped 7 of 12
   preset nodes).
2. A PROVIDER failure still degrades gracefully. The distinction is the whole
   point; failing every file on any TypeError would trade a silent bug for a
   brittle pipeline.

Nothing here contacts a provider.
"""

from __future__ import annotations

import pytest

from fichero_server.workflows.tools.vision_base import (
    _is_call_signature_error,
    _is_non_retriable_provider_error,
)


class TestASignatureErrorIsNotAProviderFailure:
    """The predicate that decides raise-vs-degrade."""

    @pytest.mark.parametrize(
        "message",
        [
            "_vision() got an unexpected keyword argument 'language'",
            "vision() missing 1 required positional argument: 'config'",
            "vision() takes 3 positional arguments but 4 were given",
        ],
    )
    def test_a_malformed_call_is_recognised(self, message):
        assert _is_call_signature_error(message) is True, (
            f"{message!r} is a caller bug; swallowing it produces a green run "
            "over zero transcriptions"
        )

    @pytest.mark.parametrize(
        "message",
        [
            "unsupported operand type(s) for +: 'int' and 'str'",
            "'NoneType' object is not subscriptable",
            "expected str, bytes or os.PathLike object, not dict",
        ],
    )
    def test_a_data_shaped_TypeError_is_not(self, message):
        """These come from INSIDE a call and are data problems — they must
        still degrade to an empty page, as before. Failing every file on any
        TypeError would trade a silent bug for a brittle pipeline."""
        assert _is_call_signature_error(message) is False

    def test_it_does_not_collide_with_the_provider_error_predicate(self):
        """The two classifiers must not both claim the same message, or which
        branch runs would depend on ordering rather than meaning."""
        signature = "_vision() got an unexpected keyword argument 'language'"
        assert _is_call_signature_error(signature) is True
        assert _is_non_retriable_provider_error(signature) is False


class TestTheFanoutRaisesRatherThanReturningNothing:
    """The behaviour, through the real `process_vision`."""

    @pytest.mark.asyncio
    async def test_a_double_missing_the_language_kwarg_fails_loudly(
        self, tmp_path
    ):
        """Exactly the #4504 regression, reproduced through the real fanout.

        The first version of this test called `process_vision` with a kwarg it
        does not accept, so `pytest.raises(TypeError)` caught the TEST's own
        bad call and passed against BOTH the fixed and the unfixed code. It was
        the very defect it exists to catch, one level up. Hence
        `_assert_calls_the_real_signature` below: the call is checked against
        the real signature before it is made, so this can never again pass by
        raising for its own reasons.
        """
        import inspect
        from unittest.mock import patch

        from fichero_server.llm import LLMConfig
        from fichero_server.workflows.tools.vision_base import (
            VisionToolConfig,
            process_vision,
        )

        image = tmp_path / "page.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)

        kwargs = dict(
            files=[str(image)],
            documents=[],
            prompt="Transcribe this page.",
            llm_config=LLMConfig(provider="mock", model="mock"),
            library_path=str(tmp_path),
            task_id=None,
            tool_config=VisionToolConfig(artifact_type="transcription"),
        )
        # Fail here, loudly, if this call itself is malformed — rather than
        # letting the TypeError below be mistaken for the fanout's.
        inspect.signature(process_vision).bind(**kwargs)

        async def _stale_double(images, prompt, config):  # no `language` (#4497)
            return "should never be reached"

        with patch("fichero_server.llm.vision", new=_stale_double):
            with pytest.raises(TypeError) as caught:
                await process_vision(**kwargs)

        message = str(caught.value)
        assert "language" in message, (
            f"raised, but not for the missing `language` kwarg: {message}"
        )
        assert _is_call_signature_error(message)
