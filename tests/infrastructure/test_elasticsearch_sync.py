from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.adapters.cdc.elasticsearch_sync import ElasticsearchSyncConsumer
from src.infrastructure.exceptions import UnrecoverableMessageException


def _consumer(es=None, cache=None):
    return ElasticsearchSyncConsumer(
        kafka_client=MagicMock(),
        elasticsearch_client=es or MagicMock(),
        topic_to_index={"library.public.books": "books"},
        logger=MagicMock(),
        cache=cache,
    )


def test_projection_does_not_call_reserved_book_borrowed():
    document = _consumer().transform_book(
        {"id": "book-1", "status": "reserved", "version": 4}
    )

    assert document["is_borrowed"] is False
    assert document["version"] == 4


def test_loan_projection_does_not_persist_time_stale_overdue_flag():
    document = _consumer().transform_loan(
        {
            "id": "loan-1",
            "status": "active",
            "due_date": "2020-01-01T00:00:00Z",
            "version": 2,
        }
    )

    assert "is_overdue" not in document
    assert document["version"] == 2


@pytest.mark.asyncio
async def test_cdc_update_uses_reindex_aware_dual_write():
    es = MagicMock()
    es.index_read_model = AsyncMock()
    consumer = _consumer(es)

    await consumer._process_message(
        "library.public.books",
        {"id": "book-1"},
        {
            "op": "u",
            "before": {"id": "book-1", "version": 1},
            "after": {
                "id": "book-1",
                "title": "Updated",
                "author": "Author",
                "status": "available",
                "version": 2,
            },
        },
    )

    es.index_read_model.assert_awaited_once()
    assert es.index_read_model.await_args.args[:2] == ("books", "book-1")


@pytest.mark.asyncio
async def test_cdc_invalidates_cache_after_projection_update():
    es = MagicMock()
    es.index_read_model = AsyncMock()
    cache = AsyncMock()
    consumer = _consumer(es, cache)

    await consumer._process_message(
        "library.public.books",
        {"id": "book-1"},
        {
            "op": "u",
            "after": {
                "id": "book-1",
                "title": "Current",
                "author": "Author",
                "status": "borrowed",
                "version": 3,
            },
        },
    )

    es.index_read_model.assert_awaited_once()
    cache.invalidate_entity.assert_awaited_once_with("book", "book-1")


@pytest.mark.asyncio
async def test_cdc_delete_carries_before_version_to_tombstone():
    es = MagicMock()
    es.delete_read_model = AsyncMock()
    consumer = _consumer(es)
    before = {"id": "book-1", "version": 7}

    await consumer._process_message(
        "library.public.books",
        {"id": "book-1"},
        {"op": "d", "before": before, "after": None},
    )

    es.delete_read_model.assert_awaited_once_with(
        "books", "book-1", source=before
    )


@pytest.mark.asyncio
async def test_structurally_unknown_cdc_operation_is_unrecoverable():
    consumer = _consumer()

    with pytest.raises(UnrecoverableMessageException, match="Unsupported CDC operation"):
        await consumer._process_message(
            "library.public.books",
            {"id": "book-1"},
            {"op": "future-op", "after": {"id": "book-1"}},
        )


@pytest.mark.asyncio
async def test_projection_consumer_uses_durable_retry_policy():
    class Kafka:
        def __init__(self):
            self.connect_consumer = AsyncMock()
            self.close = AsyncMock()
            self.consume_kwargs = None

        async def consume(self, **kwargs):
            self.consume_kwargs = kwargs
            if False:
                yield None

    kafka = Kafka()
    es = MagicMock()
    es.connect = AsyncMock()
    es.close = AsyncMock()
    consumer = ElasticsearchSyncConsumer(
        kafka_client=kafka,
        elasticsearch_client=es,
        topic_to_index={"library.public.books": "books"},
        logger=MagicMock(),
        group_id="projection-worker-v1",
    )

    await consumer.start()

    kafka.connect_consumer.assert_awaited_once_with(
        topics=["library.public.books"],
        group_id="projection-worker-v1",
    )
    assert kafka.consume_kwargs["retry_forever"] is True
    assert kafka.consume_kwargs["park_unrecoverable"] is False
