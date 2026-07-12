"""
Unit tests for the event dispatcher and domain event consumer.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.container import Container
from src.domain.catalog import CatalogBookBorrowed
from src.domain.lending import LoanCancelled, LoanCompleted, LoanCreated
from src.infrastructure.adapters.events import (
    EventDispatcher,
    InvalidEventEnvelopeError,
    deserialize_event,
    serialize_event,
)
from src.infrastructure.exceptions import (
    DurableMessageHandlingException,
    EventDispatcherException,
    UnrecoverableMessageException,
)
from src.infrastructure.adapters.events.domain_event_consumer import (
    DomainEventConsumer,
)


def _loan_created() -> LoanCreated:
    return LoanCreated(
        loan_id="loan-1",
        reservation_id="11111111-1111-4111-8111-111111111111",
        reservation_generation=3,
        patron_id="patron-1",
        patron_email="patron@example.com",
        book_id="book-1",
        book_title="Domain-Driven Design",
        borrowed_at=datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc),
        due_date=datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc),
    )


class TestEventDispatcher:
    def test_composition_root_isolates_optional_notifications(self):
        workflow_subscriptions = (
            Container.event_dispatcher.kwargs["subscriptions"].kwargs
        )
        notification_subscriptions = (
            Container.notification_event_dispatcher.kwargs["subscriptions"].kwargs
        )

        assert CatalogBookBorrowed not in workflow_subscriptions
        assert CatalogBookBorrowed in notification_subscriptions
        assert Container.domain_event_consumer.kwargs["durable_delivery"] is True
        assert (
            Container.notification_event_consumer.kwargs["durable_delivery"]
            is False
        )
        assert (
            Container.domain_event_consumer.kwargs["kafka_client"]
            is not Container.notification_event_consumer.kwargs["kafka_client"]
        )

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

    @pytest.mark.asyncio
    async def test_factory_subscription_resolves_fresh_handler_per_delivery(self):
        handlers = []

        def factory():
            handler = AsyncMock()
            handlers.append(handler)
            return handler

        dispatcher = EventDispatcher(subscriptions={LoanCreated: [factory]})

        await dispatcher.dispatch(_loan_created())
        await dispatcher.dispatch(_loan_created())

        assert len(handlers) == 2
        handlers[0].handle.assert_awaited_once()
        handlers[1].handle.assert_awaited_once()


class TestEventSerialization:
    def test_round_trip(self):
        event = _loan_created()

        import json
        payload = json.loads(serialize_event(event))
        restored = deserialize_event(payload)

        assert restored == event

    def test_flat_event_type_is_rejected_for_quarantine(self):
        with pytest.raises(InvalidEventEnvelopeError):
            deserialize_event({"event_type": "NoSuchEvent"})

    def test_cancelled_loan_is_registered_and_round_trips(self):
        event = LoanCancelled(
            loan_id="loan-1",
            reservation_id="11111111-1111-4111-8111-111111111111",
            reservation_generation=3,
            patron_id="patron-1",
            book_id="book-1",
            reason="catalog reservation expired",
        )

        import json

        restored = deserialize_event(json.loads(serialize_event(event)))

        assert restored == event


class TestDomainEventConsumer:
    @pytest.mark.asyncio
    async def test_start_uses_configured_group_and_delivery_policy(self):
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
        consumer = DomainEventConsumer(
            kafka_client=kafka,
            event_dispatcher=AsyncMock(),
            logger=MagicMock(),
            topics=["outbox.event.book"],
            group_id="notification-worker-v1",
            durable_delivery=False,
        )

        await consumer.start()

        kafka.connect_consumer.assert_awaited_once_with(
            topics=["outbox.event.book"],
            group_id="notification-worker-v1",
        )
        assert kafka.consume_kwargs["retry_forever"] is False

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
        identity = dispatcher.dispatch.await_args.kwargs["delivery_identity"]
        assert identity.contract_name == "library.lending.loan-created"
        assert identity.contract_version == 1
        assert len(identity.payload_hash) == 64

    @pytest.mark.asyncio
    async def test_unknown_event_type_is_quarantined(self):
        dispatcher = AsyncMock()
        logger = MagicMock()
        quarantine = AsyncMock()
        quarantine.quarantine.return_value = "quarantine-1"
        consumer = DomainEventConsumer(
            kafka_client=MagicMock(),
            event_dispatcher=dispatcher,
            logger=logger,
            quarantine=quarantine,
        )

        with pytest.raises(UnrecoverableMessageException):
            await consumer._process_message(
                "outbox.event.loan", "x", {"event_type": "NoSuchEvent"}
            )

        dispatcher.dispatch.assert_not_awaited()
        quarantine.quarantine.assert_awaited_once()
        logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_known_event_with_invalid_schema_is_unrecoverable(self):
        consumer = DomainEventConsumer(
            kafka_client=MagicMock(),
            event_dispatcher=AsyncMock(),
            logger=MagicMock(),
        )

        with pytest.raises(UnrecoverableMessageException):
            await consumer._process_message(
                "outbox.event.loan",
                "loan-1",
                {"event_type": "LoanCompleted", "loan_id": "loan-1"},
            )

    @pytest.mark.asyncio
    async def test_failed_state_transition_is_marked_for_durable_retry(self):
        dispatcher = AsyncMock()
        dispatcher.dispatch.side_effect = RuntimeError("database down")
        consumer = DomainEventConsumer(
            kafka_client=MagicMock(),
            event_dispatcher=dispatcher,
            logger=MagicMock(),
        )
        import json

        payload = json.loads(serialize_event(_loan_created()))

        with pytest.raises(DurableMessageHandlingException):
            await consumer._process_message(
                "outbox.event.loan", "loan-1", payload
            )
