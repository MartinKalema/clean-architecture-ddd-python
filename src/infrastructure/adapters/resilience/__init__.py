"""
Resilience patterns for infrastructure adapters.

Provides:
- Circuit Breaker: Prevents cascading failures
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

# Re-export from canonical location for convenience
from src.infrastructure.exceptions import CircuitBreakerOpenException

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerOpenException",
    "CircuitState",
    "CircuitBreakerMetrics",
    "CircuitBreakerRegistry",
    "circuit_breaker_registry",
]
