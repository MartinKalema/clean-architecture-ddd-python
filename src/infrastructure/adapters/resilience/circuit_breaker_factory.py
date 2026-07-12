"""
Circuit Breaker Factory for creating and registering circuit breakers.

Encapsulates the creation and registration logic, keeping the container
free of side effects and creation logic.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .circuit_breaker import CircuitBreaker, circuit_breaker_registry

if TYPE_CHECKING:
    from src.application.ports import ILogger


class CircuitBreakerFactory:
    """
    Factory for creating and registering circuit breaker instances.

    Callable factory - returns CircuitBreaker instance, not CircuitBreakerFactory.

    Handles:
    - Circuit breaker instantiation with configuration
    - Automatic registration with the global registry

    Usage in container:
        sendgrid_cb = providers.Singleton(
            CircuitBreakerFactory,
            name="sendgrid",
            failure_threshold=config.circuit_breakers.sendgrid.failure_threshold,
            ...
        )
    """

    def __new__(  # type: ignore[misc]
        cls,
        name: str,
        failure_threshold: int,
        success_threshold: int,
        timeout: float,
        logger: ILogger,
        failure_rate_threshold: float = 50.0,
        window_seconds: float = 60.0,
        minimum_calls: int = 10,
        half_open_max_calls: int = 1,
        call_timeout: float | None = None,
        excluded_exceptions: tuple = (),
    ) -> CircuitBreaker:
        """
        Create and register a circuit breaker.

        Args:
            name: Identifier for logging and monitoring
            failure_threshold: Consecutive failures before opening circuit
            success_threshold: Successes in half-open before closing
            timeout: Seconds before testing recovery
            logger: Logger instance for observability
            failure_rate_threshold: Percent of failures in the sliding
                                    window that opens the circuit
            window_seconds: Length of the sliding window
            minimum_calls: Outcomes required before the rate is evaluated
            half_open_max_calls: Concurrent probes admitted in half-open
            call_timeout: Seconds before an in-flight call counts as failed
            excluded_exceptions: Exception types that do not count as
                                 failures (request-level rejections that
                                 say nothing about service health)

        Returns:
            Configured and registered CircuitBreaker instance
        """
        circuit_breaker = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            timeout=timeout,
            failure_rate_threshold=failure_rate_threshold,
            window_seconds=window_seconds,
            minimum_calls=minimum_calls,
            half_open_max_calls=half_open_max_calls,
            call_timeout=call_timeout,
            excluded_exceptions=excluded_exceptions,
            logger=logger,
        )

        circuit_breaker_registry.register(circuit_breaker)

        return circuit_breaker
