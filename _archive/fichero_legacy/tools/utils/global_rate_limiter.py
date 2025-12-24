"""
Global API Rate Limiter

Provides a singleton rate limiter that is shared across all folders and tools
to prevent exceeding API rate limits when processing multiple folders in parallel.

Usage:
    from fichero.tools.utils.global_rate_limiter import get_rate_limiter

    limiter = get_rate_limiter('dashscope')
    async with limiter.acquire():
        result = await api_call()
"""

import asyncio
import threading
import time
import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for a rate limiter"""
    max_concurrent: int = 30
    retry_on_429: bool = True
    max_retries: int = 5
    base_retry_delay: float = 1.0


@dataclass
class RateLimiterStats:
    """Statistics for monitoring rate limiter usage"""
    total_requests: int = 0
    active_requests: int = 0
    waiting_requests: int = 0
    rate_limit_hits: int = 0
    successful_retries: int = 0
    failed_retries: int = 0


class GlobalRateLimiter:
    """
    Thread-safe global rate limiter using asyncio.Semaphore.

    This limiter is shared across all folders and tools to ensure
    we don't exceed API rate limits when processing in parallel.

    Key features:
    - Global semaphore shared across all event loops (via thread-local storage)
    - Configurable per-provider limits
    - 429 error detection with exponential backoff
    - Statistics tracking for monitoring
    """

    _instance: Optional['GlobalRateLimiter'] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._configs: Dict[str, RateLimitConfig] = {}
        self._stats: Dict[str, RateLimiterStats] = {}
        self._semaphores: Dict[str, Dict[int, asyncio.Semaphore]] = {}  # provider -> {loop_id -> semaphore}
        self._semaphore_locks: Dict[str, threading.Lock] = {}
        self._global_counter = threading.Lock()
        self._active_counts: Dict[str, int] = {}  # Global active count per provider

        # Load default configs
        self._load_default_configs()

        logger.info("GlobalRateLimiter initialized")

    def _load_default_configs(self):
        """Load default configurations"""
        # Defaults - will be overridden by settings if available
        self._configs['dashscope'] = RateLimitConfig(
            max_concurrent=30,
            retry_on_429=True,
            max_retries=5,
            base_retry_delay=1.0
        )
        self._configs['openai'] = RateLimitConfig(
            max_concurrent=20,
            retry_on_429=True,
            max_retries=5,
            base_retry_delay=1.0
        )
        self._configs['default'] = RateLimitConfig(
            max_concurrent=30,
            retry_on_429=True,
            max_retries=5,
            base_retry_delay=1.0
        )

        # Initialize stats
        for provider in self._configs:
            self._stats[provider] = RateLimiterStats()
            self._semaphores[provider] = {}
            self._semaphore_locks[provider] = threading.Lock()
            self._active_counts[provider] = 0

    def configure(self, settings: Dict[str, Any]):
        """
        Configure rate limits from application settings.

        Args:
            settings: Settings dict with 'api_rate_limits' section
        """
        rate_limits = settings.get('api_rate_limits', {})

        # Global default
        global_max = rate_limits.get('global_max_concurrent', 30)
        self._configs['default'].max_concurrent = global_max

        # Per-provider configs
        for provider in ['dashscope', 'openai']:
            if provider in rate_limits:
                provider_config = rate_limits[provider]
                if provider not in self._configs:
                    self._configs[provider] = RateLimitConfig()
                    self._stats[provider] = RateLimiterStats()
                    self._semaphores[provider] = {}
                    self._semaphore_locks[provider] = threading.Lock()
                    self._active_counts[provider] = 0

                self._configs[provider].max_concurrent = provider_config.get('max_concurrent', global_max)
                self._configs[provider].retry_on_429 = provider_config.get('retry_on_429', True)
                self._configs[provider].max_retries = provider_config.get('max_retries', 5)
                self._configs[provider].base_retry_delay = provider_config.get('base_retry_delay', 1.0)

        logger.info(f"Rate limiter configured: {self._configs}")

    def _get_semaphore(self, provider: str) -> asyncio.Semaphore:
        """
        Get or create a semaphore for the current event loop.

        Semaphores are per-event-loop because asyncio.Semaphore is not thread-safe.
        We use a global counter to track total active requests across all loops.
        """
        if provider not in self._configs:
            provider = 'default'

        try:
            loop = asyncio.get_running_loop()
            loop_id = id(loop)
        except RuntimeError:
            # No running loop - create a new one will happen in the caller
            loop_id = 0

        with self._semaphore_locks.get(provider, threading.Lock()):
            if provider not in self._semaphores:
                self._semaphores[provider] = {}

            if loop_id not in self._semaphores[provider]:
                max_concurrent = self._configs[provider].max_concurrent
                self._semaphores[provider][loop_id] = asyncio.Semaphore(max_concurrent)
                logger.debug(f"Created semaphore for {provider} in loop {loop_id} with limit {max_concurrent}")

            return self._semaphores[provider][loop_id]

    def get_config(self, provider: str) -> RateLimitConfig:
        """Get configuration for a provider"""
        return self._configs.get(provider, self._configs['default'])

    def get_stats(self, provider: str) -> RateLimiterStats:
        """Get statistics for a provider"""
        return self._stats.get(provider, RateLimiterStats())

    def get_available_slots(self, provider: str) -> int:
        """Get number of available slots for a provider"""
        config = self.get_config(provider)
        with self._global_counter:
            active = self._active_counts.get(provider, 0)
        return max(0, config.max_concurrent - active)

    @asynccontextmanager
    async def acquire(self, provider: str = 'default'):
        """
        Acquire a rate limit slot.

        Usage:
            async with limiter.acquire('dashscope'):
                result = await api_call()
        """
        if provider not in self._configs:
            provider = 'default'

        semaphore = self._get_semaphore(provider)
        stats = self._stats[provider]

        # Track waiting
        with self._global_counter:
            stats.waiting_requests += 1

        try:
            await semaphore.acquire()

            with self._global_counter:
                stats.waiting_requests -= 1
                stats.active_requests += 1
                stats.total_requests += 1
                self._active_counts[provider] = self._active_counts.get(provider, 0) + 1

            yield

        finally:
            semaphore.release()
            with self._global_counter:
                stats.active_requests -= 1
                self._active_counts[provider] = max(0, self._active_counts.get(provider, 1) - 1)

    async def execute_with_retry(
        self,
        provider: str,
        async_fn,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute an async function with rate limiting and 429 retry handling.

        Args:
            provider: API provider name ('dashscope', 'openai', etc.)
            async_fn: Async function to execute
            *args, **kwargs: Arguments to pass to the function

        Returns:
            Result from async_fn

        Raises:
            Exception: If all retries fail
        """
        config = self.get_config(provider)
        stats = self._stats.get(provider, RateLimiterStats())

        last_error = None
        retry_delay = config.base_retry_delay

        for attempt in range(config.max_retries + 1):
            try:
                async with self.acquire(provider):
                    result = await async_fn(*args, **kwargs)

                    if attempt > 0:
                        stats.successful_retries += 1
                        logger.info(f"Request succeeded after {attempt} retries")

                    return result

            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Check for rate limit error (429)
                is_rate_limit = any(x in error_str for x in ['429', 'rate limit', 'too many requests', 'throttl'])

                if is_rate_limit:
                    stats.rate_limit_hits += 1

                    if config.retry_on_429 and attempt < config.max_retries:
                        logger.warning(
                            f"Rate limit hit for {provider} (attempt {attempt + 1}/{config.max_retries + 1}). "
                            f"Retrying in {retry_delay:.1f}s..."
                        )
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                    else:
                        logger.error(f"Rate limit exceeded for {provider} after {attempt + 1} attempts")
                        stats.failed_retries += 1
                        raise
                else:
                    # Non-rate-limit error - don't retry
                    raise

        # Should not reach here, but just in case
        if last_error:
            raise last_error

    def log_stats(self, provider: str = None):
        """Log current statistics"""
        providers = [provider] if provider else list(self._stats.keys())

        for p in providers:
            if p in self._stats:
                stats = self._stats[p]
                config = self._configs.get(p, self._configs['default'])
                logger.info(
                    f"Rate limiter stats [{p}]: "
                    f"active={stats.active_requests}/{config.max_concurrent}, "
                    f"waiting={stats.waiting_requests}, "
                    f"total={stats.total_requests}, "
                    f"429_hits={stats.rate_limit_hits}, "
                    f"retries_ok={stats.successful_retries}, "
                    f"retries_fail={stats.failed_retries}"
                )

    def reset_stats(self, provider: str = None):
        """Reset statistics"""
        providers = [provider] if provider else list(self._stats.keys())
        for p in providers:
            if p in self._stats:
                self._stats[p] = RateLimiterStats()


# Singleton accessor
_rate_limiter: Optional[GlobalRateLimiter] = None


def get_rate_limiter() -> GlobalRateLimiter:
    """Get the global rate limiter singleton"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = GlobalRateLimiter()
    return _rate_limiter


def configure_rate_limiter(settings: Dict[str, Any]):
    """Configure the global rate limiter from settings"""
    limiter = get_rate_limiter()
    limiter.configure(settings)


# Convenience function for simple usage
async def rate_limited_call(provider: str, async_fn, *args, **kwargs):
    """
    Execute an async function with rate limiting.

    Usage:
        result = await rate_limited_call('dashscope', api.transcribe, image_path)
    """
    limiter = get_rate_limiter()
    return await limiter.execute_with_retry(provider, async_fn, *args, **kwargs)
