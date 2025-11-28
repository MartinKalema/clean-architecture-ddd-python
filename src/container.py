import os
from dependency_injector import containers, providers

from src.infrastructure.configurations.settings import load_config
from src.infrastructure.external.database import Database

from src.application.use_cases.add_book import AddBook
from src.application.use_cases.list_books import ListBooks
from src.application.use_cases.borrow_book import BorrowBook

from src.infrastructure.adapters.messaging.rabbitmq_event_dispatcher import RabbitMQEventDispatcher
from src.infrastructure.adapters.email.sendgrid_email_service import SendGridEmailService
from src.application.handlers.book_handlers import BookHandlers
from src.infrastructure.adapters.repositories.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork

from src.infrastructure.external.rabbitmq_client import RabbitMQClient
from src.infrastructure.external.sendgrid_client import SendGridClient

from src.infrastructure.adapters.templates.jinja2_template_renderer import Jinja2TemplateRenderer
from src.infrastructure.adapters.logger.standard_logger import StandardLogger
from src.infrastructure.adapters.logger.json_logger import JsonLogger

from src.infrastructure.adapters.resilience import CircuitBreaker, circuit_breaker_registry


def create_logger(config: dict):
    """Factory function to create appropriate logger based on config."""
    log_format = config.get("logging", {}).get("format", "json")
    if log_format == "json":
        return JsonLogger()
    return StandardLogger()


def create_circuit_breaker(
    name: str,
    failure_threshold: int,
    success_threshold: int,
    timeout: float,
    logger,
) -> CircuitBreaker:
    """Factory to create and register circuit breakers."""
    cb = CircuitBreaker(
        name=name,
        failure_threshold=failure_threshold,
        success_threshold=success_threshold,
        timeout=timeout,
        logger=logger,
    )
    circuit_breaker_registry.register(cb)
    return cb


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(modules=[
        "src.presentation.api.routes.book_routes",
        "src.presentation.api.routes.health_routes",
        "src.presentation.cli.commands.add_book_command",
        "src.presentation.cli.commands.list_books_command",
        "src.presentation.cli.commands.borrow_book_command"
    ])

    config = providers.Configuration()
    config.from_dict(load_config())

    # Logger - uses JSON format by default, configurable via LOG_FORMAT env var
    logger = providers.Singleton(
        create_logger,
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

    # External Drivers
    rabbitmq_client = providers.Singleton(
        RabbitMQClient,
        amqp_url=config.rabbitmq.url,
        logger=logger
    )

    sendgrid_client = providers.Singleton(
        SendGridClient,
        api_key=config.sendgrid.api_key,
        logger=logger
    )

    # Circuit Breakers - configured per external service
    rabbitmq_circuit_breaker = providers.Singleton(
        create_circuit_breaker,
        name="rabbitmq",
        failure_threshold=5,
        success_threshold=2,
        timeout=30.0,
        logger=logger,
    )

    sendgrid_circuit_breaker = providers.Singleton(
        create_circuit_breaker,
        name="sendgrid",
        failure_threshold=3,
        success_threshold=2,
        timeout=60.0,
        logger=logger,
    )

    # Adapters
    event_dispatcher = providers.Singleton(
        RabbitMQEventDispatcher,
        client=rabbitmq_client,
        exchange_name=config.rabbitmq.exchange_name,
        logger=logger,
        circuit_breaker=rabbitmq_circuit_breaker,
    )

    email_service = providers.Singleton(
        SendGridEmailService,
        client=sendgrid_client,
        from_email=config.sendgrid.from_email,
        admin_email=config.sendgrid.admin_email,
        logger=logger,
        circuit_breaker=sendgrid_circuit_breaker,
    )

    # Template Renderer
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
        event_dispatcher=event_dispatcher
    )

    add_book_use_case = providers.Factory(
        AddBook,
        uow=uow,
        logger=logger
    )

    list_books_use_case = providers.Factory(
        ListBooks,
        uow=uow,
        logger=logger
    )

    borrow_book_use_case = providers.Factory(
        BorrowBook,
        uow=uow,
        logger=logger
    )
