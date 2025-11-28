from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import click
from dependency_injector.wiring import inject, Provide

from src.container import Container
from src.application.commands import BorrowBookCommand

if TYPE_CHECKING:
    from src.application.commands import BorrowBookHandler


@click.command()
@click.argument("book_id")
@click.argument("borrower_email")
@inject
def borrow(
    book_id: str,
    borrower_email: str,
    handler: BorrowBookHandler = Provide[Container.borrow_book_handler]
):
    """Borrow a book from the catalog."""
    try:
        command = BorrowBookCommand(book_id=book_id, borrower_email=borrower_email)
        result = asyncio.run(handler.handle(command))
        click.echo(f"Successfully borrowed: {result.title}")
    except Exception as e:
        click.echo(f"Error: {e}")
