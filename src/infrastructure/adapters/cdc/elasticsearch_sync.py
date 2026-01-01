"""
Elasticsearch Sync Consumer

Consumes CDC events from Debezium via Kafka and syncs them to Elasticsearch.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.domain.shared_kernel import ILogger
    from src.infrastructure.external.elasticsearch_client import ElasticsearchClient
    from src.infrastructure.external.kafka_client import KafkaClient


class ElasticsearchSyncConsumer:
    """
    Consumes CDC events from Kafka and syncs to Elasticsearch.

    Debezium captures row-level changes from PostgreSQL and publishes
    them to Kafka topics. This consumer transforms those events and
    indexes them in Elasticsearch for fast searching.

    Cache consistency is handled via TTL-based expiry rather than
    explicit invalidation, providing eventual consistency.
    """

    def __init__(
        self,
        kafka_client: KafkaClient,
        elasticsearch_client: ElasticsearchClient,
        topic_to_index: dict[str, str],
        logger: ILogger,
    ) -> None:
        self._kafka = kafka_client
        self._elasticsearch = elasticsearch_client
        self._topic_to_index = topic_to_index
        self._logger = logger
        self._running = False

    def transform_book(self, data: dict[str, Any]) -> dict[str, Any]:
        """Transform book CDC event to ES document."""
        return {
            "id": data.get("id"),
            "title": data.get("title"),
            "author": data.get("author"),
            "is_borrowed": data.get("is_borrowed", False),
            "borrowed_at": self._parse_timestamp(data.get("borrowed_at")),
            "return_due_date": self._parse_timestamp(data.get("return_due_date")),
        }

    def transform_patron(self, data: dict[str, Any]) -> dict[str, Any]:
        """Transform patron CDC event to ES document."""
        first_name = data.get("first_name", "")
        last_name = data.get("last_name", "")
        return {
            "id": data.get("id"),
            "first_name": first_name,
            "last_name": last_name,
            "full_name": f"{first_name} {last_name}".strip(),
            "email": data.get("email"),
            "membership_tier": data.get("membership_tier"),
            "is_suspended": data.get("is_suspended", False),
            "suspended_reason": data.get("suspended_reason"),
            "registered_at": self._parse_timestamp(data.get("registered_at")),
            "current_loan_count": data.get("current_loan_count", 0),
        }

    def transform_loan(self, data: dict[str, Any]) -> dict[str, Any]:
        """Transform loan CDC event to ES document."""
        due_date = self._parse_timestamp(data.get("due_date"))
        is_overdue = False
        if due_date and data.get("status") == "active":
            try:
                due_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                is_overdue = due_dt < datetime.now(timezone.utc)
            except (ValueError, TypeError):
                pass

        return {
            "id": data.get("id"),
            "patron_id": data.get("patron_id"),
            "patron_email": data.get("patron_email"),
            "catalog_book_id": data.get("catalog_book_id"),
            "book_title": data.get("book_title"),
            "borrowed_at": self._parse_timestamp(data.get("borrowed_at")),
            "due_date": due_date,
            "returned_at": self._parse_timestamp(data.get("returned_at")),
            "status": data.get("status"),
            "is_overdue": is_overdue,
        }

    def _parse_timestamp(self, value: Any) -> Optional[str]:
        """Parse timestamp from various formats."""
        if value is None:
            return None
        if isinstance(value, int):
            # Debezium sends timestamps as microseconds since epoch
            return datetime.fromtimestamp(value / 1_000_000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        if isinstance(value, str):
            return value
        return None

    async def _process_message(self, topic: str, key: dict | None, value: dict | None) -> None:
        """Process a single CDC message."""
        index = self._topic_to_index.get(topic)
        if not index:
            self._logger.warning(f"Unknown topic: {topic}")
            return

        # Debezium CDC event structure
        # value = {"before": {...}, "after": {...}, "op": "c/u/d/r"}
        # op: c=create, u=update, d=delete, r=read (snapshot)

        if value is None:
            # Tombstone message (delete)
            if key and "id" in key:
                doc_id = key["id"]
                self._logger.info(f"Deleting {index}/{doc_id}")
                await self._elasticsearch.delete(index=index, doc_id=doc_id)
            return

        op = value.get("op")
        after = value.get("after")
        before = value.get("before")

        if op == "d":
            # Delete operation
            if before and "id" in before:
                doc_id = before["id"]
                self._logger.info(f"Deleting {index}/{doc_id}")
                await self._elasticsearch.delete(index=index, doc_id=doc_id)
        elif op in ("c", "u", "r"):
            # Create, Update, or Read (snapshot)
            if after:
                doc_id = after.get("id")
                if not doc_id:
                    self._logger.warning(f"No ID in message: {after}")
                    return

                # Transform based on index type
                if index == "books":
                    doc = self.transform_book(after)
                elif index == "patrons":
                    doc = self.transform_patron(after)
                elif index == "loans":
                    doc = self.transform_loan(after)
                else:
                    doc = after

                self._logger.info(f"Indexing {index}/{doc_id}")
                await self._elasticsearch.index(index=index, doc_id=doc_id, document=doc)

    async def start(self) -> None:
        """Start the consumer loop."""
        self._logger.info("Connecting to Kafka and Elasticsearch...")

        await self._kafka.connect_consumer(
            topics=list(self._topic_to_index.keys()),
            group_id="es-sync-consumer",
        )
        await self._elasticsearch.connect()

        self._running = True
        self._logger.info("Starting consumer loop...")

        try:
            async for _ in self._kafka.consume(handler=self._process_message):
                if not self._running:
                    break
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the consumer."""
        self._running = False
        await self._kafka.close()
        await self._elasticsearch.close()
        self._logger.info("Consumer stopped")
