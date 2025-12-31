"""
Circuit Breaker Factory for creating and registering circuit breakers.

Encapsulates the creation and registration logic, keeping the container
free of side effects and creation logic.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .circuit_breaker import CircuitBreaker, circuit_breaker_registry

if TYPE_CHECKING:
    from src.domain.shared_kernel import ILogger


class CircuitBreakerFactory:
    """
    Factory for creating and registering circuit breaker instances.

    Callable factory - returns CircuitBreaker instance, not CircuitBreakerFactory.

    Handles:
    - Circuit breaker instantiation with configuration
    - Automatic registration with the global registry

    Usage in container:
        rabbitmq_cb = providers.Singleton(
            CircuitBreakerFactory,
            name="rabbitmq",
            failure_threshold=config.circuit_breakers.rabbitmq.failure_threshold,
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
    ) -> CircuitBreaker:
        """
        Create and register a circuit breaker.

        Args:
            name: Identifier for logging and monitoring
            failure_threshold: Failures before opening circuit
            success_threshold: Successes in half-open before closing
            timeout: Seconds before testing recovery
            logger: Logger instance for observability

        Returns:
            Configured and registered CircuitBreaker instance
        """
        circuit_breaker = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            timeout=timeout,
            logger=logger,
        )

        circuit_breaker_registry.register(circuit_breaker)

        return circuit_breaker
