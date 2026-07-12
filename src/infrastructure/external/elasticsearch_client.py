"""
Elasticsearch Client - External service wrapper for Elasticsearch.
"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, NoReturn, Optional

from elasticsearch import AsyncElasticsearch, ConflictError, NotFoundError

from src.infrastructure.exceptions import SearchEngineException

if TYPE_CHECKING:
    from src.application.ports import ILogger


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
        self._reindex_targets: dict[str, tuple[float, list[str]]] = {}

    REINDEX_TARGET_SUFFIX = "__reindex_target"
    REINDEX_TARGET_CACHE_SECONDS = 1.0

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
        assert self._client is not None
        return self._client

    def _raise(self, operation: str, error: Exception) -> NoReturn:
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
        external_version: int | None = None,
    ) -> bool:
        """Index a document."""
        client = await self._ensure_connected()

        try:
            kwargs: dict[str, Any] = {
                "index": index,
                "id": doc_id,
                "document": document,
            }
            if external_version is not None:
                kwargs.update(
                    version=external_version,
                    version_type="external_gte",
                )
            await client.index(**kwargs)
            if self._logger:
                self._logger.debug(f"Indexed document {index}/{doc_id}")
            return True
        except ConflictError:
            # A concurrent reindex may already have written a newer database
            # version. Ignoring the stale CDC write preserves monotonic state.
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

    async def delete(
        self, index: str, doc_id: str, external_version: int | None = None
    ) -> bool:
        """Delete a document by ID."""
        client = await self._ensure_connected()

        try:
            kwargs: dict[str, Any] = {"index": index, "id": doc_id}
            if external_version is not None:
                kwargs.update(
                    version=external_version,
                    version_type="external_gte",
                )
            await client.delete(**kwargs)
            if self._logger:
                self._logger.debug(f"Deleted document {index}/{doc_id}")
            return True
        except (NotFoundError, ConflictError):
            return True  # Already deleted
        except Exception as e:
            self._raise("delete", e)

    async def search(
        self,
        index: str,
        query: dict[str, Any],
        size: int = 10,
        from_: int = 0,
        sort: list[Any] | None = None,
        search_after: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a search query."""
        client = await self._ensure_connected()

        try:
            kwargs: dict[str, Any] = {
                "index": index,
                "query": query,
                "size": size,
                # This method's result feeds the public X-Total-Count header.
                # Elasticsearch otherwise caps hits.total at 10,000.
                "track_total_hits": True,
            }
            if sort:
                kwargs["sort"] = sort
            if search_after is not None:
                kwargs["search_after"] = search_after
            else:
                kwargs["from_"] = from_
            result = await client.search(**kwargs)
            return {
                "total": result["hits"]["total"]["value"],
                "hits": [
                    {
                        "id": hit["_id"],
                        "score": hit.get("_score"),
                        "_sort": hit.get("sort", []),
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
        sort: list[Any] | None = None,
        search_after: list[Any] | None = None,
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
            sort=sort,
            search_after=search_after,
        )

    async def index_read_model(
        self,
        logical_index: str,
        doc_id: str,
        document: dict[str, Any],
    ) -> bool:
        """Write to the live alias and any active reindex target.

        Reindex registers its new physical index before scanning PostgreSQL.
        CDC then dual-writes concurrent changes, preventing the alias swap from
        losing updates that arrived after a row was scanned.
        """
        version = self._document_external_version(document)
        targets = await self.get_read_model_write_targets(logical_index)
        await asyncio.gather(*(
            self.index(
                index=target,
                doc_id=doc_id,
                document=document,
                external_version=version,
            )
            for target in targets
        ))
        return True

    async def delete_read_model(
        self,
        logical_index: str,
        doc_id: str,
        *,
        source: dict[str, Any] | None = None,
    ) -> bool:
        version = self._document_external_version(source or {})
        # A delete must dominate a concurrent snapshot write of the row's
        # last version. The extra step leaves a tombstone strictly newer than
        # that snapshot, preventing resurrection during the alias rebuild.
        if version is not None:
            version += 1
        targets = await self.get_read_model_write_targets(logical_index)
        await asyncio.gather(*(
            self.delete(target, doc_id, external_version=version)
            for target in targets
        ))
        return True

    async def get_read_model_write_targets(
        self, logical_index: str
    ) -> list[str]:
        now = time.monotonic()
        cached = self._reindex_targets.get(logical_index)
        if cached and cached[0] > now:
            return cached[1]

        target_alias = f"{logical_index}{self.REINDEX_TARGET_SUFFIX}"
        targets = [logical_index, *await self.get_alias_indices(target_alias)]
        # Preserve order while removing duplicate physical target names.
        targets = list(dict.fromkeys(targets))
        self._reindex_targets[logical_index] = (
            now + self.REINDEX_TARGET_CACHE_SECONDS,
            targets,
        )
        return targets

    async def set_reindex_target(self, logical_index: str, target: str) -> None:
        """Atomically register one physical index for CDC dual-writes."""
        target_alias = f"{logical_index}{self.REINDEX_TARGET_SUFFIX}"
        actions: list[dict[str, Any]] = [
            {"remove": {"index": old, "alias": target_alias}}
            for old in await self.get_alias_indices(target_alias)
        ]
        actions.append({"add": {"index": target, "alias": target_alias}})
        client = await self._ensure_connected()
        try:
            await client.indices.update_aliases(actions=actions)
        except Exception as e:
            self._raise("set_reindex_target", e)
        self._reindex_targets.pop(logical_index, None)

    async def clear_reindex_target(
        self,
        logical_index: str,
        *,
        expected_target: str | None = None,
    ) -> None:
        """Remove CDC dual-write targets without clearing another job's target.

        Reindex workers pass ``expected_target`` so their cleanup action names
        only the physical index they created. ``must_exist`` turns lost
        ownership into a visible failure instead of silently clearing state
        that may have changed underneath the worker.
        """
        target_alias = f"{logical_index}{self.REINDEX_TARGET_SUFFIX}"
        targets = (
            [expected_target]
            if expected_target is not None
            else await self.get_alias_indices(target_alias)
        )
        if targets:
            client = await self._ensure_connected()
            try:
                actions = []
                for target in targets:
                    remove: dict[str, Any] = {
                        "index": target,
                        "alias": target_alias,
                    }
                    if expected_target is not None:
                        remove["must_exist"] = True
                    actions.append({"remove": remove})
                await client.indices.update_aliases(actions=actions)
            except Exception as e:
                self._raise("clear_reindex_target", e)
        self._reindex_targets.pop(logical_index, None)

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
        missing_ids = 0
        for doc in documents:
            doc_id = doc.get(id_field)
            if doc_id:
                action: dict[str, Any] = {"_index": index, "_id": doc_id}
                version = self._document_external_version(doc)
                if version is not None:
                    action.update(version=version, version_type="external_gte")
                operations.append({"index": action})
                operations.append(doc)
            else:
                missing_ids += 1

        if not operations:
            return 0, missing_ids

        try:
            result = await client.bulk(operations=operations)
            errors = 0
            for item in result["items"]:
                error = item.get("index", {}).get("error")
                if error and error.get("type") != "version_conflict_engine_exception":
                    errors += 1
            errors += missing_ids
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

    @staticmethod
    def _document_external_version(document: dict[str, Any]) -> int | None:
        raw = document.get("version")
        if raw is None:
            return None
        try:
            version = int(raw)
        except (TypeError, ValueError):
            return None
        # Elasticsearch external versions start at 1 while aggregates start
        # at 0. The offset preserves their ordering exactly.
        return version + 1 if version >= 0 else None
