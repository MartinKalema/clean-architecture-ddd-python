"""Explicit post-command cache invalidation policies and decorator."""
from __future__ import annotations

from enum import Enum
from typing import Generic, Protocol, TypeVar

from src.application.ports import ICache, ICommandHandler, ILogger

C = TypeVar("C")
R = TypeVar("R")
class CacheNamespace(str, Enum):
    """The complete set of application-owned cache namespaces."""

    BOOK = "book"
    PATRON = "patron"
    LOAN = "loan"


class CacheInvalidation(Protocol):
    """Cache maintenance applied after a committed command."""

    @property
    def label(self) -> str: ...

    async def apply(self) -> None: ...


class NamespaceCacheInvalidation:
    """Invalidate one complete read-model namespace."""

    def __init__(
        self,
        cache: ICache,
        namespace: CacheNamespace,
        logger: ILogger | None = None,
    ) -> None:
        self._cache = cache
        self._namespace = namespace
        self._logger = logger

    @property
    def label(self) -> str:
        return self._namespace.value

    async def apply(self) -> None:
        fenced = await self._cache.invalidate_all(self._namespace.value)
        if fenced is False and self._logger is not None:
            self._logger.warning(
                f"Cache invalidation fence is recovering for "
                f"{self._namespace.value}; reads in this process bypass cache"
            )


class InvalidateCacheAfterCommand(Generic[C, R]):
    """Apply a cache policy after an operation completes successfully.

    Cache failure is deliberately non-fatal: the cache adapter treats backend
    errors as misses, while a successful domain commit must not be reported as
    failed. The operation is therefore never retried merely because cache
    maintenance failed after its transaction committed.
    """

    def __init__(
        self,
        operation: ICommandHandler[C, R],
        invalidation: CacheInvalidation,
        logger: ILogger | None = None,
    ) -> None:
        self._operation = operation
        self._invalidation = invalidation
        self._logger = logger

    async def handle(self, command: C) -> R:
        result = await self._operation.handle(command)
        try:
            await self._invalidation.apply()
        except Exception as error:
            # The write has already committed. Reporting failure would invite
            # a harmful retry after the command has already committed.
            if self._logger is not None:
                self._logger.warning(
                    f"Cache invalidation failed for {self._invalidation.label}: "
                    f"{type(error).__name__}"
                )
        return result
