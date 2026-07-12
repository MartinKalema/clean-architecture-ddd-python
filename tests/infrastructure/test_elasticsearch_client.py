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


@pytest.mark.asyncio
async def test_search_passes_stable_sort_and_cursor_to_elasticsearch():
    fake = MagicMock()
    fake.search = AsyncMock(return_value={
        "hits": {
            "total": {"value": 1},
            "hits": [{
                "_id": "book-1",
                "_score": None,
                "_source": {"title": "A"},
                "sort": ["A", "book-1"],
            }],
        }
    })
    client = _client_with(fake)
    sort = [{"title.keyword": "asc"}, {"id": "asc"}]

    result = await client.search(
        index="books",
        query={"match_all": {}},
        size=20,
        sort=sort,
        search_after=["A", "book-0"],
    )

    fake.search.assert_awaited_once_with(
        index="books",
        query={"match_all": {}},
        size=20,
        track_total_hits=True,
        sort=sort,
        search_after=["A", "book-0"],
    )
    assert result["hits"][0]["_sort"] == ["A", "book-1"]


@pytest.mark.asyncio
async def test_search_requests_exact_total_hits_for_public_pagination_metadata():
    fake = MagicMock()
    fake.search = AsyncMock(return_value={
        "hits": {
            "total": {"value": 125_001, "relation": "eq"},
            "hits": [],
        }
    })
    client = _client_with(fake)

    result = await client.search(index="books", query={"match_all": {}}, size=10)

    assert result["total"] == 125_001
    fake.search.assert_awaited_once_with(
        index="books",
        query={"match_all": {}},
        size=10,
        from_=0,
        track_total_hits=True,
    )


@pytest.mark.asyncio
async def test_reindex_cleanup_removes_only_the_target_owned_by_the_worker():
    fake = MagicMock()
    fake.indices.update_aliases = AsyncMock()
    client = _client_with(fake)

    await client.clear_reindex_target(
        "books",
        expected_target="books-build-owned-by-this-worker",
    )

    fake.indices.update_aliases.assert_awaited_once_with(actions=[{
        "remove": {
            "index": "books-build-owned-by-this-worker",
            "alias": "books__reindex_target",
            "must_exist": True,
        }
    }])


@pytest.mark.asyncio
async def test_read_model_write_is_versioned_and_dual_written():
    fake = MagicMock()
    fake.index = AsyncMock()
    fake.indices.exists_alias = AsyncMock(return_value=True)
    fake.indices.get_alias = AsyncMock(return_value={"books-new": {}})
    client = _client_with(fake)

    await client.index_read_model(
        "books", "book-1", {"id": "book-1", "title": "New", "version": 7}
    )

    assert {call.kwargs["index"] for call in fake.index.await_args_list} == {
        "books",
        "books-new",
    }
    assert {call.kwargs["version"] for call in fake.index.await_args_list} == {8}
    assert {call.kwargs["version_type"] for call in fake.index.await_args_list} == {
        "external_gte"
    }


@pytest.mark.asyncio
async def test_delete_tombstone_strictly_dominates_snapshot_version():
    fake = MagicMock()
    fake.delete = AsyncMock()
    fake.indices.exists_alias = AsyncMock(return_value=False)
    client = _client_with(fake)

    await client.delete_read_model(
        "books", "book-1", source={"id": "book-1", "version": 7}
    )

    fake.delete.assert_awaited_once_with(
        index="books",
        id="book-1",
        version=9,
        version_type="external_gte",
    )


@pytest.mark.asyncio
async def test_bulk_snapshot_uses_row_version_below_delete_tombstone():
    fake = MagicMock()
    fake.bulk = AsyncMock(return_value={"items": [{"index": {"status": 200}}]})
    client = _client_with(fake)

    success, errors = await client.bulk_index(
        "books-new", [{"id": "book-1", "title": "Old", "version": 7}]
    )

    action = fake.bulk.await_args.kwargs["operations"][0]["index"]
    assert action["version"] == 8
    assert action["version_type"] == "external_gte"
    assert (success, errors) == (1, 0)
