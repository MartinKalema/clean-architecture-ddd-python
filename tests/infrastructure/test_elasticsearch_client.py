"""
Unit tests for ElasticsearchClient error handling and counting.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.exceptions import SearchEngineException
from src.infrastructure.external.elasticsearch_client import ElasticsearchClient


def _client_with(fake) -> ElasticsearchClient:
    client = ElasticsearchClient(logger=MagicMock())
    client._client = fake
    return client


@pytest.mark.asyncio
async def test_search_failure_raises_instead_of_returning_empty():
    """An ES outage must be distinguishable from 'no results'."""
    fake = MagicMock()
    fake.search = AsyncMock(side_effect=ConnectionError("ES down"))
    client = _client_with(fake)

    with pytest.raises(SearchEngineException):
        await client.search(index="books", query={"match_all": {}})


@pytest.mark.asyncio
async def test_index_failure_raises():
    fake = MagicMock()
    fake.index = AsyncMock(side_effect=ConnectionError("ES down"))
    client = _client_with(fake)

    with pytest.raises(SearchEngineException):
        await client.index(index="books", doc_id="1", document={"title": "x"})


@pytest.mark.asyncio
async def test_count_uses_count_api():
    """Counting must use _count: search hits.total caps at 10,000."""
    fake = MagicMock()
    fake.count = AsyncMock(return_value={"count": 123456})
    client = _client_with(fake)

    result = await client.count(index="books", query={"match_all": {}})

    assert result == 123456
    fake.count.assert_awaited_once_with(index="books", query={"match_all": {}})


@pytest.mark.asyncio
async def test_swap_alias_is_atomic():
    """Alias swap removes old targets and adds the new one in one call."""
    fake = MagicMock()
    fake.indices.exists_alias = AsyncMock(return_value=True)
    fake.indices.get_alias = AsyncMock(return_value={"books-000001": {}})
    fake.indices.update_aliases = AsyncMock()
    client = _client_with(fake)

    await client.swap_alias("books", "books-000002")

    fake.indices.update_aliases.assert_awaited_once_with(actions=[
        {"remove": {"index": "books-000001", "alias": "books"}},
        {"add": {"index": "books-000002", "alias": "books"}},
    ])
