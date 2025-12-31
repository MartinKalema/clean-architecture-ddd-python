"""Run CircuitBreakerTestShape - overwhelm to 15k then recover."""
from scenarios import BrowserUser, BorrowerUser, LibrarianUser, PatronManagerUser
from shapes.circuit_breaker import CircuitBreakerTestShape
