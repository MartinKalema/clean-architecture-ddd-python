"""
Elasticsearch Client - External service wrapper for Elasticsearch.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from elasticsearch import AsyncElasticsearch, NotFoundError

from src.infrastructure.exceptions import SearchEngineException

if TYPE_CHECKING:
    from src.domain.shared_kernel import ILogger


class ElasticsearchClient:
    """
    Async client for Elasticsearch operations.

    Provides indexing, search, and document management functionality.
    Configuration is loaded from etcd via dependency injection.

    Failures raise SearchEngineException instead of returning empty
    results, so an outage is distinguishable from "no data" — callers
    decide whether to fall back (query repositories fall back to
    PostgreSQL) or surface the error.
    """

    def __init__(
        self,
        url: str = "http://localhost:9200",
        max_connections: int = 100,
        request_timeout: int = 30,
        max_retries: int = 3,
        username: str = "",
        password: str = "",
        verify_certs: bool = True,
        logger: Optional[ILogger] = None,
    ):
        self._url = url
        self._max_connections = max_connections
        self._request_timeout = request_timeout
        self._max_retries = max_retries
        self._username = username
        self._password = password
        self._verify_certs = verify_certs
        self._logger = logger
        self._client: Optional[AsyncElasticsearch] = None

    async def connect(self) -> None:
        """Establish connection to Elasticsearch with connection pooling."""
        if self._client is None:
            kwargs: dict[str, Any] = {
                "hosts": self._url,
                "request_timeout": self._request_timeout,
                "max_retries": self._max_retries,
                "retry_on_timeout": True,
                "connections_per_node": self._max_connections,
            }
            if self._username:
                kwargs["basic_auth"] = (self._username, self._password)
            if self._url.startswith("https"):
                kwargs["verify_certs"] = self._verify_certs
                kwargs["ssl_show_warn"] = self._verify_certs

            self._client = AsyncElasticsearch(**kwargs)
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
            try:
                await self.connect()
            except Exception as e:
                # Connection failures must honor the typed-exception contract
                # too, or they bypass the circuit breaker and PG fallback
                self._raise("connect", e)
        return self._client

    def _raise(self, operation: str, error: Exception) -> None:
        if self._logger:
            self._logger.error(f"Elasticsearch {operation} error: {error}")
        raise SearchEngineException(
            f"Elasticsearch {operation} failed: {error}",
            original_exception=error,
        )

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
            self._raise("index", e)

    async def get(self, index: str, doc_id: str) -> Optional[dict[str, Any]]:
        """Get a document by ID. Returns None only when the document is absent."""
        client = await self._ensure_connected()

        try:
            result = await client.get(index=index, id=doc_id)
            return result["_source"]
        except NotFoundError:
            return None
        except Exception as e:
            self._raise("get", e)

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
            self._raise("delete", e)

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
            self._raise("search", e)

    async def count(self, index: str, query: dict[str, Any]) -> int:
        """
        Count documents matching a query.

        Uses the _count API: search hits.total caps at 10,000 by default,
        so it must not be used for counting.
        """
        client = await self._ensure_connected()

        try:
            result = await client.count(index=index, query=query)
            return result["count"]
        except Exception as e:
            self._raise("count", e)

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
        aliases: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Create an index with mappings (and optionally settings/aliases)."""
        client = await self._ensure_connected()

        try:
            body: dict[str, Any] = {"mappings": mappings}
            if settings:
                body["settings"] = settings
            if aliases:
                body["aliases"] = aliases

            exists = await client.indices.exists(index=index)
            if not exists:
                await client.indices.create(index=index, body=body)
                if self._logger:
                    self._logger.info(f"Created index: {index}")
            return True
        except Exception as e:
            self._raise("create_index", e)

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
            self._raise("delete_index", e)

    async def get_alias_indices(self, alias: str) -> list[str]:
        """Return the physical indices an alias currently points to."""
        client = await self._ensure_connected()

        try:
            exists = await client.indices.exists_alias(name=alias)
            if not exists:
                return []
            result = await client.indices.get_alias(name=alias)
            return list(result.keys())
        except Exception as e:
            self._raise("get_alias_indices", e)

    async def swap_alias(self, alias: str, new_index: str) -> bool:
        """
        Atomically point an alias at a new index.

        Removes the alias from every index it currently targets and adds it
        to new_index in a single _aliases call, so readers never observe a
        missing or duplicated alias — this is what makes reindexing
        zero-downtime.
        """
        client = await self._ensure_connected()

        try:
            actions: list[dict[str, Any]] = [
                {"remove": {"index": old_index, "alias": alias}}
                for old_index in await self.get_alias_indices(alias)
            ]
            actions.append({"add": {"index": new_index, "alias": alias}})

            await client.indices.update_aliases(actions=actions)
            if self._logger:
                self._logger.info(f"Alias '{alias}' now points to {new_index}")
            return True
        except SearchEngineException:
            raise
        except Exception as e:
            self._raise("swap_alias", e)

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
            self._raise("bulk_index", e)

    async def refresh(self, index: str) -> None:
        """Make recently indexed documents visible to search."""
        client = await self._ensure_connected()

        try:
            await client.indices.refresh(index=index)
        except Exception as e:
            self._raise("refresh", e)

    async def ping(self) -> bool:
        """Check if connected to Elasticsearch."""
        if not self._client:
            return False
        try:
            return await self._client.ping()
        except Exception:
            return False
