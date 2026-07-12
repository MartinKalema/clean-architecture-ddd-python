from unittest.mock import AsyncMock

import pytest

from src.infrastructure.adapters.maintenance import DurableStateRetentionService


@pytest.mark.asyncio
async def test_durable_state_retention_rejects_unsafe_horizons_before_io():
    service = DurableStateRetentionService(AsyncMock())

    with pytest.raises(ValueError, match="retention days"):
        await service.prune(processed_inbox_days=0)


@pytest.mark.asyncio
async def test_durable_state_retention_bounds_batch_work_before_io():
    service = DurableStateRetentionService(AsyncMock())

    with pytest.raises(ValueError, match="batch_size"):
        await service.prune(batch_size=0)
    with pytest.raises(ValueError, match="max_batches_per_table"):
        await service.prune(max_batches_per_table=0)
