"""
Elasticsearch Client - External service wrapper for Elasticsearch.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from elasticsearch import AsyncElasticsearch, NotFoundError

if TYPE_CHECKING:
    from src.domain.shared_kernel import ILogger


class ElasticsearchClient:
    """
    Async client for Elasticsearch operations.

    Provides indexing, search, and document management functionality.
    Configuration is loaded from etcd via dependency injection.
    """

    def __init__(
        self,
        url: str = "http://localhost:9200",
        logger: Optional[ILogger] = None,
    ):
        self._url = url
        self._logger = logger
        self._client: Optional[AsyncElasticsearch] = None

    async def connect(self) -> None:
        """Establish connection to Elasticsearch."""
        if self._client is None:
            self._client = AsyncElasticsearch(
                hosts=self._url,
                verify_certs=False,
                ssl_show_warn=False,
            )
            info = await self._client.info()
            if self._logger:
                self._logger.info(f"Connected to Elasticsearch {info['version']['number']} at {self._url}")

    async def close(self) -> None:
        """Close the Elasticsearch connection."""
        if self._client:
            await self._client.close()
            self._client = None
            if self._logger:
                self._logger.info("Disconnected from Elasticsearch")

    async def _ensure_connected(self) -> AsyncElasticsearch:
        """Ensure we have an active connection."""
        if self._client is None:
            await self.connect()
        return self._client

    async def index(
        self,
        index: str,
        doc_id: str,
        document: dict[str, Any],
    ) -> bool:
        """Index a document."""
        client = await self._ensure_connected()

        try:
            await client.index(index=index, id=doc_id, document=document)
            if self._logger:
                self._logger.debug(f"Indexed document {index}/{doc_id}")
            return True
        except Exception as e:
            if self._logger:
                self._logger.error(f"Elasticsearch index error: {e}")
            return False

    async def get(self, index: str, doc_id: str) -> Optional[dict[str, Any]]:
        """Get a document by ID."""
        client = await self._ensure_connected()

        try:
            result = await client.get(index=index, id=doc_id)
            return result["_source"]
        except NotFoundError:
            return None
        except Exception as e:
            if self._logger:
                self._logger.error(f"Elasticsearch get error: {e}")
            return None

    async def delete(self, index: str, doc_id: str) -> bool:
        """Delete a document by ID."""
        client = await self._ensure_connected()

        try:
            await client.delete(index=index, id=doc_id)
            if self._logger:
                self._logger.debug(f"Deleted document {index}/{doc_id}")
            return True
        except NotFoundError:
            return True  # Already deleted
        except Exception as e:
            if self._logger:
                self._logger.error(f"Elasticsearch delete error: {e}")
            return False

    async def search(
        self,
        index: str,
        query: dict[str, Any],
        size: int = 10,
        from_: int = 0,
    ) -> dict[str, Any]:
        """Execute a search query."""
        client = await self._ensure_connected()

        try:
            result = await client.search(
                index=index,
                query=query,
                size=size,
                from_=from_,
            )
            return {
                "total": result["hits"]["total"]["value"],
                "hits": [
                    {
                        "id": hit["_id"],
                        "score": hit["_score"],
                        **hit["_source"],
                    }
                    for hit in result["hits"]["hits"]
                ],
            }
        except Exception as e:
            if self._logger:
                self._logger.error(f"Elasticsearch search error: {e}")
            return {"total": 0, "hits": []}

    async def search_text(
        self,
        index: str,
        query_text: str,
        fields: list[str],
        size: int = 10,
        from_: int = 0,
    ) -> dict[str, Any]:
        """Execute a multi-match text search."""
        return await self.search(
            index=index,
            query={
                "multi_match": {
                    "query": query_text,
                    "fields": fields,
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            },
            size=size,
            from_=from_,
        )

    async def create_index(
        self,
        index: str,
        mappings: dict[str, Any],
        settings: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Create an index with mappings."""
        client = await self._ensure_connected()

        try:
            body = {"mappings": mappings}
            if settings:
                body["settings"] = settings

            exists = await client.indices.exists(index=index)
            if not exists:
                await client.indices.create(index=index, body=body)
                if self._logger:
                    self._logger.info(f"Created index: {index}")
            return True
        except Exception as e:
            if self._logger:
                self._logger.error(f"Elasticsearch create_index error: {e}")
            return False

    async def delete_index(self, index: str) -> bool:
        """Delete an index."""
        client = await self._ensure_connected()

        try:
            exists = await client.indices.exists(index=index)
            if exists:
                await client.indices.delete(index=index)
                if self._logger:
                    self._logger.info(f"Deleted index: {index}")
            return True
        except Exception as e:
            if self._logger:
                self._logger.error(f"Elasticsearch delete_index error: {e}")
            return False

    async def bulk_index(
        self,
        index: str,
        documents: list[dict[str, Any]],
        id_field: str = "id",
    ) -> tuple[int, int]:
        """
        Bulk index documents.

        Returns:
            Tuple of (success_count, error_count)
        """
        client = await self._ensure_connected()

        operations = []
        for doc in documents:
            doc_id = doc.get(id_field)
            if doc_id:
                operations.append({"index": {"_index": index, "_id": doc_id}})
                operations.append(doc)

        if not operations:
            return 0, 0

        try:
            result = await client.bulk(operations=operations)
            errors = sum(1 for item in result["items"] if item.get("index", {}).get("error"))
            success = len(documents) - errors
            return success, errors
        except Exception as e:
            if self._logger:
                self._logger.error(f"Elasticsearch bulk_index error: {e}")
            return 0, len(documents)

    async def ping(self) -> bool:
        """Check if connected to Elasticsearch."""
        if not self._client:
            return False
        try:
            return await self._client.ping()
        except Exception:
            return False
