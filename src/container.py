"""
Dependency Injection Container.

This is the composition root - the only place where dependencies are wired together.
The container should ONLY contain wiring logic, not creation/business logic.
All factory logic belongs in the infrastructure layer.

CQRS Architecture:
- Commands: Write operations (AddBook, BorrowBook, ReturnBook)
- Queries: Read operations (ListBooks, GetBook)

Message Brokers:
- RabbitMQ: Task queues, job processing
- Kafka: Event streaming, domain events (used by default for domain events)
"""
from dependency_injector import containers, providers

from src.application.command_handlers import (AddBookHandler,
                                              BorrowBookHandler,
                                              ReturnBookHandler)
from src.application.event_handlers.book_handlers import BookHandlers
from src.application.query_handlers import GetBookHandler, ListBooksHandler
from src.infrastructure.adapters.email.sendgrid_email_service import \
    SendGridEmailService
from src.infrastructure.adapters.logger import LoggerFactory
from src.infrastructure.adapters.messaging.kafka_event_dispatcher import \
    KafkaEventDispatcher
from src.infrastructure.adapters.messaging.rabbitmq_event_dispatcher import \
    RabbitMQEventDispatcher
from src.infrastructure.adapters.repositories.sql_book_query_repository import \
    SQLBookQueryRepository
from src.infrastructure.adapters.repositories.sqlalchemy_unit_of_work import \
    SqlAlchemyUnitOfWork
from src.infrastructure.adapters.resilience import CircuitBreakerFactory
from src.infrastructure.adapters.templates.jinja2_template_renderer import \
    Jinja2TemplateRenderer
from src.infrastructure.configurations.settings import load_config
from src.infrastructure.external.database import Database
from src.infrastructure.external.kafka_client import KafkaClient
from src.infrastructure.external.rabbitmq_client import RabbitMQClient
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
        "src.presentation.cli.commands.add_book_command",
        "src.presentation.cli.commands.list_books_command",
        "src.presentation.cli.commands.borrow_book_command"
    ])

    config = providers.Configuration()
    config.from_dict(load_config())

    logger = providers.Singleton(
        LoggerFactory,
        config=config
    )

    database = providers.Singleton(
        Database,
        db_url=config.database.url,
        pool_size=config.database.pool_size,
        max_overflow=config.database.max_overflow,
        pool_timeout=config.database.pool_timeout,
        pool_recycle=config.database.pool_recycle,
    )

    session_factory = providers.Resource(
        lambda db: db.session_factory,
        db=database
    )

    rabbitmq_client = providers.Singleton(
        RabbitMQClient,
        amqp_url=config.rabbitmq.url,
        logger=logger
    )

    kafka_client = providers.Singleton(
        KafkaClient,
        bootstrap_servers=config.kafka.bootstrap_servers,
        logger=logger
    )

    sendgrid_client = providers.Singleton(
        SendGridClient,
        api_key=config.sendgrid.api_key,
        logger=logger
    )

    rabbitmq_circuit_breaker = providers.Singleton(
        CircuitBreakerFactory,
        name="rabbitmq",
        failure_threshold=config.circuit_breakers.rabbitmq.failure_threshold,
        success_threshold=config.circuit_breakers.rabbitmq.success_threshold,
        timeout=config.circuit_breakers.rabbitmq.timeout,
        logger=logger,
    )

    kafka_circuit_breaker = providers.Singleton(
        CircuitBreakerFactory,
        name="kafka",
        failure_threshold=config.circuit_breakers.kafka.failure_threshold,
        success_threshold=config.circuit_breakers.kafka.success_threshold,
        timeout=config.circuit_breakers.kafka.timeout,
        logger=logger,
    )

    sendgrid_circuit_breaker = providers.Singleton(
        CircuitBreakerFactory,
        name="sendgrid",
        failure_threshold=config.circuit_breakers.sendgrid.failure_threshold,
        success_threshold=config.circuit_breakers.sendgrid.success_threshold,
        timeout=config.circuit_breakers.sendgrid.timeout,
        logger=logger,
    )

    rabbitmq_event_dispatcher = providers.Singleton(
        RabbitMQEventDispatcher,
        client=rabbitmq_client,
        exchange_name=config.rabbitmq.exchange_name,
        logger=logger,
        circuit_breaker=rabbitmq_circuit_breaker,
    )

    kafka_event_dispatcher = providers.Singleton(
        KafkaEventDispatcher,
        client=kafka_client,
        topic_prefix=config.kafka.topic_prefix,
        logger=logger,
        circuit_breaker=kafka_circuit_breaker,
    )

    email_service = providers.Singleton(
        SendGridEmailService,
        client=sendgrid_client,
        from_email=config.sendgrid.from_email,
        admin_email=config.sendgrid.admin_email,
        logger=logger,
        circuit_breaker=sendgrid_circuit_breaker,
    )

    template_renderer = providers.Singleton(
        Jinja2TemplateRenderer,
        template_dir=config.templates.dir,
        template_map=config.templates.map,
        logger=logger
    )

    book_handlers = providers.Singleton(
        BookHandlers,
        email_service=email_service,
        template_renderer=template_renderer,
        logger=logger
    )

    uow = providers.Factory(
        SqlAlchemyUnitOfWork,
        session_factory=session_factory,
        event_dispatcher=kafka_event_dispatcher
    )

    book_query_repository = providers.Singleton(
        SQLBookQueryRepository,
        session_factory=session_factory
    )

    add_book_handler = providers.Factory(
        AddBookHandler,
        uow=uow,
        logger=logger
    )

    borrow_book_handler = providers.Factory(
        BorrowBookHandler,
        uow=uow,
        logger=logger
    )

    return_book_handler = providers.Factory(
        ReturnBookHandler,
        uow=uow,
        logger=logger
    )

    list_books_handler = providers.Factory(
        ListBooksHandler,
        query_repository=book_query_repository,
        logger=logger
    )

    get_book_handler = providers.Factory(
        GetBookHandler,
        query_repository=book_query_repository,
        logger=logger
    )
