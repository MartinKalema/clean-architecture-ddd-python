"""CDC (Change Data Capture) adapters module."""

from src.infrastructure.adapters.cdc.elasticsearch_sync import ElasticsearchSyncConsumer

__all__ = ["ElasticsearchSyncConsumer"]
