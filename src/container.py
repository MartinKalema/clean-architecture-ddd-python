"""
Dependency Injection Container.

This is the composition root - the only place where dependencies are wired together.
The container should ONLY contain wiring logic, not creation/business logic.
All factory logic belongs in the infrastructure layer.

CQRS Architecture:
- Commands: Write operations (AddBook, BorrowBook, ReturnBook)
- Queries: Read operations (ListBooks, GetBook)
"""
import os

from dependency_injector import containers, providers

from src.application.command_handlers import (AddBookHandler,
                                              BorrowBookHandler,
                                              ReturnBookHandler)
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
from src.application.event_handlers import (ConfirmBorrowOnLoanCreatedHandler,
                                            CreateLoanOnBookReservedHandler,
                                            SendLoanConfirmationEmailHandler)
from src.application.query_handlers import GetBookHandler, ListBooksHandler
from src.application.query_handlers.get_loan import GetLoanHandler
from src.application.query_handlers.get_patron import GetPatronHandler
from src.application.query_handlers.list_patron_loans import \
    ListPatronLoansHandler
from src.application.query_handlers.list_patrons import ListPatronsHandler
from src.domain.catalog import CatalogBookReserved
from src.domain.lending import LoanCreated
from src.infrastructure.adapters.cache import CacheAdapter
from src.infrastructure.adapters.catalog import (BookQueryRepository,
                                                 CatalogUnitOfWork)
from src.infrastructure.adapters.cdc import ElasticsearchSyncConsumer
from src.infrastructure.adapters.email.sendgrid_email_service import \
    SendGridEmailService
from src.infrastructure.adapters.etcd import EtcdAdapter
from src.infrastructure.adapters.events import (DomainEventConsumer,
                                                EventDispatcher)
from src.infrastructure.adapters.lending import (LoanQueryRepository,
                                                 LoanUnitOfWork)
from src.infrastructure.adapters.logger import LoggerFactory
from src.infrastructure.adapters.patron import (PatronQueryRepository,
                                                PatronUnitOfWork)
from src.infrastructure.adapters.resilience import CircuitBreakerFactory
from src.infrastructure.external.elasticsearch_client import \
    ElasticsearchClient
from src.infrastructure.external.etcd_client import EtcdClient
from src.infrastructure.external.kafka_client import KafkaClient
from src.infrastructure.external.postgresql import PostgreSQL
from src.infrastructure.external.redis_client import RedisClient
from src.infrastructure.external.sendgrid_client import SendGridClient


class Container(containers.DeclarativeContainer):
    """
    Application dependency injection container.

    Wires all dependencies together following CQRS pattern:
    - Command handlers for write operations
    - Query handlers for read operations
    """

    wiring_config = containers.WiringConfiguration(modules=[
        "src.presentation.api.routes.book_routes",
        "src.presentation.api.routes.health_routes",
        "src.presentation.api.routes.loan_routes",
        "src.presentation.api.routes.patron_routes",
        "src.presentation.cli.commands.add_book_command",
        "src.presentation.cli.commands.list_books_command",
        "src.presentation.cli.commands.borrow_book_command"
    ])

    configurations = providers.Configuration()

    etcd_client = providers.Singleton(
        EtcdClient,
        host=os.environ.get("ETCD_HOST", "localhost"),
        port=int(os.environ.get("ETCD_PORT", "2379")),
    )

    etcd_adapter = providers.Singleton(
        EtcdAdapter,
        client=etcd_client,
        config_prefix=os.environ.get("ETCD_CONFIG_PREFIX", "/config/"),
    )

    logger = providers.Singleton(
        LoggerFactory,
        config=configurations
    )

    postgresql = providers.Singleton(
        PostgreSQL,
        db_url=configurations.database.url,
        pool_size=configurations.database.pool_size,
        max_overflow=configurations.database.max_overflow,
        pool_timeout=configurations.database.pool_timeout,
        pool_recycle=configurations.database.pool_recycle,
    )

    session_factory = providers.Resource(
        lambda db: db.session_factory,
        db=postgresql
    )

    sendgrid_client = providers.Singleton(
        SendGridClient,
        api_key=configurations.sendgrid.api_key,
        logger=logger
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

    # CDC Pipeline
    kafka_client = providers.Singleton(
        KafkaClient,
        bootstrap_servers=configurations.kafka.bootstrap_servers,
        consumer_max_retries=configurations.kafka.consumer_max_retries,
        retry_backoff_seconds=configurations.kafka.retry_backoff_seconds,
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

    elasticsearch_sync_consumer = providers.Singleton(
        ElasticsearchSyncConsumer,
        kafka_client=kafka_client,
        elasticsearch_client=elasticsearch_client,
        topic_to_index=configurations.cdc.topic_to_index,
        logger=logger,
    )

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
        call_timeout=configurations.circuit_breakers.sendgrid.call_timeout,
        logger=logger,
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
    )

    email_service = providers.Singleton(
        SendGridEmailService,
        client=sendgrid_client,
        from_email=configurations.sendgrid.from_email,
        admin_email=configurations.sendgrid.admin_email,
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
    )

    add_book_handler = providers.Factory(
        AddBookHandler,
        uow=catalog_uow,
        logger=logger
    )

    borrow_book_handler = providers.Factory(
        BorrowBookHandler,
        uow=catalog_uow,
        logger=logger
    )

    return_book_handler = providers.Factory(
        ReturnBookHandler,
        uow=catalog_uow,
        logger=logger
    )

    confirm_book_borrow_handler = providers.Factory(
        ConfirmBookBorrowHandler,
        uow=catalog_uow,
        logger=logger
    )

    release_book_reservation_handler = providers.Factory(
        ReleaseBookReservationHandler,
        uow=catalog_uow,
        logger=logger
    )

    release_expired_reservations_handler = providers.Factory(
        ReleaseExpiredReservationsHandler,
        uow=catalog_uow,
        logger=logger
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

    patron_query_repository = providers.Singleton(
        PatronQueryRepository,
        session_factory=session_factory,
        elasticsearch_client=elasticsearch_client,
        circuit_breaker=elasticsearch_circuit_breaker,
        logger=logger,
    )

    register_patron_handler = providers.Factory(
        RegisterPatronHandler,
        uow=patron_uow,
        logger=logger
    )

    suspend_patron_handler = providers.Factory(
        SuspendPatronHandler,
        uow=patron_uow,
        logger=logger
    )

    reinstate_patron_handler = providers.Factory(
        ReinstatePatronHandler,
        uow=patron_uow,
        logger=logger
    )

    upgrade_patron_tier_handler = providers.Factory(
        UpgradePatronTierHandler,
        uow=patron_uow,
        logger=logger
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
    )

    create_loan_handler = providers.Factory(
        CreateLoanHandler,
        uow=loan_uow,
        logger=logger
    )

    extend_loan_handler = providers.Factory(
        ExtendLoanHandler,
        uow=loan_uow,
        logger=logger
    )

    return_loan_handler = providers.Factory(
        ReturnLoanHandler,
        uow=loan_uow,
        logger=logger
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
        create_loan_handler=create_loan_handler,
        release_book_reservation_handler=release_book_reservation_handler,
        patron_query_repository=patron_query_repository,
        logger=logger
    )

    confirm_borrow_on_loan_created_handler = providers.Factory(
        ConfirmBorrowOnLoanCreatedHandler,
        confirm_book_borrow_handler=confirm_book_borrow_handler,
        logger=logger
    )

    event_dispatcher = providers.Singleton(
        EventDispatcher,
        subscriptions=providers.Dict({
            CatalogBookReserved: providers.List(create_loan_on_book_reserved_handler),
            LoanCreated: providers.List(
                confirm_borrow_on_loan_created_handler,
                send_loan_confirmation_email_handler,
            ),
        }),
        logger=logger
    )

    domain_event_consumer = providers.Singleton(
        DomainEventConsumer,
        kafka_client=kafka_client,
        event_dispatcher=event_dispatcher,
        logger=logger
    )
