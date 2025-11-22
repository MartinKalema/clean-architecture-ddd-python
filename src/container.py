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
import os

class Container(containers.DeclarativeContainer):
    # ... (wiring config same) ...
    wiring_config = containers.WiringConfiguration(modules=[
        "src.presentation.api.routes.book_routes",
        "src.presentation.cli.commands.add_book_command",
        "src.presentation.cli.commands.list_books_command",
        "src.presentation.cli.commands.borrow_book_command"
    ])

    config = providers.Configuration()
    config.from_dict(load_config())

    database = providers.Singleton(
        Database,
        db_url=config.database.url
    )

    session_factory = providers.Resource(
        lambda db: db.session_factory,
        db=database
    )

    # External Drivers
    rabbitmq_client = providers.Singleton(
        RabbitMQClient,
        amqp_url=config.rabbitmq.url
    )

    sendgrid_client = providers.Singleton(
        SendGridClient,
        api_key=config.sendgrid.api_key
    )

    # Adapters
    event_dispatcher = providers.Singleton(
        RabbitMQEventDispatcher,
        client=rabbitmq_client,
        exchange_name="domain_events"
    )

    email_service = providers.Singleton(
        SendGridEmailService,
        client=sendgrid_client,
        from_email=config.sendgrid.from_email,
        admin_email=config.sendgrid.admin_email
    )

    # Template Renderer
    template_renderer = providers.Singleton(
        Jinja2TemplateRenderer,
        template_dir=config.templates.dir,
        template_map=config.templates.map
    )

    book_handlers = providers.Singleton(
        BookHandlers,
        email_service=email_service,
        template_renderer=template_renderer
    )

    uow = providers.Factory(
        SqlAlchemyUnitOfWork,
        session_factory=session_factory,
        event_dispatcher=event_dispatcher
    )

    add_book_use_case = providers.Factory(
        AddBook,
        uow=uow
    )

    list_books_use_case = providers.Factory(
        ListBooks,
        uow=uow
    )

    borrow_book_use_case = providers.Factory(
        BorrowBook,
        uow=uow
    )


