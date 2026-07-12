"""Application decorator that keeps cache-aside reads coherent after writes."""
from __future__ import annotations

from typing import Generic, Protocol, TypeVar

from src.application.ports import ICache, ILogger

C = TypeVar("C")
R = TypeVar("R")
CommandT = TypeVar("CommandT", contravariant=True)
ResultT = TypeVar("ResultT", covariant=True)


class CommandHandler(Protocol[CommandT, ResultT]):
    async def handle(self, command: CommandT) -> ResultT: ...


class CacheInvalidatingHandler(Generic[C, R]):
    """Invalidate one read-model namespace after a successful command.

    Cache failure is deliberately non-fatal: the cache adapter treats backend
    errors as misses, while a successful domain commit must not be reported as
    failed. Namespace invalidation favors correctness over fragile hand-built
    key lists and is implemented as bounded SCAN/UNLINK batches by the adapter.
    """

    def __init__(
        self,
        handler: CommandHandler[C, R],
        cache: ICache,
        entity_type: str,
        logger: ILogger | None = None,
    ) -> None:
        self._handler = handler
        self._cache = cache
        self._entity_type = entity_type
        self._logger = logger

    async def handle(self, command: C) -> R:
        result = await self._handler.handle(command)
        try:
            fenced = await self._cache.invalidate_all(self._entity_type)
            if fenced is False and self._logger is not None:
                self._logger.warning(
                    f"Cache invalidation fence is recovering for "
                    f"{self._entity_type}; reads in this process bypass cache"
                )
        except Exception as error:
            # The write has already committed. Reporting failure would invite
            # a harmful retry (especially for non-idempotent legacy callers).
            if self._logger is not None:
                self._logger.warning(
                    f"Cache invalidation failed for {self._entity_type}: "
                    f"{type(error).__name__}"
                )
        return result
