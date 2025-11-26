"""
Outbox Processor - Background worker that polls the outbox and publishes events.

This should be run as a separate process or background task to ensure
events are reliably published to the message broker.
"""
import asyncio
from typing import Optional

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from src.domain.shared_kernel import Logger, EventDispatcher
from src.infrastructure.adapters.outbox import OutboxRepository, OutboxMessage


class OutboxProcessor:
    """
    Polls the outbox table and dispatches events to the message broker.

    Implements at-least-once delivery guarantee. Consumers must be idempotent.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        event_dispatcher: EventDispatcher,
        logger: Logger,
        poll_interval: float = 1.0,
        batch_size: int = 100
    ):
        self.session_factory = session_factory
        self.event_dispatcher = event_dispatcher
        self.logger = logger
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self._running = False

    async def start(self) -> None:
        """Start processing the outbox."""
        self._running = True
        self.logger.info("Outbox processor started")

        while self._running:
            try:
                processed = await self._process_batch()
                if processed == 0:
                    # No messages to process, wait before polling again
                    await asyncio.sleep(self.poll_interval)
            except Exception as e:
                self.logger.error(f"Error processing outbox batch", exception=e)
                await asyncio.sleep(self.poll_interval)

    async def stop(self) -> None:
        """Stop the processor gracefully."""
        self._running = False
        self.logger.info("Outbox processor stopped")

    async def _process_batch(self) -> int:
        """Process a batch of outbox messages. Returns count of processed messages."""
        async with self.session_factory() as session:
            repo = OutboxRepository(session)
            messages = await repo.get_unprocessed(limit=self.batch_size)

            if not messages:
                return 0

            processed_count = 0
            for message in messages:
                try:
                    await self._dispatch_message(message)
                    await repo.mark_as_processed(message.id)
                    processed_count += 1
                    self.logger.debug(f"Dispatched outbox message: {message.id}")
                except Exception as e:
                    await repo.mark_as_failed(message.id, str(e))
                    self.logger.error(f"Failed to dispatch outbox message {message.id}", exception=e)

            await session.commit()

            if processed_count > 0:
                self.logger.info(f"Processed {processed_count} outbox messages")

            return processed_count

    async def _dispatch_message(self, message: OutboxMessage) -> None:
        """Dispatch a single outbox message to the event dispatcher."""
        event_data = message.to_event_dict()

        # Create a simple event-like object for the dispatcher
        class OutboxEvent:
            def __init__(self, event_type: str, payload: dict):
                self.event_type = event_type
                self.__dict__.update(payload)

            def __class_getattr__(cls, name):
                return cls.__name__

        # The dispatcher expects the event class name, which we have
        await self.event_dispatcher.dispatch_raw(
            event_type=event_data["event_type"],
            payload=event_data["payload"]
        )
