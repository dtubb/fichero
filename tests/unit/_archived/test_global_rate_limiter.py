"""
Unit tests for global rate limiter.

Tests the GlobalRateLimiter singleton used for API rate limiting
across all folders and tools.
"""

import pytest
import asyncio
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from fichero.tools.utils.global_rate_limiter import (
    GlobalRateLimiter,
    get_rate_limiter,
    configure_rate_limiter,
    rate_limited_call,
    RateLimitConfig,
)


class TestGlobalRateLimiterSingleton:
    """Test singleton pattern"""

    def test_singleton_returns_same_instance(self):
        """Test that get_rate_limiter returns the same instance"""
        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()
        assert limiter1 is limiter2

    def test_singleton_is_thread_safe(self):
        """Test that singleton is thread-safe"""
        limiters = []

        def get_limiter():
            limiters.append(get_rate_limiter())

        threads = [threading.Thread(target=get_limiter) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should be the same instance
        assert len(set(id(l) for l in limiters)) == 1


class TestRateLimiterConfiguration:
    """Test configuration"""

    def test_default_configs(self):
        """Test default configurations are loaded"""
        limiter = get_rate_limiter()

        dashscope_config = limiter.get_config('dashscope')
        assert dashscope_config.max_concurrent == 30
        assert dashscope_config.retry_on_429 is True

        openai_config = limiter.get_config('openai')
        assert openai_config.max_concurrent == 20

    def test_configure_from_settings(self):
        """Test configuration from settings dict"""
        limiter = get_rate_limiter()

        settings = {
            'api_rate_limits': {
                'global_max_concurrent': 50,
                'dashscope': {
                    'max_concurrent': 40,
                    'retry_on_429': True,
                    'max_retries': 3,
                    'base_retry_delay': 2.0
                }
            }
        }

        configure_rate_limiter(settings)

        config = limiter.get_config('dashscope')
        assert config.max_concurrent == 40
        assert config.max_retries == 3
        assert config.base_retry_delay == 2.0

    def test_unknown_provider_uses_default(self):
        """Test unknown provider falls back to default config"""
        limiter = get_rate_limiter()
        config = limiter.get_config('unknown_provider')
        default_config = limiter.get_config('default')
        assert config.max_concurrent == default_config.max_concurrent


class TestRateLimiterAcquire:
    """Test acquire context manager"""

    @pytest.mark.asyncio
    async def test_acquire_releases_slot(self):
        """Test that acquire properly acquires and releases slots"""
        limiter = get_rate_limiter()
        provider = 'dashscope'

        initial_available = limiter.get_available_slots(provider)

        async with limiter.acquire(provider):
            during_available = limiter.get_available_slots(provider)
            assert during_available == initial_available - 1

        after_available = limiter.get_available_slots(provider)
        assert after_available == initial_available

    @pytest.mark.asyncio
    async def test_concurrent_acquire_respects_limit(self):
        """Test that concurrent acquires respect the max limit"""
        limiter = get_rate_limiter()

        # Use a small limit for testing
        limiter._configs['test_provider'] = RateLimitConfig(max_concurrent=3)
        limiter._stats['test_provider'] = limiter._stats.get('dashscope').__class__()
        limiter._semaphores['test_provider'] = {}
        limiter._semaphore_locks['test_provider'] = threading.Lock()
        limiter._active_counts['test_provider'] = 0

        max_concurrent_seen = 0
        concurrent_count = 0
        lock = asyncio.Lock()

        async def acquire_and_work():
            nonlocal max_concurrent_seen, concurrent_count
            async with limiter.acquire('test_provider'):
                async with lock:
                    concurrent_count += 1
                    max_concurrent_seen = max(max_concurrent_seen, concurrent_count)
                await asyncio.sleep(0.05)
                async with lock:
                    concurrent_count -= 1

        # Start 10 concurrent tasks
        tasks = [acquire_and_work() for _ in range(10)]
        await asyncio.gather(*tasks)

        # Should never exceed 3 concurrent
        assert max_concurrent_seen <= 3


class TestRateLimiter429Handling:
    """Test 429 error handling and retry logic"""

    @pytest.mark.asyncio
    async def test_execute_with_retry_success(self):
        """Test successful execution without retries"""
        limiter = get_rate_limiter()

        async def successful_fn():
            return {"success": True}

        result = await limiter.execute_with_retry('dashscope', successful_fn)
        assert result == {"success": True}

    @pytest.mark.asyncio
    async def test_execute_with_retry_on_429(self):
        """Test retry on 429 error"""
        limiter = get_rate_limiter()

        call_count = 0

        async def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("429 Too Many Requests")
            return {"success": True}

        result = await limiter.execute_with_retry('dashscope', failing_then_success)
        assert result == {"success": True}
        assert call_count == 3  # Failed twice, succeeded on third

    @pytest.mark.asyncio
    async def test_execute_with_retry_max_retries_exceeded(self):
        """Test that max retries is respected"""
        limiter = get_rate_limiter()

        # Configure low retry count
        limiter._configs['dashscope'].max_retries = 2
        limiter._configs['dashscope'].base_retry_delay = 0.01  # Fast for testing

        async def always_failing():
            raise Exception("429 Rate limit exceeded")

        with pytest.raises(Exception, match="429"):
            await limiter.execute_with_retry('dashscope', always_failing)

    @pytest.mark.asyncio
    async def test_non_429_error_not_retried(self):
        """Test that non-429 errors are not retried"""
        limiter = get_rate_limiter()

        call_count = 0

        async def non_rate_limit_error():
            nonlocal call_count
            call_count += 1
            raise Exception("Internal Server Error")

        with pytest.raises(Exception, match="Internal Server Error"):
            await limiter.execute_with_retry('dashscope', non_rate_limit_error)

        assert call_count == 1  # Only called once, no retry


class TestRateLimiterStats:
    """Test statistics tracking"""

    def test_stats_tracking(self):
        """Test that stats are properly tracked"""
        limiter = get_rate_limiter()
        limiter.reset_stats('dashscope')

        stats = limiter.get_stats('dashscope')
        assert stats.total_requests == 0
        assert stats.active_requests == 0

    @pytest.mark.asyncio
    async def test_stats_increment_on_acquire(self):
        """Test that stats are incremented during acquire"""
        limiter = get_rate_limiter()
        limiter.reset_stats('dashscope')

        async with limiter.acquire('dashscope'):
            stats = limiter.get_stats('dashscope')
            assert stats.total_requests == 1
            assert stats.active_requests == 1

        stats = limiter.get_stats('dashscope')
        assert stats.active_requests == 0


class TestRateLimitedCallConvenience:
    """Test the convenience function"""

    @pytest.mark.asyncio
    async def test_rate_limited_call(self):
        """Test rate_limited_call convenience function"""
        async def my_api_call(arg1, kwarg1=None):
            return {"arg1": arg1, "kwarg1": kwarg1}

        result = await rate_limited_call('dashscope', my_api_call, "test", kwarg1="value")
        assert result == {"arg1": "test", "kwarg1": "value"}


class TestMultipleEventLoops:
    """Test behavior with multiple event loops (multi-folder scenario)"""

    def test_rate_limiter_works_across_threads(self):
        """Test that rate limiting works when called from multiple threads"""
        limiter = get_rate_limiter()
        results = []
        errors = []

        def run_in_thread():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    async def do_work():
                        async with limiter.acquire('dashscope'):
                            await asyncio.sleep(0.01)
                            return threading.current_thread().name

                    result = loop.run_until_complete(do_work())
                    results.append(result)
                finally:
                    loop.close()
            except Exception as e:
                errors.append(str(e))

        # Start multiple threads
        threads = [threading.Thread(target=run_in_thread) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
