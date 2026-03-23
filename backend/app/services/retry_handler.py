"""
Retry and Failover Handler Module

Implements logic for request retry and provider failover.
"""

import asyncio
import logging
import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Awaitable

from app.config import get_settings
from app.common.time import utc_now
from app.providers.base import ProviderResponse
from app.rules.models import CandidateProvider
from app.services.strategy import SelectionStrategy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

@dataclass
class _CircuitState:
    """Per-provider circuit state."""
    consecutive_failures: int = 0
    # Monotonic timestamp (seconds) when the circuit opened; None = closed
    opened_at: Optional[float] = None


class CircuitBreakerRegistry:
    """
    In-process circuit breaker registry (singleton).

    State machine per provider key:
      CLOSED  → normal operation
      OPEN    → provider is skipped; triggered after N consecutive failures
      HALF-OPEN → cooldown elapsed; one probe request is allowed through;
                  success → CLOSED, failure → OPEN again

    Thread/coroutine safety: protected by a single asyncio.Lock.
    """

    def __init__(self) -> None:
        self._states: dict[str, _CircuitState] = {}
        self._lock: Optional[asyncio.Lock] = None

    @property
    def _alock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _key(self, candidate: CandidateProvider) -> str:
        if candidate.provider_mapping_id is not None:
            return f"mapping:{candidate.provider_mapping_id}"
        return f"provider:{candidate.provider_id}:{candidate.target_model}"

    def _state(self, key: str) -> _CircuitState:
        if key not in self._states:
            self._states[key] = _CircuitState()
        return self._states[key]

    async def is_open(self, candidate: CandidateProvider) -> bool:
        """
        Return True if the provider should be skipped (circuit is OPEN and still
        within the cooldown window).  HALF-OPEN (cooldown elapsed) returns False so
        a probe request is allowed.
        """
        settings = get_settings()
        if not settings.CIRCUIT_BREAKER_ENABLED:
            return False
        key = self._key(candidate)
        async with self._alock:
            state = self._state(key)
            if state.opened_at is None:
                return False
            elapsed = time.monotonic() - state.opened_at
            if elapsed >= settings.CIRCUIT_BREAKER_COOLDOWN_SECONDS:
                # Transition to HALF-OPEN: reset failure count so a single success
                # will close the circuit, but leave opened_at so we can detect the
                # probe outcome in record_failure / record_success.
                state.consecutive_failures = 0
                return False  # allow the probe through
            return True

    async def record_failure(self, candidate: CandidateProvider) -> None:
        """Record a failure for a provider; may open the circuit."""
        settings = get_settings()
        if not settings.CIRCUIT_BREAKER_ENABLED:
            return
        key = self._key(candidate)
        async with self._alock:
            state = self._state(key)
            state.consecutive_failures += 1
            if state.consecutive_failures >= settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD:
                if state.opened_at is None:
                    # Newly opened
                    state.opened_at = time.monotonic()
                    logger.warning(
                        "Circuit OPENED for provider key=%s after %d consecutive failures; "
                        "cooldown=%ds",
                        key,
                        state.consecutive_failures,
                        settings.CIRCUIT_BREAKER_COOLDOWN_SECONDS,
                    )
                else:
                    # Probe in HALF-OPEN failed → reset cooldown timer
                    state.opened_at = time.monotonic()
                    logger.warning(
                        "Circuit re-OPENED (probe failed) for provider key=%s; "
                        "cooldown=%ds",
                        key,
                        settings.CIRCUIT_BREAKER_COOLDOWN_SECONDS,
                    )

    async def record_success(self, candidate: CandidateProvider) -> None:
        """Record a success; closes the circuit."""
        settings = get_settings()
        if not settings.CIRCUIT_BREAKER_ENABLED:
            return
        key = self._key(candidate)
        async with self._alock:
            state = self._state(key)
            if state.opened_at is not None:
                logger.info(
                    "Circuit CLOSED for provider key=%s after successful probe", key
                )
            state.consecutive_failures = 0
            state.opened_at = None

    def reset(self, candidate: Optional[CandidateProvider] = None) -> None:
        """Reset circuit state (mainly for testing)."""
        if candidate is not None:
            self._states.pop(self._key(candidate), None)
        else:
            self._states.clear()


# Global singleton shared across all RetryHandler instances in this process.
circuit_breaker = CircuitBreakerRegistry()


@dataclass
class AttemptRecord:
    """
    Attempt Record

    Stores per-attempt information so callers can persist logs for failures/retries.
    """

    provider: CandidateProvider
    response: ProviderResponse
    request_time: datetime
    attempt_index: int


@dataclass
class RetryResult:
    """
    Retry Result Data Class
    
    Encapsulates result information after retry execution.
    """
    
    # Final Response
    response: ProviderResponse
    # Total Retry Count
    retry_count: int
    # Final Provider Used
    final_provider: CandidateProvider
    # Success Status
    success: bool
    # All attempts in order (including final)
    attempts: list[AttemptRecord]


class RetryHandler:
    """
    Retry and Failover Handler

    Implements the following retry logic:
    - Status code >= 500: Retry on the same provider, max N times, with delay
    - Status code < 500: Switch directly to the next provider
    - All providers failed: Return the last failed response

    Circuit breaker: providers that fail consecutively are temporarily skipped
    (OPEN state) for a configurable cooldown period, enabling fast failover
    to healthy providers without burning time on repeated retries.
    """

    def __init__(self, strategy: SelectionStrategy):
        """
        Initialize Handler

        Args:
            strategy: Provider Selection Strategy
        """
        settings = get_settings()
        self.strategy = strategy
        # Max retries on same provider
        self.max_retries = settings.RETRY_MAX_ATTEMPTS
        # Retry interval (ms)
        self.retry_delay_ms = settings.RETRY_DELAY_MS

    @staticmethod
    def _candidate_key(
        candidate: CandidateProvider,
    ) -> tuple[str, int] | tuple[str, int, str]:
        if candidate.provider_mapping_id is not None:
            return ("mapping", candidate.provider_mapping_id)
        return ("provider_target", candidate.provider_id, candidate.target_model)

    async def get_ordered_candidates(
        self,
        candidates: list[CandidateProvider],
        requested_model: str,
        *,
        input_tokens: Optional[int] = None,
        image_count: Optional[int] = None,
    ) -> list[CandidateProvider]:
        """
        Get candidate order based on the selection strategy.

        This mirrors provider selection + failover ordering without making requests.
        """
        if not candidates:
            return []

        ordered: list[CandidateProvider] = []
        tried_candidates: set[tuple[str, int] | tuple[str, int, str]] = set()
        current_provider = await self.strategy.select(candidates, requested_model, input_tokens, image_count)
        while current_provider is not None:
            current_key = self._candidate_key(current_provider)
            if current_key in tried_candidates:
                break
            ordered.append(current_provider)
            tried_candidates.add(current_key)
            if len(tried_candidates) >= len(candidates):
                break
            current_provider = await self._get_next_untried_provider(
                candidates, tried_candidates, requested_model, current_provider, input_tokens, image_count
            )

        if len(ordered) == len(candidates):
            return ordered

        for candidate in candidates:
            if self._candidate_key(candidate) not in tried_candidates:
                ordered.append(candidate)

        return ordered
    
    async def execute_with_retry(
        self,
        candidates: list[CandidateProvider],
        requested_model: str,
        forward_fn: Callable[[CandidateProvider], Any],
        *,
        input_tokens: Optional[int] = None,
        image_count: Optional[int] = None,
        on_failure_attempt: Callable[[AttemptRecord], Awaitable[None]] | None = None,
    ) -> RetryResult:
        """
        Execute Request with Retry

        Args:
            candidates: List of candidate providers
            requested_model: Requested model name
            forward_fn: Forwarding function, accepts CandidateProvider and returns ProviderResponse
            input_tokens: Number of input tokens (for cost-based selection)

        Returns:
            RetryResult: Retry result
        """
        if not candidates:
            return RetryResult(
                response=ProviderResponse(
                    status_code=503,
                    error="No available providers",
                ),
                retry_count=0,
                final_provider=None,  # type: ignore
                success=False,
                attempts=[],
            )

        # Track tried candidates
        tried_candidates: set[tuple[str, int] | tuple[str, int, str]] = set()
        total_retry_count = 0
        last_response: Optional[ProviderResponse] = None
        last_provider: Optional[CandidateProvider] = None
        attempts: list[AttemptRecord] = []
        attempt_index = 0

        # Select the first provider, skipping circuit-broken ones
        current_provider = await self._select_first_available(
            candidates, requested_model, input_tokens, image_count
        )

        while current_provider is not None:
            # Record current provider as tried
            tried_candidates.add(self._candidate_key(current_provider))
            last_provider = current_provider

            # Same provider retry count
            same_provider_retries = 0

            while same_provider_retries < self.max_retries:
                # Execute request
                attempt_time = utc_now()
                response = await forward_fn(current_provider)
                last_response = response
                attempt_record = AttemptRecord(
                    provider=current_provider,
                    response=response,
                    request_time=attempt_time,
                    attempt_index=attempt_index,
                )
                attempts.append(attempt_record)
                attempt_index += 1

                # Success response
                if response.is_success:
                    await circuit_breaker.record_success(current_provider)
                    return RetryResult(
                        response=response,
                        retry_count=total_retry_count,
                        final_provider=current_provider,
                        success=True,
                        attempts=attempts,
                    )

                if on_failure_attempt is not None:
                    try:
                        await on_failure_attempt(attempt_record)
                    except Exception:
                        logger.exception(
                            "on_failure_attempt callback failed: provider_id=%s attempt_index=%s",
                            current_provider.provider_id,
                            attempt_record.attempt_index,
                        )

                # Log failure
                logger.warning(
                    "Provider request failed: provider_id=%s, provider_name=%s, protocol=%s, "
                    "status_code=%s, error=%s, retry_attempt=%s/%s",
                    current_provider.provider_id,
                    current_provider.provider_name,
                    current_provider.protocol,
                    response.status_code,
                    response.error,
                    same_provider_retries + 1,
                    self.max_retries,
                )

                # Status code >= 500: Retry on same provider
                if response.is_server_error:
                    await circuit_breaker.record_failure(current_provider)
                    same_provider_retries += 1
                    total_retry_count += 1

                    if same_provider_retries < self.max_retries and not await circuit_breaker.is_open(current_provider):
                        # Wait before retry
                        await asyncio.sleep(self.retry_delay_ms / 1000)
                        continue
                    else:
                        # Max retries reached or circuit opened, switch provider
                        logger.warning(
                            "Max retries reached for provider: provider_id=%s, provider_name=%s, switching to next provider",
                            current_provider.provider_id,
                            current_provider.provider_name,
                        )
                        break
                else:
                    # Status code < 500: Switch provider immediately
                    await circuit_breaker.record_failure(current_provider)
                    logger.warning(
                        "Client error from provider, switching: provider_id=%s, provider_name=%s, status_code=%s",
                        current_provider.provider_id,
                        current_provider.provider_name,
                        response.status_code,
                    )
                    total_retry_count += 1
                    break

            # Try to switch to the next provider
            next_provider = await self._get_next_untried_provider(
                candidates, tried_candidates, requested_model, current_provider, input_tokens, image_count
            )

            if next_provider is None:
                # All providers tried
                break

            current_provider = next_provider

        # All providers failed
        return RetryResult(
            response=last_response or ProviderResponse(
                status_code=503,
                error="All providers failed",
            ),
            retry_count=total_retry_count,
            final_provider=last_provider,  # type: ignore
            success=False,
            attempts=attempts,
        )

    async def execute_with_retry_stream(
        self,
        candidates: list[CandidateProvider],
        requested_model: str,
        forward_stream_fn: Callable[[CandidateProvider], Any],
        *,
        input_tokens: Optional[int] = None,
        image_count: Optional[int] = None,
        on_failure_attempt: Callable[[AttemptRecord], Awaitable[None]] | None = None,
    ) -> Any:
        """
        Execute Streaming Request with Retry

        Args:
            candidates: List of candidate providers
            requested_model: Requested model name
            forward_stream_fn: Streaming forwarding function
            input_tokens: Number of input tokens (for cost-based selection)

        Yields:
            tuple[bytes, ProviderResponse, CandidateProvider, int]: (Data chunk, Response info, Final Provider, Retry Count)
        """
        if not candidates:
            yield b"", ProviderResponse(
                status_code=503,
                error="No available providers",
            ), None, 0
            return

        tried_candidates: set[tuple[str, int] | tuple[str, int, str]] = set()
        total_retry_count = 0
        last_chunk: bytes = b""
        last_response: Optional[ProviderResponse] = None
        last_provider: Optional[CandidateProvider] = None
        attempt_index = 0

        current_provider = await self._select_first_available(
            candidates, requested_model, input_tokens, image_count
        )

        while current_provider is not None:
            tried_candidates.add(self._candidate_key(current_provider))
            last_provider = current_provider
            same_provider_retries = 0
            pending_attempt_record: Optional[AttemptRecord] = None

            while same_provider_retries < self.max_retries:
                try:
                    # Get generator
                    attempt_time = utc_now()
                    result = forward_stream_fn(current_provider)
                    # Handle both sync and async forward_stream_fn
                    if asyncio.iscoroutine(result):
                        generator = await result
                    else:
                        generator = result
                    # Get first chunk
                    chunk, response = await anext(generator)
                    last_response = response
                    last_chunk = chunk
                    attempt_record = AttemptRecord(
                        provider=current_provider,
                        response=response,
                        request_time=attempt_time,
                        attempt_index=attempt_index,
                    )
                    attempt_index += 1

                    if response.is_success:
                        await circuit_breaker.record_success(current_provider)
                        # Success, yield subsequent data
                        yield chunk, response, current_provider, total_retry_count
                        async for chunk, response in generator:
                            yield chunk, response, current_provider, total_retry_count
                        return

                    if on_failure_attempt is not None:
                        try:
                            await on_failure_attempt(attempt_record)
                        except Exception:
                            logger.exception(
                                "on_failure_attempt callback failed (stream): provider_id=%s attempt_index=%s",
                                current_provider.provider_id,
                                attempt_record.attempt_index,
                            )

                    # Log failure
                    logger.warning(
                        "Provider stream request failed: provider_id=%s, provider_name=%s, protocol=%s, "
                        "status_code=%s, error=%s, retry_attempt=%s/%s",
                        current_provider.provider_id,
                        current_provider.provider_name,
                        current_provider.protocol,
                        response.status_code,
                        response.error,
                        same_provider_retries + 1,
                        self.max_retries,
                    )

                    # Failure logic
                    if response.is_server_error:
                        await circuit_breaker.record_failure(current_provider)
                        same_provider_retries += 1
                        total_retry_count += 1
                        if same_provider_retries < self.max_retries and not await circuit_breaker.is_open(current_provider):
                            await asyncio.sleep(self.retry_delay_ms / 1000)
                            continue
                        else:
                            logger.warning(
                                "Max retries reached for stream provider: provider_id=%s, provider_name=%s, switching to next provider",
                                current_provider.provider_id,
                                current_provider.provider_name,
                            )
                            pending_attempt_record = attempt_record
                            break
                    else:
                        await circuit_breaker.record_failure(current_provider)
                        logger.warning(
                            "Client error from stream provider, switching: provider_id=%s, provider_name=%s, status_code=%s",
                            current_provider.provider_id,
                            current_provider.provider_name,
                            response.status_code,
                        )
                        total_retry_count += 1
                        pending_attempt_record = attempt_record
                        break

                except Exception as e:
                    # Network or other exceptions
                    attempt_time = utc_now()
                    attempt_record = AttemptRecord(
                        provider=current_provider,
                        response=ProviderResponse(status_code=502, error=str(e)),
                        request_time=attempt_time,
                        attempt_index=attempt_index,
                    )
                    attempt_index += 1
                    await circuit_breaker.record_failure(current_provider)
                    if on_failure_attempt is not None:
                        try:
                            await on_failure_attempt(attempt_record)
                        except Exception:
                            logger.exception(
                                "on_failure_attempt callback failed (stream exception): provider_id=%s attempt_index=%s",
                                current_provider.provider_id,
                                attempt_record.attempt_index,
                            )
                    logger.warning(
                        "Exception during stream request: provider_id=%s, provider_name=%s, protocol=%s, "
                        "exception=%s, retry_attempt=%s/%s",
                        current_provider.provider_id,
                        current_provider.provider_name,
                        current_provider.protocol,
                        str(e),
                        same_provider_retries + 1,
                        self.max_retries,
                    )
                    same_provider_retries += 1
                    total_retry_count += 1
                    if same_provider_retries < self.max_retries:
                        await asyncio.sleep(self.retry_delay_ms / 1000)
                        continue
                    else:
                        logger.warning(
                            "Max exception retries reached for stream provider: provider_id=%s, provider_name=%s, switching to next provider",
                            current_provider.provider_id,
                            current_provider.provider_name,
                        )
                        pending_attempt_record = attempt_record
                        break

            next_provider = await self._get_next_untried_provider(
                candidates, tried_candidates, requested_model, current_provider, input_tokens, image_count
            )
            if next_provider is None:
                break
            current_provider = next_provider

        # All failed, return last error
        yield last_chunk, last_response or ProviderResponse(
            status_code=503,
            error="All providers failed",
        ), last_provider, total_retry_count

    async def _select_first_available(
        self,
        candidates: list[CandidateProvider],
        requested_model: str,
        input_tokens: Optional[int] = None,
        image_count: Optional[int] = None,
    ) -> Optional[CandidateProvider]:
        """
        Select the first available (non-circuit-broken) provider.

        Falls back gracefully: if ALL providers are circuit-broken, returns the
        strategy's normal choice (better to try a tripped provider than return 503
        immediately when there might be a half-open probe opportunity).
        """
        candidate_provider = await self.strategy.select(candidates, requested_model, input_tokens, image_count)
        # Fast path: circuit open, walk forward until we find an available one.
        if candidate_provider is not None and await circuit_breaker.is_open(candidate_provider):
            tried: set[tuple[str, int] | tuple[str, int, str]] = set()
            tried.add(self._candidate_key(candidate_provider))
            for _ in range(len(candidates)):
                nxt = await self.strategy.get_next(
                    candidates, requested_model, candidate_provider, input_tokens, image_count
                )
                if nxt is None:
                    break
                key = self._candidate_key(nxt)
                if key in tried:
                    break
                tried.add(key)
                if not await circuit_breaker.is_open(nxt):
                    logger.info(
                        "Circuit breaker: skipped %d provider(s), selected provider_id=%s",
                        len(tried) - 1,
                        nxt.provider_id,
                    )
                    return nxt
                candidate_provider = nxt
            # All circuit-broken: fall back to the strategy's original choice
            logger.warning(
                "Circuit breaker: all %d providers are open; falling back to strategy default",
                len(candidates),
            )
            return await self.strategy.select(candidates, requested_model, input_tokens, image_count)
        return candidate_provider

    async def _get_next_untried_provider(
        self,
        candidates: list[CandidateProvider],
        tried_candidates: set[tuple[str, int] | tuple[str, int, str]],
        requested_model: str,
        current_provider: CandidateProvider,
        input_tokens: Optional[int] = None,
        image_count: Optional[int] = None,
    ) -> Optional[CandidateProvider]:
        """
        Get next untried provider using the selection strategy.

        Skips providers whose circuit is OPEN when possible; if all remaining
        providers are circuit-broken, still returns the next untried one so the
        caller can attempt a probe rather than failing immediately.
        """
        candidate_keys = {self._candidate_key(c) for c in candidates}
        if candidate_keys and candidate_keys.issubset(tried_candidates):
            return None

        # Use the strategy to get the next provider
        next_provider = await self.strategy.get_next(
            candidates, requested_model, current_provider, input_tokens, image_count
        )

        first_untried: Optional[CandidateProvider] = None

        # Keep trying until we find an untried, non-open provider or run out of options.
        # Some strategies can cycle indefinitely; cap iterations to avoid infinite loops.
        for _ in range(max(1, len(candidate_keys))):
            if next_provider is None:
                break
            key = self._candidate_key(next_provider)
            if key not in tried_candidates:
                # Remember first untried regardless of circuit state (fallback)
                if first_untried is None:
                    first_untried = next_provider
                # Prefer one whose circuit is not open
                if not await circuit_breaker.is_open(next_provider):
                    return next_provider
            next_provider = await self.strategy.get_next(
                candidates, requested_model, next_provider, input_tokens, image_count
            )

        # All remaining are circuit-broken; still return the first untried for a probe
        return first_untried

