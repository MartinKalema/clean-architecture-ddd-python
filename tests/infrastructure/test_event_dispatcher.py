"""
Unit tests for the event dispatcher and domain event consumer.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.lending import LoanCompleted, LoanCreated
from src.infrastructure.adapters.events import (
    EventDispatcher,
    deserialize_event,
    serialize_event,
)
from src.infrastructure.exceptions import EventDispatcherException
from src.infrastructure.adapters.events.domain_event_consumer import (
    DomainEventConsumer,
)


def _loan_created() -> LoanCreated:
    return LoanCreated(
        loan_id="loan-1",
        patron_id="patron-1",
        patron_email="patron@example.com",
        book_id="book-1",
        book_title="Domain-Driven Design",
        borrowed_at=datetime(2026, 7, 4, 12, 0),
        due_date=datetime(2026, 7, 18, 12, 0),
    )


class TestEventDispatcher:
    @pytest.mark.asyncio
    async def test_dispatches_to_subscribed_handler(self):
        handler = AsyncMock()
        dispatcher = EventDispatcher(subscriptions={LoanCreated: [handler]})

        event = _loan_created()
        await dispatcher.dispatch(event)

        handler.handle.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_ignores_events_without_subscribers(self):
        handler = AsyncMock()
        dispatcher = EventDispatcher(subscriptions={LoanCompleted: [handler]})

        await dispatcher.dispatch(_loan_created())

        handler.handle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failing_handler_does_not_block_others_but_raises_after(self):
        failing = AsyncMock()
        failing.handle.side_effect = RuntimeError("boom")
        succeeding = AsyncMock()
        logger = MagicMock()
        dispatcher = EventDispatcher(
            subscriptions={LoanCreated: [failing, succeeding]}, logger=logger
        )

        # Every handler gets its chance...
        with pytest.raises(EventDispatcherException):
            await dispatcher.dispatch(_loan_created())

        succeeding.handle.assert_awaited_once()
        logger.error.assert_called_once()
        # ...and the raise hands the message back to the delivery layer
        # for retry/DLQ, so a transient failure is not silently dropped

    @pytest.mark.asyncio
    async def test_subscribe_adds_handler(self):
        handler = AsyncMock()
        dispatcher = EventDispatcher()
        dispatcher.subscribe(LoanCreated, handler)

        await dispatcher.dispatch(_loan_created())

        handler.handle.assert_awaited_once()


class TestEventSerialization:
    def test_round_trip(self):
        event = _loan_created()

        import json
        payload = json.loads(serialize_event(event))
        restored = deserialize_event(payload)

        assert restored == event

    def test_unknown_event_type_returns_none(self):
        assert deserialize_event({"event_type": "NoSuchEvent"}) is None


class TestDomainEventConsumer:
    @pytest.mark.asyncio
    async def test_message_is_deserialized_and_dispatched(self):
        dispatcher = AsyncMock()
        consumer = DomainEventConsumer(
            kafka_client=MagicMock(),
            event_dispatcher=dispatcher,
            logger=MagicMock(),
        )

        import json
        event = _loan_created()
        payload = json.loads(serialize_event(event))

        await consumer._process_message("outbox.event.loan", "loan-1", payload)

        dispatcher.dispatch.assert_awaited_once()
        dispatched = dispatcher.dispatch.await_args.args[0]
        assert isinstance(dispatched, LoanCreated)
        assert dispatched == event

    @pytest.mark.asyncio
    async def test_unknown_event_type_is_skipped(self):
        dispatcher = AsyncMock()
        logger = MagicMock()
        consumer = DomainEventConsumer(
            kafka_client=MagicMock(),
            event_dispatcher=dispatcher,
            logger=logger,
        )

        await consumer._process_message(
            "outbox.event.loan", "x", {"event_type": "NoSuchEvent"}
        )

        dispatcher.dispatch.assert_not_awaited()
        logger.warning.assert_called_once()
