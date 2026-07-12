"""
Circuit Breaker Pattern Implementation.

The circuit breaker prevents cascading failures by failing fast when a
downstream service is unhealthy. This protects the system from wasting
resources on requests that are likely to fail.

States:
- CLOSED: Normal operation, requests flow through
- OPEN: Service is unhealthy, requests fail immediately
- HALF_OPEN: Testing if service has recovered

The circuit opens on either of two conditions:
- failure_threshold consecutive failures (catches hard-down services
  quickly, even at low traffic), or
- failure rate >= failure_rate_threshold percent over the sliding
  window_seconds window, once at least minimum_calls outcomes have been
  observed (catches partial degradation that consecutive counting misses:
  a service failing 30% of requests rarely fails N in a row).

Recovery is probe-limited: in HALF_OPEN at most half_open_max_calls
requests are admitted concurrently, so a barely-recovered service is not
hit with the full request volume as its recovery test.

Async calls can be bounded with call_timeout so a hanging downstream counts
as a failure. Sync callables run in the default executor and must enforce
timeouts at the client/socket layer: cancelling an executor future does not
stop its underlying side effect and can otherwise create duplicates.

Usage:
    circuit_breaker = CircuitBreaker(
        name="sendgrid",
        failure_threshold=3,
        success_threshold=2,
        timeout=60.0,
    )

    @circuit_breaker
    async def send_email(to, subject, content):
        await sendgrid.send(to, subject, content)

    async with circuit_breaker:
        await sendgrid.send(to, subject, content)
"""
from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import time
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Deque, Optional, Tuple

from src.infrastructure.exceptions import CircuitBreakerOpenException

if TYPE_CHECKING:
    from src.application.ports import ILogger


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerMetrics:
    """Metrics for observability."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rejected_requests: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    state_changes: int = 0

    def record_success(self) -> None:
        self.total_requests += 1
        self.successful_requests += 1
        self.last_success_time = time.time()

    def record_failure(self) -> None:
        self.total_requests += 1
        self.failed_requests += 1
        self.last_failure_time = time.time()

    def record_rejection(self) -> None:
        self.total_requests += 1
        self.rejected_requests += 1

    def to_dict(self) -> dict:
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "rejected_requests": self.rejected_requests,
            "success_rate": (
                self.successful_requests / self.total_requests
                if self.total_requests > 0 else 0
            ),
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
            "state_changes": self.state_changes,
        }


class CircuitBreaker:
    """
    Production-grade circuit breaker for protecting external service calls.

    Features:
    - Thread-safe with asyncio locks
    - Consecutive-failure AND sliding-window failure-rate tripping
    - Probe-limited recovery testing (half-open admits few calls)
    - Per-call timeout for cancellable async calls
    - Sync callables dispatched to the executor (never block the loop)
    - Metrics for observability
    - Decorator and context manager support
    - Optional fallback function

    Args:
        name: Identifier for logging and metrics
        failure_threshold: Consecutive failures before opening circuit (default: 5)
        success_threshold: Successes in half-open before closing (default: 2)
        timeout: Seconds before testing recovery (default: 30)
        failure_rate_threshold: Percent of failures in the sliding window
                                that opens the circuit (default: 50.0)
        window_seconds: Length of the sliding window (default: 60)
        minimum_calls: Outcomes required in the window before the failure
                       rate is evaluated (default: 10)
        half_open_max_calls: Concurrent probes admitted in half-open (default: 1)
        call_timeout: Seconds before a cancellable async call counts as
                      failed. Sync clients require transport-level timeouts.
        excluded_exceptions: Exceptions that don't count as failures
        fallback: Optional function to call when circuit is open
        logger: Optional logger for observability
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: float = 30.0,
        failure_rate_threshold: float = 50.0,
        window_seconds: float = 60.0,
        minimum_calls: int = 10,
        half_open_max_calls: int = 1,
        call_timeout: Optional[float] = None,
        excluded_exceptions: tuple = (),
        fallback: Optional[Callable] = None,
        logger: Optional[ILogger] = None,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout
        self.failure_rate_threshold = failure_rate_threshold
        self.window_seconds = window_seconds
        self.minimum_calls = minimum_calls
        self.half_open_max_calls = half_open_max_calls
        self.call_timeout = call_timeout
        self.excluded_exceptions = excluded_exceptions
        self.fallback = fallback
        self._logger = logger or logging.getLogger(__name__)

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

        # Sliding window of (monotonic timestamp, is_failure) outcomes
        self._window: Deque[Tuple[float, bool]] = deque()
        # In-flight probes while HALF_OPEN
        self._half_open_in_flight = 0
        # Whether the current task's context-manager call is a probe
        self._ctx_is_probe: ContextVar[bool] = ContextVar(
            f"circuit_breaker_{name}_is_probe", default=False
        )

        self.metrics = CircuitBreakerMetrics()

    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        return self._state

    @property
    def is_closed(self) -> bool:
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        return self._state == CircuitState.HALF_OPEN

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to test recovery."""
        if self._last_failure_time is None:
            return True
        return time.time() - self._last_failure_time >= self.timeout

    def _time_until_retry(self) -> float:
        """Seconds remaining before retry is allowed."""
        if self._last_failure_time is None:
            return 0
        elapsed = time.time() - self._last_failure_time
        return max(0, self.timeout - elapsed)

    def _record_outcome(self, is_failure: bool) -> None:
        """Add an outcome to the sliding window and evict expired entries."""
        now = time.monotonic()
        self._window.append((now, is_failure))
        self._prune_window(now)

    def _prune_window(self, now: Optional[float] = None) -> None:
        now = now if now is not None else time.monotonic()
        cutoff = now - self.window_seconds
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()

    def _window_failure_rate(self) -> Optional[float]:
        """
        Failure rate (percent) over the sliding window.

        Returns None below minimum_calls: too few outcomes to judge.
        """
        self._prune_window()
        total = len(self._window)
        if total < self.minimum_calls:
            return None
        failures = sum(1 for _, is_failure in self._window if is_failure)
        return failures / total * 100

    async def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state with logging."""
        old_state = self._state
        self._state = new_state
        self.metrics.state_changes += 1

        if new_state == CircuitState.CLOSED:
            # Fresh start after recovery: pre-outage outcomes must not
            # re-trip the rate condition immediately
            self._window.clear()
        if new_state != CircuitState.HALF_OPEN:
            self._half_open_in_flight = 0

        log_msg = f"Circuit breaker '{self.name}': {old_state.value} -> {new_state.value}"
        if hasattr(self._logger, 'info'):
            self._logger.info(log_msg)
        else:
            logging.info(log_msg)

    async def _handle_success(self, is_probe: bool = False) -> None:
        """Handle a successful call."""
        self.metrics.record_success()
        self._record_outcome(is_failure=False)
        self._release_probe(is_probe)

        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                await self._transition_to(CircuitState.CLOSED)
                self._failure_count = 0
                self._success_count = 0
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    async def _handle_failure(self, exception: Exception, is_probe: bool = False) -> None:
        """Handle a failed call."""
        if isinstance(exception, self.excluded_exceptions):
            self._release_probe(is_probe)
            return

        self.metrics.record_failure()
        self._record_outcome(is_failure=True)
        self._release_probe(is_probe)
        self._last_failure_time = time.time()
        self._failure_count += 1

        if self._state == CircuitState.HALF_OPEN:
            await self._transition_to(CircuitState.OPEN)
            self._success_count = 0
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self.failure_threshold:
                await self._transition_to(CircuitState.OPEN)
            else:
                rate = self._window_failure_rate()
                if rate is not None and rate >= self.failure_rate_threshold:
                    if hasattr(self._logger, 'warning'):
                        self._logger.warning(
                            f"Circuit breaker '{self.name}': failure rate "
                            f"{rate:.1f}% over last {self.window_seconds:.0f}s "
                            f"exceeds {self.failure_rate_threshold:.1f}%"
                        )
                    await self._transition_to(CircuitState.OPEN)

    def _release_probe(self, is_probe: bool) -> None:
        if is_probe and self._half_open_in_flight > 0:
            self._half_open_in_flight -= 1

    async def _acquire(self) -> Tuple[bool, bool]:
        """
        Decide whether a call may execute.

        Returns:
            (allowed, is_probe): is_probe marks calls admitted in HALF_OPEN,
            which count against half_open_max_calls until they complete.
        """
        if self._state == CircuitState.CLOSED:
            return True, False

        if self._state == CircuitState.OPEN:
            if self._should_attempt_reset():
                await self._transition_to(CircuitState.HALF_OPEN)
                self._success_count = 0
                self._half_open_in_flight = 1
                return True, True
            return False, False

        # HALF_OPEN: admit a bounded number of concurrent probes
        if self._half_open_in_flight < self.half_open_max_calls:
            self._half_open_in_flight += 1
            return True, True
        return False, False

    async def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute a function with circuit breaker protection.

        Sync functions run in the default executor so they cannot block the
        event loop. They are not wrapped in an asyncio timeout because that
        cannot stop the underlying side effect; sync clients must enforce a
        transport-level timeout.

        Args:
            func: Function to execute (async or sync)
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result of func

        Raises:
            CircuitBreakerOpenException: If circuit is open (or half-open
                                         with all probe slots taken)
            asyncio.TimeoutError: If the call exceeds call_timeout
            Exception: Original exception if call fails
        """
        async with self._lock:
            allowed, is_probe = await self._acquire()

        if not allowed:
            self.metrics.record_rejection()
            if self.fallback:
                return (
                    await self.fallback(*args, **kwargs)
                    if inspect.iscoroutinefunction(self.fallback)
                    else self.fallback(*args, **kwargs)
                )
            raise CircuitBreakerOpenException(
                self.name,
                self._time_until_retry()
            )

        try:
            result = await self._run_call(func, *args, **kwargs)

            async with self._lock:
                await self._handle_success(is_probe)

            return result

        except Exception as e:
            async with self._lock:
                await self._handle_failure(e, is_probe)
            raise

    async def _run_call(self, func: Callable, *args, **kwargs) -> Any:
        """Run the protected call, off-loop for sync functions, with timeout."""
        if inspect.iscoroutinefunction(func):
            awaitable = func(*args, **kwargs)
            if self.call_timeout:
                return await asyncio.wait_for(
                    awaitable, timeout=self.call_timeout
                )
            return await awaitable

        loop = asyncio.get_running_loop()
        awaitable = loop.run_in_executor(
            None, functools.partial(func, *args, **kwargs)
        )
        # asyncio cannot cancel work that has already started in an executor.
        # Returning a timeout while it may still succeed would let a message
        # retry duplicate the side effect.
        return await awaitable

    def __call__(self, func: Callable) -> Callable:
        """Decorator for protecting async functions."""
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await self.execute(func, *args, **kwargs)
        return wrapper

    async def __aenter__(self) -> "CircuitBreaker":
        """Context manager entry."""
        async with self._lock:
            allowed, is_probe = await self._acquire()

        if not allowed:
            self.metrics.record_rejection()
            raise CircuitBreakerOpenException(
                self.name,
                self._time_until_retry()
            )

        # ContextVar is task-local, so concurrent tasks sharing this breaker
        # each see their own probe flag
        self._ctx_is_probe.set(is_probe)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Context manager exit."""
        is_probe = self._ctx_is_probe.get()
        async with self._lock:
            if exc_type is None:
                await self._handle_success(is_probe)
            elif exc_val is not None:
                await self._handle_failure(exc_val, is_probe)
        return False

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._window.clear()
        self._half_open_in_flight = 0

    def get_status(self) -> dict:
        """Get current status for monitoring."""
        failure_rate = self._window_failure_rate()
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self.failure_threshold,
            "success_threshold": self.success_threshold,
            "timeout": self.timeout,
            "failure_rate_threshold": self.failure_rate_threshold,
            "window_seconds": self.window_seconds,
            "window_calls": len(self._window),
            "window_failure_rate": round(failure_rate, 1) if failure_rate is not None else None,
            "call_timeout": self.call_timeout,
            "time_until_retry": self._time_until_retry() if self.is_open else 0,
            "metrics": self.metrics.to_dict(),
        }


class CircuitBreakerRegistry:
    """
    Registry for managing multiple circuit breakers.

    Useful for:
    - Centralized monitoring
    - Health checks
    - Bulk operations
    """

    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}

    def register(self, breaker: CircuitBreaker) -> None:
        """Register a circuit breaker."""
        self._breakers[breaker.name] = breaker

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get a circuit breaker by name."""
        return self._breakers.get(name)

    def get_all_status(self) -> dict[str, dict]:
        """Get status of all circuit breakers."""
        return {
            name: breaker.get_status()
            for name, breaker in self._breakers.items()
        }

    def get_unhealthy(self) -> list[str]:
        """Get names of open circuit breakers."""
        return [
            name for name, breaker in self._breakers.items()
            if breaker.is_open
        ]

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()
