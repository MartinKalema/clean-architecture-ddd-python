"""
Resilience patterns for infrastructure adapters.

Provides:
- Circuit Breaker: Prevents cascading failures
- CircuitBreakerFactory: Creates and registers circuit breakers
- (Future) Retry: Automatic retry with backoff
- (Future) Bulkhead: Isolate failures
- (Future) Rate Limiter: Prevent overload
"""
from .circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerMetrics,
    CircuitBreakerRegistry,
    circuit_breaker_registry,
)
from .circuit_breaker_factory import CircuitBreakerFactory

# Re-export from canonical location for convenience
from src.infrastructure.exceptions import CircuitBreakerOpenException

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerFactory",
    "CircuitBreakerOpenException",
    "CircuitState",
    "CircuitBreakerMetrics",
    "CircuitBreakerRegistry",
    "circuit_breaker_registry",
]
