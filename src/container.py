"""
Dependency Injection Container.

This is the composition root - the only place where dependencies are wired together.
The container should ONLY contain wiring logic, not creation/business logic.
All factory logic belongs in the infrastructure layer.

CQRS Architecture:
- Commands: Write operations (AddBook, BorrowBook, ReturnBook)
- Queries: Read operations (ListBooks, GetBook)
"""
from dependency_injector import containers, providers

from src.application.cache_invalidation import (
    CacheNamespace,
    InvalidateCacheAfterCommand,
    NamespaceCacheInvalidation,
)
from src.application.command_handlers import (AddBookHandler,
                                              BorrowBookHandler,
                                              ReturnBookHandler)
from src.application.command_handlers.cancel_loan import CancelLoanHandler
from src.application.command_handlers.create_loan import CreateLoanHandler
from src.application.command_handlers.extend_loan import ExtendLoanHandler
from src.application.command_handlers.register_patron import \
    RegisterPatronHandler
from src.application.command_handlers.reinstate_patron import \
    ReinstatePatronHandler
from src.application.command_handlers.return_loan import ReturnLoanHandler
from src.application.command_handlers.suspend_patron import \
    SuspendPatronHandler
from src.application.command_handlers.confirm_book_borrow import \
    ConfirmBookBorrowHandler
from src.application.command_handlers.release_book_reservation import \
    ReleaseBookReservationHandler
from src.application.command_handlers.release_expired_reservations import \
    ReleaseExpiredReservationsHandler
from src.application.command_handlers.upgrade_patron_tier import \
    UpgradePatronTierHandler
from src.application.event_handlers import (
    CancelLoanOnBookReleasedHandler,
    ConfirmBorrowOnLoanCreatedHandler,
    CreateLoanOnBookReservedHandler,
    ReturnBookOnLoanCompletedHandler,
    SendLoanConfirmationEmailHandler,
)
from src.application.query_handlers import (
    GetBookHandler,
    GetBorrowOperationHandler,
    ListBooksHandler,
)
from src.application.query_handlers.get_loan import GetLoanHandler
from src.application.query_handlers.get_patron import GetPatronHandler
from src.application.query_handlers.list_patron_loans import \
    ListPatronLoansHandler
from src.application.query_handlers.list_patrons import ListPatronsHandler
from src.application.ports import EmailDeliveryException
from src.domain.catalog import (
    CatalogBookBorrowed,
    CatalogBookReleased,
    CatalogBookReserved,
)
from src.domain.lending import LoanCompleted, LoanCreated
from src.infrastructure.adapters.cache import CacheAdapter
from src.infrastructure.adapters.catalog import (BookQueryRepository,
                                                 CatalogUnitOfWork)
from src.infrastructure.adapters.cdc import ElasticsearchSyncConsumer
from src.infrastructure.adapters.cdc.kafka_projection_freshness import (
    KafkaProjectionFreshness,
)
from src.infrastructure.adapters.email.sendgrid_email_service import \
    SendGridEmailService
from src.infrastructure.adapters.etcd import EtcdAdapter
from src.infrastructure.adapters.events import (
    DomainEventConsumer,
    EventDispatcher,
    SqlAlchemyEventQuarantine,
    SqlAlchemyHandlerInbox,
)
from src.infrastructure.adapters.lending import (LoanQueryRepository,
                                                 LoanUnitOfWork)
from src.infrastructure.adapters.logger import LoggerFactory
from src.infrastructure.adapters.patron import (
    PatronBorrowerDirectoryAdapter,
    PatronQueryRepository,
    PatronUnitOfWork,
)
from src.infrastructure.adapters.resilience import (
    CircuitBreakerFactory,
    CircuitBreakerRegistry,
)
from src.infrastructure.external.elasticsearch_client import \
    ElasticsearchClient
from src.infrastructure.external.etcd_client import EtcdClient
from src.infrastructure.external.kafka_client import KafkaClient
from src.infrastructure.external.postgresql import PostgreSQL
from src.infrastructure.external.redis_client import RedisClient
from src.infrastructure.external.sendgrid_client import SendGridClient
from src.infrastructure.adapters.utc_clock import UtcClock


class ApplicationContainer(containers.DeclarativeContainer):
    """
    Application dependency injection container.

    Wires all dependencies together following CQRS pattern:
    - Command handlers for write operations
    - Query handlers for read operations
    """

    bootstrap = providers.Configuration(strict=True)
    configurations = providers.Configuration(strict=True)

    etcd_client = providers.Singleton(
        EtcdClient,
        host=bootstrap.etcd.host,
        port=bootstrap.etcd.port,
    )

    etcd_adapter = providers.Singleton(
        EtcdAdapter,
        client=etcd_client,
        config_prefix=bootstrap.etcd.prefix,
    )

    logger = providers.Singleton(
        LoggerFactory,
        config=configurations
    )

    clock = providers.Singleton(UtcClock)

    postgresql = providers.Singleton(
        PostgreSQL,
        db_url=configurations.database.url,
        pool_size=configurations.database.pool_size,
        max_overflow=configurations.database.max_overflow,
        pool_timeout=configurations.database.pool_timeout,
        pool_recycle=configurations.database.pool_recycle,
    )

    session_factory = providers.Singleton(
        lambda db: db.session_factory,
        db=postgresql
    )

    sendgrid_client = providers.Singleton(
        SendGridClient,
        api_key=configurations.sendgrid.api_key,
        logger=logger,
        request_timeout_seconds=configurations.sendgrid.request_timeout_seconds,
    )

    redis_client = providers.Singleton(
        RedisClient,
        url=configurations.redis.url,
        default_ttl=configurations.redis.cache_ttl,
        enabled=configurations.redis.enabled,
        logger=logger,
    )

    cache = providers.Singleton(
        CacheAdapter,
        client=redis_client,
    )

    book_cache_invalidation = providers.Singleton(
        NamespaceCacheInvalidation,
        cache=cache,
        namespace=CacheNamespace.BOOK,
        logger=logger,
    )

    patron_cache_invalidation = providers.Singleton(
        NamespaceCacheInvalidation,
        cache=cache,
        namespace=CacheNamespace.PATRON,
        logger=logger,
    )

    loan_cache_invalidation = providers.Singleton(
        NamespaceCacheInvalidation,
        cache=cache,
        namespace=CacheNamespace.LOAN,
        logger=logger,
    )

    # CDC Pipeline
    kafka_client = providers.Singleton(
        KafkaClient,
        bootstrap_servers=configurations.kafka.bootstrap_servers,
        consumer_max_retries=configurations.kafka.consumer_max_retries,
        retry_backoff_seconds=configurations.kafka.retry_backoff_seconds,
        consumer_max_poll_interval_ms=configurations.kafka.consumer_max_poll_interval_ms,
        message_processing_timeout_seconds=configurations.kafka.message_processing_timeout_seconds,
        internal_topic_replication_factor=configurations.kafka.internal_topic_replication_factor,
        logger=logger,
    )

    # Notification delivery has an independent consumer group and transport.
    # A slow/rejected SendGrid call must never hold the consumer that advances
    # Catalog/Lending workflow transitions.
    notification_kafka_client = providers.Singleton(
        KafkaClient,
        bootstrap_servers=configurations.kafka.bootstrap_servers,
        consumer_max_retries=configurations.kafka.consumer_max_retries,
        retry_backoff_seconds=configurations.kafka.retry_backoff_seconds,
        consumer_max_poll_interval_ms=configurations.kafka.consumer_max_poll_interval_ms,
        message_processing_timeout_seconds=configurations.kafka.message_processing_timeout_seconds,
        internal_topic_replication_factor=configurations.kafka.internal_topic_replication_factor,
        logger=logger,
    )

    elasticsearch_client = providers.Singleton(
        ElasticsearchClient,
        url=configurations.elasticsearch.url,
        max_connections=configurations.elasticsearch.max_connections,
        request_timeout=configurations.elasticsearch.request_timeout,
        max_retries=configurations.elasticsearch.max_retries,
        username=configurations.elasticsearch.username,
        password=configurations.elasticsearch.password,
        verify_certs=configurations.elasticsearch.verify_certs,
        logger=logger,
    )

    projection_freshness = providers.Singleton(
        KafkaProjectionFreshness,
        bootstrap_servers=configurations.kafka.bootstrap_servers,
        group_id=configurations.kafka.projection_group_id,
        topics=providers.List(
            "library.public.books",
            "library.public.patrons",
            "library.public.loans",
        ),
        logger=logger,
    )

    elasticsearch_sync_consumer = providers.Singleton(
        ElasticsearchSyncConsumer,
        kafka_client=kafka_client,
        elasticsearch_client=elasticsearch_client,
        topic_to_index=configurations.cdc.topic_to_index,
        logger=logger,
        cache=cache,
        group_id=configurations.kafka.projection_group_id,
    )

    circuit_breaker_registry = providers.Singleton(CircuitBreakerRegistry)

    sendgrid_circuit_breaker = providers.Singleton(
        CircuitBreakerFactory,
        name=configurations.circuit_breakers.sendgrid.name,
        failure_threshold=configurations.circuit_breakers.sendgrid.failure_threshold,
        success_threshold=configurations.circuit_breakers.sendgrid.success_threshold,
        timeout=configurations.circuit_breakers.sendgrid.timeout,
        failure_rate_threshold=configurations.circuit_breakers.sendgrid.failure_rate_threshold,
        window_seconds=configurations.circuit_breakers.sendgrid.window_seconds,
        minimum_calls=configurations.circuit_breakers.sendgrid.minimum_calls,
        half_open_max_calls=configurations.circuit_breakers.sendgrid.half_open_max_calls,
        # Deterministic request/configuration rejections are not
        # service-health signals. Rate limiting remains retryable.
        excluded_exceptions=(EmailDeliveryException,),
        logger=logger,
        registry=circuit_breaker_registry,
    )

    elasticsearch_circuit_breaker = providers.Singleton(
        CircuitBreakerFactory,
        name=configurations.circuit_breakers.elasticsearch.name,
        failure_threshold=configurations.circuit_breakers.elasticsearch.failure_threshold,
        success_threshold=configurations.circuit_breakers.elasticsearch.success_threshold,
        timeout=configurations.circuit_breakers.elasticsearch.timeout,
        failure_rate_threshold=configurations.circuit_breakers.elasticsearch.failure_rate_threshold,
        window_seconds=configurations.circuit_breakers.elasticsearch.window_seconds,
        minimum_calls=configurations.circuit_breakers.elasticsearch.minimum_calls,
        half_open_max_calls=configurations.circuit_breakers.elasticsearch.half_open_max_calls,
        call_timeout=configurations.circuit_breakers.elasticsearch.call_timeout,
        logger=logger,
        registry=circuit_breaker_registry,
    )

    email_service = providers.Singleton(
        SendGridEmailService,
        client=sendgrid_client,
        from_email=configurations.sendgrid.from_email,
        logger=logger,
        circuit_breaker=sendgrid_circuit_breaker,
    )

    catalog_uow = providers.Factory(
        CatalogUnitOfWork,
        session_factory=session_factory,
        logger=logger
    )

    book_query_repository = providers.Singleton(
        BookQueryRepository,
        session_factory=session_factory,
        elasticsearch_client=elasticsearch_client,
        circuit_breaker=elasticsearch_circuit_breaker,
        logger=logger,
        search_enabled=configurations.elasticsearch.enabled,
        projection_freshness=projection_freshness,
    )

    patron_query_repository = providers.Singleton(
        PatronQueryRepository,
        session_factory=session_factory,
        elasticsearch_client=elasticsearch_client,
        circuit_breaker=elasticsearch_circuit_breaker,
        logger=logger,
        search_enabled=configurations.elasticsearch.enabled,
        projection_freshness=projection_freshness,
    )

    borrower_directory = providers.Singleton(
        PatronBorrowerDirectoryAdapter,
        session_factory=session_factory,
    )

    add_book_operation = providers.Factory(
        AddBookHandler,
        uow=catalog_uow,
        logger=logger
    )

    add_book = providers.Factory(
        InvalidateCacheAfterCommand,
        operation=add_book_operation,
        invalidation=book_cache_invalidation,
        logger=logger,
    )

    borrow_book_operation = providers.Factory(
        BorrowBookHandler,
        uow=catalog_uow,
        borrower_directory=borrower_directory,
        logger=logger,
        clock=clock,
    )

    borrow_book = providers.Factory(
        InvalidateCacheAfterCommand,
        operation=borrow_book_operation,
        invalidation=book_cache_invalidation,
        logger=logger,
    )

    get_borrow_operation_handler = providers.Factory(
        GetBorrowOperationHandler,
        uow=catalog_uow,
    )

    return_book_operation = providers.Factory(
        ReturnBookHandler,
        uow=catalog_uow,
        logger=logger,
        clock=clock,
    )

    return_book = providers.Factory(
        InvalidateCacheAfterCommand,
        operation=return_book_operation,
        invalidation=book_cache_invalidation,
        logger=logger,
    )

    confirm_book_borrow_operation = providers.Factory(
        ConfirmBookBorrowHandler,
        uow=catalog_uow,
        logger=logger,
        clock=clock,
    )

    confirm_book_borrow = providers.Factory(
        InvalidateCacheAfterCommand,
        operation=confirm_book_borrow_operation,
        invalidation=book_cache_invalidation,
        logger=logger,
    )

    release_book_reservation_operation = providers.Factory(
        ReleaseBookReservationHandler,
        uow=catalog_uow,
        logger=logger,
        clock=clock,
    )

    release_book_reservation = providers.Factory(
        InvalidateCacheAfterCommand,
        operation=release_book_reservation_operation,
        invalidation=book_cache_invalidation,
        logger=logger,
    )

    release_expired_reservations_operation = providers.Factory(
        ReleaseExpiredReservationsHandler,
        uow=catalog_uow,
        logger=logger,
        clock=clock,
    )

    release_expired_reservations = providers.Factory(
        InvalidateCacheAfterCommand,
        operation=release_expired_reservations_operation,
        invalidation=book_cache_invalidation,
        logger=logger,
    )

    list_books_handler = providers.Factory(
        ListBooksHandler,
        query_repository=book_query_repository,
        cache=cache,
        logger=logger
    )

    get_book_handler = providers.Factory(
        GetBookHandler,
        query_repository=book_query_repository,
        cache=cache,
        logger=logger
    )

    # Patron Context
    patron_uow = providers.Factory(
        PatronUnitOfWork,
        session_factory=session_factory,
        logger=logger
    )

    register_patron_operation = providers.Factory(
        RegisterPatronHandler,
        uow=patron_uow,
        logger=logger,
        clock=clock,
    )

    register_patron = providers.Factory(
        InvalidateCacheAfterCommand,
        operation=register_patron_operation,
        invalidation=patron_cache_invalidation,
        logger=logger,
    )

    suspend_patron_operation = providers.Factory(
        SuspendPatronHandler,
        uow=patron_uow,
        logger=logger
    )

    suspend_patron = providers.Factory(
        InvalidateCacheAfterCommand,
        operation=suspend_patron_operation,
        invalidation=patron_cache_invalidation,
        logger=logger,
    )

    reinstate_patron_operation = providers.Factory(
        ReinstatePatronHandler,
        uow=patron_uow,
        logger=logger
    )

    reinstate_patron = providers.Factory(
        InvalidateCacheAfterCommand,
        operation=reinstate_patron_operation,
        invalidation=patron_cache_invalidation,
        logger=logger,
    )

    upgrade_patron_tier_operation = providers.Factory(
        UpgradePatronTierHandler,
        uow=patron_uow,
        logger=logger
    )

    upgrade_patron_tier = providers.Factory(
        InvalidateCacheAfterCommand,
        operation=upgrade_patron_tier_operation,
        invalidation=patron_cache_invalidation,
        logger=logger,
    )

    get_patron_handler = providers.Factory(
        GetPatronHandler,
        query_repository=patron_query_repository,
        cache=cache,
        logger=logger
    )

    list_patrons_handler = providers.Factory(
        ListPatronsHandler,
        query_repository=patron_query_repository,
        cache=cache,
        logger=logger
    )

    # Lending Context
    loan_uow = providers.Factory(
        LoanUnitOfWork,
        session_factory=session_factory,
        logger=logger
    )

    loan_query_repository = providers.Singleton(
        LoanQueryRepository,
        session_factory=session_factory,
        elasticsearch_client=elasticsearch_client,
        circuit_breaker=elasticsearch_circuit_breaker,
        logger=logger,
        search_enabled=configurations.elasticsearch.enabled,
        projection_freshness=projection_freshness,
    )

    create_loan_operation = providers.Factory(
        CreateLoanHandler,
        uow=loan_uow,
        borrower_directory=borrower_directory,
        logger=logger
    )

    create_loan = providers.Factory(
        InvalidateCacheAfterCommand,
        operation=create_loan_operation,
        invalidation=loan_cache_invalidation,
        logger=logger,
    )

    extend_loan_operation = providers.Factory(
        ExtendLoanHandler,
        uow=loan_uow,
        logger=logger,
        clock=clock,
    )

    extend_loan = providers.Factory(
        InvalidateCacheAfterCommand,
        operation=extend_loan_operation,
        invalidation=loan_cache_invalidation,
        logger=logger,
    )

    return_loan_operation = providers.Factory(
        ReturnLoanHandler,
        uow=loan_uow,
        logger=logger,
        clock=clock,
    )

    return_loan = providers.Factory(
        InvalidateCacheAfterCommand,
        operation=return_loan_operation,
        invalidation=loan_cache_invalidation,
        logger=logger,
    )

    cancel_loan_operation = providers.Factory(
        CancelLoanHandler,
        uow=loan_uow,
        logger=logger,
    )

    cancel_loan = providers.Factory(
        InvalidateCacheAfterCommand,
        operation=cancel_loan_operation,
        invalidation=loan_cache_invalidation,
        logger=logger,
    )

    get_loan_handler = providers.Factory(
        GetLoanHandler,
        query_repository=loan_query_repository,
        cache=cache,
        logger=logger
    )

    list_patron_loans_handler = providers.Factory(
        ListPatronLoansHandler,
        query_repository=loan_query_repository,
        cache=cache,
        logger=logger
    )

    # Domain Events (outbox -> Debezium -> Kafka -> event worker)
    send_loan_confirmation_email_handler = providers.Factory(
        SendLoanConfirmationEmailHandler,
        email_service=email_service,
        logger=logger
    )

    create_loan_on_book_reserved_handler = providers.Factory(
        CreateLoanOnBookReservedHandler,
        create_loan_operation=create_loan,
        release_book_reservation_operation=release_book_reservation,
        logger=logger
    )

    confirm_borrow_on_loan_created_handler = providers.Factory(
        ConfirmBorrowOnLoanCreatedHandler,
        confirm_book_borrow_operation=confirm_book_borrow,
        cancel_loan_operation=cancel_loan,
        logger=logger
    )

    cancel_loan_on_book_released_handler = providers.Factory(
        CancelLoanOnBookReleasedHandler,
        cancel_loan_operation=cancel_loan,
        logger=logger,
    )

    return_book_on_loan_completed_handler = providers.Factory(
        ReturnBookOnLoanCompletedHandler,
        return_book_operation=return_book,
        logger=logger
    )

    handler_inbox = providers.Singleton(
        SqlAlchemyHandlerInbox,
        session_factory=session_factory,
    )

    event_quarantine = providers.Singleton(
        SqlAlchemyEventQuarantine,
        session_factory=session_factory,
    )

    event_dispatcher = providers.Singleton(
        EventDispatcher,
        subscriptions=providers.Dict({
            CatalogBookReserved: providers.List(
                create_loan_on_book_reserved_handler.provider
            ),
            CatalogBookReleased: providers.List(
                cancel_loan_on_book_released_handler.provider
            ),
            LoanCreated: providers.List(
                confirm_borrow_on_loan_created_handler.provider
            ),
            LoanCompleted: providers.List(
                return_book_on_loan_completed_handler.provider
            ),
        }),
        logger=logger,
        inbox=handler_inbox,
    )

    notification_event_dispatcher = providers.Singleton(
        EventDispatcher,
        subscriptions=providers.Dict({
            CatalogBookBorrowed: providers.List(
                send_loan_confirmation_email_handler.provider
            ),
        }),
        logger=logger,
        inbox=handler_inbox,
    )

    domain_event_consumer = providers.Singleton(
        DomainEventConsumer,
        kafka_client=kafka_client,
        event_dispatcher=event_dispatcher,
        logger=logger,
        quarantine=event_quarantine,
        group_id=configurations.kafka.workflow_group_id,
        durable_delivery=True,
    )

    notification_event_consumer = providers.Singleton(
        DomainEventConsumer,
        kafka_client=notification_kafka_client,
        event_dispatcher=notification_event_dispatcher,
        logger=logger,
        topics=providers.List("outbox.event.book"),
        quarantine=event_quarantine,
        group_id=configurations.kafka.notification_group_id,
        durable_delivery=False,
    )


class Container(ApplicationContainer):
    """API-only composition root retained as the public FastAPI container."""

    wiring_config = containers.WiringConfiguration(modules=[
        "src.presentation.api.routes.book_routes",
        "src.presentation.api.routes.health_routes",
        "src.presentation.api.routes.loan_routes",
        "src.presentation.api.routes.patron_routes",
    ])


class CliContainer(ApplicationContainer):
    """CLI composition root; it never wires API modules."""

    wiring_config = containers.WiringConfiguration(modules=[
        "src.presentation.cli.commands.add_book_command",
        "src.presentation.cli.commands.list_books_command",
        "src.presentation.cli.commands.borrow_book_command",
    ])


class WorkflowContainer(ApplicationContainer):
    """Correctness-critical cross-context workflow worker composition root."""


class NotificationContainer(ApplicationContainer):
    """Optional notification worker composition root."""


class ProjectionContainer(ApplicationContainer):
    """Elasticsearch projection worker composition root."""


class ReaperContainer(ApplicationContainer):
    """Expired-reservation reaper composition root."""


class MaintenanceContainer(ApplicationContainer):
    """Short-lived administrative command composition root."""
