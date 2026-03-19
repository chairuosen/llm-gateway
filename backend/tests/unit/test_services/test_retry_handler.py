"""
Retry Handler Unit Tests
"""

import pytest
import time
from unittest.mock import AsyncMock
from app.services.retry_handler import RetryHandler, CircuitBreakerRegistry, circuit_breaker
from app.services.strategy import RoundRobinStrategy, PriorityStrategy
from app.providers.base import ProviderResponse
from app.rules.models import CandidateProvider


class TestRetryHandler:
    """Retry Handler Tests"""
    
    def setup_method(self):
        """Setup before test"""
        self.strategy = RoundRobinStrategy()
        self.handler = RetryHandler(self.strategy)
        self.handler.max_retries = 3
        self.handler.retry_delay_ms = 10  # Speed up test
        
        self.candidates = [
            CandidateProvider(
                provider_id=1,
                provider_name="Provider1",
                base_url="https://api1.com",
                protocol="openai",
                api_key="key1",
                target_model="model1",
                priority=1,
            ),
            CandidateProvider(
                provider_id=2,
                provider_name="Provider2",
                base_url="https://api2.com",
                protocol="openai",
                api_key="key2",
                target_model="model2",
                priority=2,
            ),
        ]
    
    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        """Test success on first attempt"""
        self.strategy.reset()
        
        async def forward_fn(candidate):
            return ProviderResponse(status_code=200, body={"result": "ok"})
        
        result = await self.handler.execute_with_retry(
            candidates=self.candidates,
            requested_model="test",
            forward_fn=forward_fn,
        )
        
        assert result.success is True
        assert result.retry_count == 0
        assert result.response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_retry_on_500_error(self):
        """Test retry on 500 error"""
        self.strategy.reset()
        call_count = 0
        
        async def forward_fn(candidate):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return ProviderResponse(status_code=500, error="Server error")
            return ProviderResponse(status_code=200, body={"result": "ok"})
        
        result = await self.handler.execute_with_retry(
            candidates=self.candidates,
            requested_model="test",
            forward_fn=forward_fn,
        )
        
        assert result.success is True
        assert result.retry_count == 2  # Succeeded after 2 retries
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_switch_provider_on_400_error(self):
        """Test switch provider on 400 error"""
        self.strategy.reset()
        provider_calls = []
        
        async def forward_fn(candidate):
            provider_calls.append(candidate.provider_id)
            if candidate.provider_id == 1:
                return ProviderResponse(status_code=400, error="Bad request")
            return ProviderResponse(status_code=200, body={"result": "ok"})
        
        result = await self.handler.execute_with_retry(
            candidates=self.candidates,
            requested_model="test",
            forward_fn=forward_fn,
        )
        
        assert result.success is True
        assert result.final_provider.provider_id == 2
        # Switch to second provider immediately after first failure
        assert provider_calls == [1, 2]
    
    @pytest.mark.asyncio
    async def test_max_retries_then_switch(self):
        """Test switch provider after max retries"""
        self.strategy.reset()
        provider_calls = []
        
        async def forward_fn(candidate):
            provider_calls.append(candidate.provider_id)
            if candidate.provider_id == 1:
                return ProviderResponse(status_code=500, error="Server error")
            return ProviderResponse(status_code=200, body={"result": "ok"})
        
        result = await self.handler.execute_with_retry(
            candidates=self.candidates,
            requested_model="test",
            forward_fn=forward_fn,
        )
        
        assert result.success is True
        assert result.final_provider.provider_id == 2
        # Provider1 retries 3 times then switch to Provider2
        assert provider_calls == [1, 1, 1, 2]
    
    @pytest.mark.asyncio
    async def test_all_providers_fail(self):
        """Test all providers fail"""
        self.strategy.reset()
        
        async def forward_fn(candidate):
            return ProviderResponse(status_code=500, error="Server error")
        
        result = await self.handler.execute_with_retry(
            candidates=self.candidates,
            requested_model="test",
            forward_fn=forward_fn,
        )
        
        assert result.success is False
        assert result.response.status_code == 500
        # Each provider retries 3 times, total 6 times
        assert result.retry_count == 6
    
    @pytest.mark.asyncio
    async def test_empty_candidates(self):
        """Test empty candidate list"""
        result = await self.handler.execute_with_retry(
            candidates=[],
            requested_model="test",
            forward_fn=AsyncMock(),
        )
        
        assert result.success is False
        assert result.response.status_code == 503

    @pytest.mark.asyncio
    async def test_switch_between_same_provider_multiple_target_models(self):
        """Failover should work for multiple mappings under one provider."""
        self.strategy.reset()
        candidates = [
            CandidateProvider(
                provider_mapping_id=201,
                provider_id=1,
                provider_name="Provider1",
                base_url="https://api1.com",
                protocol="openai",
                api_key="key1",
                target_model="model-a",
                priority=1,
            ),
            CandidateProvider(
                provider_mapping_id=202,
                provider_id=1,
                provider_name="Provider1",
                base_url="https://api1.com",
                protocol="openai",
                api_key="key1",
                target_model="model-b",
                priority=2,
            ),
        ]
        called_models: list[str] = []

        async def forward_fn(candidate):
            called_models.append(candidate.target_model)
            if candidate.target_model == "model-a":
                return ProviderResponse(status_code=400, error="Bad request")
            return ProviderResponse(status_code=200, body={"result": "ok"})

        result = await self.handler.execute_with_retry(
            candidates=candidates,
            requested_model="test",
            forward_fn=forward_fn,
        )

        assert result.success is True
        assert result.final_provider.provider_mapping_id == 202
        assert called_models == ["model-a", "model-b"]


# ---------------------------------------------------------------------------
# Circuit Breaker Tests
# ---------------------------------------------------------------------------

def _make_candidate(provider_id: int, priority: int = 1) -> CandidateProvider:
    return CandidateProvider(
        provider_id=provider_id,
        provider_name=f"Provider{provider_id}",
        base_url=f"https://api{provider_id}.com",
        protocol="openai",
        api_key=f"key{provider_id}",
        target_model=f"model{provider_id}",
        priority=priority,
    )


class TestCircuitBreakerRegistry:
    """Unit tests for CircuitBreakerRegistry (independent of RetryHandler)."""

    def setup_method(self):
        self.cb = CircuitBreakerRegistry()
        self.p = _make_candidate(1)

    @pytest.mark.asyncio
    async def test_initially_closed(self):
        assert await self.cb.is_open(self.p) is False

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self):
        # Default threshold in registry is read from settings; force it via env / monkeypatch
        # Here we manipulate internal state directly for speed.
        from app.config import get_settings
        threshold = get_settings().CIRCUIT_BREAKER_FAILURE_THRESHOLD
        for _ in range(threshold):
            await self.cb.record_failure(self.p)
        assert await self.cb.is_open(self.p) is True

    @pytest.mark.asyncio
    async def test_success_closes_circuit(self):
        from app.config import get_settings
        threshold = get_settings().CIRCUIT_BREAKER_FAILURE_THRESHOLD
        for _ in range(threshold):
            await self.cb.record_failure(self.p)
        assert await self.cb.is_open(self.p) is True
        await self.cb.record_success(self.p)
        assert await self.cb.is_open(self.p) is False

    @pytest.mark.asyncio
    async def test_half_open_after_cooldown(self):
        """After cooldown, is_open returns False (probe allowed)."""
        cb = CircuitBreakerRegistry()
        p = _make_candidate(99)
        # Manually set opened_at to far in the past to simulate cooldown elapsed
        from app.config import get_settings
        cooldown = get_settings().CIRCUIT_BREAKER_COOLDOWN_SECONDS
        key = f"provider:99:model99"
        from app.services.retry_handler import _CircuitState
        import time
        cb._states[key] = _CircuitState(
            consecutive_failures=get_settings().CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            opened_at=time.monotonic() - cooldown - 1,  # already past cooldown
        )
        # Should be half-open → is_open returns False
        assert await cb.is_open(p) is False

    @pytest.mark.asyncio
    async def test_reset_clears_state(self):
        from app.config import get_settings
        threshold = get_settings().CIRCUIT_BREAKER_FAILURE_THRESHOLD
        for _ in range(threshold):
            await self.cb.record_failure(self.p)
        assert await self.cb.is_open(self.p) is True
        self.cb.reset(self.p)
        assert await self.cb.is_open(self.p) is False


class TestRetryHandlerCircuitBreaker:
    """Integration tests: RetryHandler skips circuit-broken providers."""

    def setup_method(self):
        self.strategy = PriorityStrategy()
        self.handler = RetryHandler(self.strategy)
        self.handler.max_retries = 2
        self.handler.retry_delay_ms = 0
        # Reset the global circuit breaker between tests
        circuit_breaker.reset()

    @pytest.mark.asyncio
    async def test_skips_open_provider_on_initial_select(self):
        """If the top-priority provider is circuit-broken, start with the next one."""
        from app.config import get_settings
        threshold = get_settings().CIRCUIT_BREAKER_FAILURE_THRESHOLD

        p1 = _make_candidate(1, priority=1)
        p2 = _make_candidate(2, priority=2)
        candidates = [p1, p2]

        # Trip p1's circuit in the global registry
        for _ in range(threshold):
            await circuit_breaker.record_failure(p1)
        assert await circuit_breaker.is_open(p1) is True

        called: list[int] = []

        async def forward_fn(candidate):
            called.append(candidate.provider_id)
            return ProviderResponse(status_code=200, body={"ok": True})

        result = await self.handler.execute_with_retry(
            candidates=candidates,
            requested_model="test",
            forward_fn=forward_fn,
        )

        assert result.success is True
        # p1 should have been skipped; only p2 called
        assert called == [2], f"Expected [2], got {called}"

    @pytest.mark.asyncio
    async def test_circuit_opens_after_consecutive_failures_and_skipped_next_request(self, monkeypatch):
        """After threshold failures, the provider is skipped on subsequent requests."""
        import app.config as cfg_module

        class FakeSettings:
            CIRCUIT_BREAKER_ENABLED = True
            CIRCUIT_BREAKER_FAILURE_THRESHOLD = 2
            CIRCUIT_BREAKER_COOLDOWN_SECONDS = 300
            RETRY_MAX_ATTEMPTS = 2
            RETRY_DELAY_MS = 0

        monkeypatch.setattr(cfg_module, "get_settings", lambda: FakeSettings())

        p1 = _make_candidate(1, priority=1)
        p2 = _make_candidate(2, priority=2)
        candidates = [p1, p2]
        call_log: list[int] = []

        # First request: p1 fails twice → circuit opens; p2 succeeds
        async def first_forward(candidate):
            call_log.append(candidate.provider_id)
            if candidate.provider_id == 1:
                return ProviderResponse(status_code=500, error="server error")
            return ProviderResponse(status_code=200, body={"ok": True})

        result1 = await self.handler.execute_with_retry(
            candidates=candidates, requested_model="test", forward_fn=first_forward
        )
        assert result1.success is True
        assert result1.final_provider.provider_id == 2
        assert await circuit_breaker.is_open(p1) is True

        # Second request: p1 should be skipped immediately
        call_log.clear()
        async def second_forward(candidate):
            call_log.append(candidate.provider_id)
            return ProviderResponse(status_code=200, body={"ok": True})

        result2 = await self.handler.execute_with_retry(
            candidates=candidates, requested_model="test", forward_fn=second_forward
        )
        assert result2.success is True
        assert 1 not in call_log, f"p1 should have been skipped, but was called: {call_log}"
        assert call_log == [2]

    @pytest.mark.asyncio
    async def test_fallback_when_all_open(self):
        """When all providers are circuit-broken, still attempt rather than 503."""
        from app.config import get_settings
        threshold = get_settings().CIRCUIT_BREAKER_FAILURE_THRESHOLD

        p1 = _make_candidate(1, priority=1)
        p2 = _make_candidate(2, priority=2)

        for _ in range(threshold):
            await circuit_breaker.record_failure(p1)
            await circuit_breaker.record_failure(p2)
        assert await circuit_breaker.is_open(p1) is True
        assert await circuit_breaker.is_open(p2) is True

        called: list[int] = []

        async def forward_fn(candidate):
            called.append(candidate.provider_id)
            return ProviderResponse(status_code=200, body={"ok": True})

        result = await self.handler.execute_with_retry(
            candidates=[p1, p2], requested_model="test", forward_fn=forward_fn
        )
        # Should have attempted at least one provider (fallback mode)
        assert len(called) >= 1
        assert result.success is True
