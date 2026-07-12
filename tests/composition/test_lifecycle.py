"""Container-owned resources close deterministically on every exit path."""
from unittest.mock import ANY, MagicMock, call

import pytest

from src.composition.lifecycle import ManagedResources


@pytest.mark.asyncio
async def test_resources_close_in_reverse_order_and_continue_after_failure():
    events: list[str] = []
    logger = MagicMock()

    class Resource:
        def __init__(self, name: str, *, fails: bool = False) -> None:
            self.name = name
            self.fails = fails

        async def close(self) -> None:
            events.append(self.name)
            if self.fails:
                raise RuntimeError(self.name)

    resources = ManagedResources(logger)
    resources.own("first", Resource("first"), "close")
    resources.own("second", Resource("second", fails=True), "close")
    resources.own("third", Resource("third"), "close")

    await resources.close()
    await resources.close()

    assert events == ["third", "second", "first"]
    assert logger.error.call_args_list == [
        call("Failed to close second resource", exception=ANY)
    ]
