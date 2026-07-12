"""
Resilience patterns for infrastructure adapters.

Provides:
- Circuit Breaker: Prevents cascading failures
- CircuitBreakerFactory: Creates and registers circuit breakers
- (Future) Retry: Automatic retry with backoff
- (Future) Bulkhead: Isolate failures
- (Future) Rate Limiter: Prevent overload
"""
from src.infrastructure.exceptions import CircuitBreakerOpenException

from .circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerMetrics,
    CircuitBreakerRegistry,
    CircuitState,
)
from .circuit_breaker_factory import CircuitBreakerFactory

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerFactory",
    "CircuitBreakerOpenException",
    "CircuitState",
    "CircuitBreakerMetrics",
    "CircuitBreakerRegistry",
]
