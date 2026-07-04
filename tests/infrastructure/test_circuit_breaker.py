"""
Unit tests for Circuit Breaker implementation.

Tests cover:
- State transitions (CLOSED -> OPEN -> HALF_OPEN -> CLOSED)
- Failure threshold triggering
- Success threshold for recovery
- Timeout-based recovery testing
- Metrics collection
- Registry functionality
- Decorator and context manager usage
"""
import asyncio

import pytest

from src.infrastructure.adapters.resilience import (
    CircuitBreaker,
    CircuitBreakerMetrics,
    CircuitBreakerRegistry,
    CircuitState,
)
from src.infrastructure.exceptions import CircuitBreakerOpenException


class TestCircuitBreakerMetrics:
    """Tests for CircuitBreakerMetrics dataclass."""

    def test_record_success(self):
        metrics = CircuitBreakerMetrics()
        metrics.record_success()

        assert metrics.total_requests == 1
        assert metrics.successful_requests == 1
        assert metrics.failed_requests == 0
        assert metrics.last_success_time is not None

    def test_record_failure(self):
        metrics = CircuitBreakerMetrics()
        metrics.record_failure()

        assert metrics.total_requests == 1
        assert metrics.failed_requests == 1
        assert metrics.successful_requests == 0
        assert metrics.last_failure_time is not None

    def test_record_rejection(self):
        metrics = CircuitBreakerMetrics()
        metrics.record_rejection()

        assert metrics.total_requests == 1
        assert metrics.rejected_requests == 1

    def test_to_dict(self):
        metrics = CircuitBreakerMetrics()
        metrics.record_success()
        metrics.record_failure()

        result = metrics.to_dict()

        assert result["total_requests"] == 2
        assert result["successful_requests"] == 1
        assert result["failed_requests"] == 1
        assert result["success_rate"] == 0.5

    def test_success_rate_zero_requests(self):
        metrics = CircuitBreakerMetrics()
        result = metrics.to_dict()

        assert result["success_rate"] == 0


class TestCircuitBreakerStateTransitions:
    """Tests for circuit breaker state transitions."""

    @pytest.mark.asyncio
    async def test_starts_closed(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        assert cb.is_closed
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_failure_threshold(self):
        cb = CircuitBreaker(name="test", failure_threshold=3, timeout=1.0)

        async def failing_func():
            raise Exception("Service unavailable")

        # Trigger 3 failures
        for _ in range(3):
            with pytest.raises(Exception):
                await cb.execute(failing_func)

        assert cb.is_open
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_rejects_requests_when_open(self):
        cb = CircuitBreaker(name="test", failure_threshold=2, timeout=10.0)

        async def failing_func():
            raise Exception("Fail")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                await cb.execute(failing_func)

        assert cb.is_open

        # Next call should be rejected immediately
        with pytest.raises(CircuitBreakerOpenException) as exc_info:
            await cb.execute(failing_func)

        assert exc_info.value.name == "test"
        assert exc_info.value.time_remaining > 0

    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker(name="test", failure_threshold=2, timeout=0.1)

        async def failing_func():
            raise Exception("Fail")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                await cb.execute(failing_func)

        assert cb.is_open

        # Wait for timeout
        await asyncio.sleep(0.15)

        # Next call should transition to half-open and execute
        async def success_func():
            return "success"

        result = await cb.execute(success_func)
        assert result == "success"
        # After success in half-open (but not enough), still half-open
        # Actually, with success_threshold=2, we need 2 successes

    @pytest.mark.asyncio
    async def test_closes_after_success_threshold_in_half_open(self):
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            success_threshold=2,
            timeout=0.1
        )

        async def failing_func():
            raise Exception("Fail")

        async def success_func():
            return "success"

        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                await cb.execute(failing_func)

        assert cb.is_open

        # Wait for timeout
        await asyncio.sleep(0.15)

        # Execute 2 successful calls
        await cb.execute(success_func)
        await cb.execute(success_func)

        assert cb.is_closed

    @pytest.mark.asyncio
    async def test_reopens_on_failure_in_half_open(self):
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            success_threshold=2,
            timeout=0.1
        )

        async def failing_func():
            raise Exception("Fail")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                await cb.execute(failing_func)

        assert cb.is_open

        # Wait for timeout
        await asyncio.sleep(0.15)

        # Fail in half-open state
        with pytest.raises(Exception):
            await cb.execute(failing_func)

        assert cb.is_open


class TestCircuitBreakerExecution:
    """Tests for circuit breaker execute functionality."""

    @pytest.mark.asyncio
    async def test_executes_async_function(self):
        cb = CircuitBreaker(name="test")

        async def async_func(x, y):
            return x + y

        result = await cb.execute(async_func, 1, y=2)
        assert result == 3

    @pytest.mark.asyncio
    async def test_executes_sync_function(self):
        cb = CircuitBreaker(name="test")

        def sync_func(x, y):
            return x * y

        result = await cb.execute(sync_func, 3, y=4)
        assert result == 12

    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)

        async def failing_func():
            raise Exception("Fail")

        async def success_func():
            return "ok"

        # 2 failures
        for _ in range(2):
            with pytest.raises(Exception):
                await cb.execute(failing_func)

        assert cb._failure_count == 2

        # 1 success should reset
        await cb.execute(success_func)

        assert cb._failure_count == 0
        assert cb.is_closed

    @pytest.mark.asyncio
    async def test_excluded_exceptions_dont_count(self):
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            excluded_exceptions=(ValueError,)
        )

        async def value_error_func():
            raise ValueError("Not a service failure")

        # Excluded exceptions don't count toward threshold
        for _ in range(5):
            with pytest.raises(ValueError):
                await cb.execute(value_error_func)

        assert cb.is_closed
        assert cb._failure_count == 0


class TestCircuitBreakerFallback:
    """Tests for circuit breaker fallback functionality."""

    @pytest.mark.asyncio
    async def test_calls_fallback_when_open(self):
        async def fallback(*args, **kwargs):
            return "fallback_result"

        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            timeout=10.0,
            fallback=fallback
        )

        async def failing_func():
            raise Exception("Fail")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                await cb.execute(failing_func)

        # Fallback should be called
        result = await cb.execute(failing_func)
        assert result == "fallback_result"

    @pytest.mark.asyncio
    async def test_sync_fallback(self):
        def sync_fallback(*args, **kwargs):
            return "sync_fallback"

        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            timeout=10.0,
            fallback=sync_fallback
        )

        async def failing_func():
            raise Exception("Fail")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                await cb.execute(failing_func)

        result = await cb.execute(failing_func)
        assert result == "sync_fallback"


class TestCircuitBreakerDecorator:
    """Tests for circuit breaker as decorator."""

    @pytest.mark.asyncio
    async def test_decorator_protects_function(self):
        cb = CircuitBreaker(name="test", failure_threshold=2, timeout=10.0)

        @cb
        async def protected_func():
            raise Exception("Fail")

        # Trigger failures
        for _ in range(2):
            with pytest.raises(Exception):
                await protected_func()

        # Should be open now
        with pytest.raises(CircuitBreakerOpenException):
            await protected_func()

    @pytest.mark.asyncio
    async def test_decorator_passes_arguments(self):
        cb = CircuitBreaker(name="test")

        @cb
        async def add(x, y):
            return x + y

        result = await add(5, 7)
        assert result == 12


class TestCircuitBreakerContextManager:
    """Tests for circuit breaker as async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_success(self):
        cb = CircuitBreaker(name="test")

        async with cb:
            pass  # Success

        assert cb.metrics.successful_requests == 1

    @pytest.mark.asyncio
    async def test_context_manager_failure(self):
        cb = CircuitBreaker(name="test", failure_threshold=2)

        with pytest.raises(Exception):
            async with cb:
                raise Exception("Fail")

        assert cb.metrics.failed_requests == 1

    @pytest.mark.asyncio
    async def test_context_manager_rejects_when_open(self):
        cb = CircuitBreaker(name="test", failure_threshold=2, timeout=10.0)

        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                async with cb:
                    raise Exception("Fail")

        # Should reject
        with pytest.raises(CircuitBreakerOpenException):
            async with cb:
                pass


class TestCircuitBreakerStatus:
    """Tests for circuit breaker status/monitoring."""

    @pytest.mark.asyncio
    async def test_get_status(self):
        cb = CircuitBreaker(
            name="test_service",
            failure_threshold=5,
            success_threshold=3,
            timeout=30.0
        )

        status = cb.get_status()

        assert status["name"] == "test_service"
        assert status["state"] == "closed"
        assert status["failure_threshold"] == 5
        assert status["success_threshold"] == 3
        assert status["timeout"] == 30.0
        assert "metrics" in status

    @pytest.mark.asyncio
    async def test_reset_clears_state(self):
        cb = CircuitBreaker(name="test", failure_threshold=2, timeout=10.0)

        async def failing_func():
            raise Exception("Fail")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                await cb.execute(failing_func)

        assert cb.is_open

        # Reset
        cb.reset()

        assert cb.is_closed
        assert cb._failure_count == 0
        assert cb._success_count == 0


class TestCircuitBreakerRegistry:
    """Tests for circuit breaker registry."""

    def test_register_and_get(self):
        registry = CircuitBreakerRegistry()
        cb = CircuitBreaker(name="test_cb")

        registry.register(cb)

        assert registry.get("test_cb") is cb
        assert registry.get("nonexistent") is None

    def test_get_all_status(self):
        registry = CircuitBreakerRegistry()
        cb1 = CircuitBreaker(name="service1")
        cb2 = CircuitBreaker(name="service2")

        registry.register(cb1)
        registry.register(cb2)

        all_status = registry.get_all_status()

        assert "service1" in all_status
        assert "service2" in all_status
        assert all_status["service1"]["name"] == "service1"

    @pytest.mark.asyncio
    async def test_get_unhealthy(self):
        registry = CircuitBreakerRegistry()
        cb1 = CircuitBreaker(name="healthy", failure_threshold=2)
        cb2 = CircuitBreaker(name="unhealthy", failure_threshold=2, timeout=10.0)

        registry.register(cb1)
        registry.register(cb2)

        # Open cb2
        async def failing_func():
            raise Exception("Fail")

        for _ in range(2):
            with pytest.raises(Exception):
                await cb2.execute(failing_func)

        unhealthy = registry.get_unhealthy()

        assert "unhealthy" in unhealthy
        assert "healthy" not in unhealthy

    def test_reset_all(self):
        registry = CircuitBreakerRegistry()
        cb1 = CircuitBreaker(name="cb1")
        cb2 = CircuitBreaker(name="cb2")

        cb1._failure_count = 5
        cb2._failure_count = 3

        registry.register(cb1)
        registry.register(cb2)

        registry.reset_all()

        assert cb1._failure_count == 0
        assert cb2._failure_count == 0


class TestCircuitBreakerFailureRate:
    """Tests for sliding-window failure-rate tripping."""

    @pytest.mark.asyncio
    async def test_opens_on_failure_rate_without_consecutive_failures(self):
        # Consecutive threshold high enough to never trip; rate must trip
        cb = CircuitBreaker(
            name="test",
            failure_threshold=100,
            failure_rate_threshold=50.0,
            window_seconds=60.0,
            minimum_calls=6,
        )

        async def failing_func():
            raise Exception("Fail")

        async def success_func():
            return "ok"

        # Alternate S/F: never two consecutive failures, but 50% rate
        for _ in range(3):
            await cb.execute(success_func)
            with pytest.raises(Exception):
                await cb.execute(failing_func)

        assert cb.is_open

    @pytest.mark.asyncio
    async def test_stays_closed_below_minimum_calls(self):
        cb = CircuitBreaker(
            name="test",
            failure_threshold=100,
            failure_rate_threshold=50.0,
            minimum_calls=10,
        )

        async def failing_func():
            raise Exception("Fail")

        # 100% failure rate, but only 4 outcomes: not enough evidence
        for _ in range(4):
            with pytest.raises(Exception):
                await cb.execute(failing_func)

        assert cb.is_closed

    @pytest.mark.asyncio
    async def test_recovery_clears_the_window(self):
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            success_threshold=1,
            timeout=0.05,
            failure_rate_threshold=50.0,
            minimum_calls=2,
        )

        async def failing_func():
            raise Exception("Fail")

        async def success_func():
            return "ok"

        # Open, then recover through half-open
        for _ in range(2):
            with pytest.raises(Exception):
                await cb.execute(failing_func)
        assert cb.is_open

        await asyncio.sleep(0.1)
        await cb.execute(success_func)
        assert cb.is_closed

        # Pre-outage failures must not count toward the rate anymore
        with pytest.raises(Exception):
            await cb.execute(failing_func)
        assert cb.is_closed


class TestCircuitBreakerHalfOpenProbing:
    """Tests for probe limiting in half-open state."""

    @pytest.mark.asyncio
    async def test_half_open_admits_limited_concurrent_probes(self):
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            timeout=0.05,
            half_open_max_calls=1,
        )

        async def failing_func():
            raise Exception("Fail")

        # Open the circuit, then wait for the recovery timeout
        for _ in range(2):
            with pytest.raises(Exception):
                await cb.execute(failing_func)
        await asyncio.sleep(0.1)

        probe_started = asyncio.Event()
        release_probe = asyncio.Event()

        async def slow_probe():
            probe_started.set()
            await release_probe.wait()
            return "ok"

        # First call becomes the probe and holds the only slot
        probe_task = asyncio.create_task(cb.execute(slow_probe))
        await probe_started.wait()
        assert cb.is_half_open

        # Concurrent second call is rejected: recovering service is
        # tested by one probe, not hammered by the full request volume
        with pytest.raises(CircuitBreakerOpenException):
            await cb.execute(slow_probe)

        release_probe.set()
        assert await probe_task == "ok"

    @pytest.mark.asyncio
    async def test_probe_slot_is_released_after_completion(self):
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            success_threshold=2,
            timeout=0.05,
            half_open_max_calls=1,
        )

        async def failing_func():
            raise Exception("Fail")

        async def success_func():
            return "ok"

        for _ in range(2):
            with pytest.raises(Exception):
                await cb.execute(failing_func)
        await asyncio.sleep(0.1)

        # Sequential probes are each admitted (slot freed between them)
        await cb.execute(success_func)
        await cb.execute(success_func)
        assert cb.is_closed


class TestCircuitBreakerCallTimeout:
    """Tests for per-call timeout enforcement."""

    @pytest.mark.asyncio
    async def test_hanging_call_times_out_and_counts_as_failure(self):
        cb = CircuitBreaker(name="test", failure_threshold=2, call_timeout=0.05)

        async def hanging_func():
            await asyncio.sleep(10)  # never raises on its own

        for _ in range(2):
            with pytest.raises(asyncio.TimeoutError):
                await cb.execute(hanging_func)

        # The hanging downstream tripped the breaker despite raising nothing
        assert cb.is_open
        assert cb.metrics.failed_requests == 2

    @pytest.mark.asyncio
    async def test_fast_call_unaffected_by_timeout(self):
        cb = CircuitBreaker(name="test", call_timeout=1.0)

        async def fast_func():
            return "ok"

        assert await cb.execute(fast_func) == "ok"
        assert cb.is_closed


class TestCircuitBreakerSyncExecution:
    """Tests for sync callables running off the event loop."""

    @pytest.mark.asyncio
    async def test_sync_function_does_not_block_event_loop(self):
        import time as time_module

        cb = CircuitBreaker(name="test")

        def blocking_func():
            time_module.sleep(0.2)  # blocking I/O stand-in
            return "done"

        loop_ticks = 0

        async def ticker():
            nonlocal loop_ticks
            for _ in range(10):
                loop_ticks += 1
                await asyncio.sleep(0.02)

        # If blocking_func ran on the loop, ticker could not advance
        # until it finished
        result, _ = await asyncio.gather(cb.execute(blocking_func), ticker())

        assert result == "done"
        assert loop_ticks >= 5


class TestCircuitBreakerConcurrency:
    """Tests for circuit breaker under concurrent access."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_during_transition(self):
        cb = CircuitBreaker(
            name="test",
            failure_threshold=5,
            timeout=0.1
        )

        call_count = 0

        async def tracked_func():
            nonlocal call_count
            call_count += 1
            return "ok"

        # Run many concurrent requests
        tasks = [cb.execute(tracked_func) for _ in range(10)]
        results = await asyncio.gather(*tasks)

        assert all(r == "ok" for r in results)
        assert call_count == 10

    @pytest.mark.asyncio
    async def test_concurrent_failures(self):
        cb = CircuitBreaker(
            name="test",
            failure_threshold=5,
            timeout=10.0
        )

        async def failing_func():
            await asyncio.sleep(0.01)  # Simulate some work
            raise Exception("Fail")

        # Run concurrent failing requests
        tasks = [cb.execute(failing_func) for _ in range(10)]

        # Some will fail with Exception, some with CircuitBreakerOpenException
        results = await asyncio.gather(*tasks, return_exceptions=True)

        exception_count = sum(1 for r in results if isinstance(r, Exception))
        assert exception_count == 10

        # Circuit should be open after threshold failures
        assert cb.is_open
